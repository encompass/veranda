"""Connectivity Special Buttons: Network, Weather, Software Updates."""

from __future__ import annotations

import logging
import re
from typing import Callable

from gi.repository import Gio, GLib

from veranda import launch
from veranda.actions.base import ActionContext
from veranda.actions.special.widget import LiveWidget, run_async

log = logging.getLogger(__name__)


class NetworkWidget(LiveWidget):
    TYPE_ID = "network"
    NAME = "Network"
    DESCRIPTION = "Active connection; opens network settings"
    ICON = "network-wireless-symbolic"
    REFRESH_INTERVAL = 5

    def __init__(self, params: dict | None = None) -> None:
        super().__init__(params)
        self._name: str | None = None
        self._kind = "offline"

    def refresh(self) -> None:
        run_async(
            ["nmcli", "-t", "-f", "NAME,TYPE", "connection", "show", "--active"],
            self._parse,
        )

    def _parse(self, out: str) -> None:
        name, kind = None, "offline"
        for line in out.splitlines():
            fields = re.split(r"(?<!\\):", line)
            if len(fields) < 2:
                continue
            nm, tp = fields[0].replace("\\:", ":"), fields[1]
            if "wireless" in tp:
                name, kind = nm, "wifi"
                break
            if "ethernet" in tp:
                name, kind = nm, "wired"
                break
        self._name, self._kind = name, kind
        self._emit_update()

    def display_icon(self) -> str:
        return {
            "wifi": "network-wireless-symbolic",
            "wired": "network-wired-symbolic",
        }.get(self._kind, "network-offline-symbolic")

    def display_text(self) -> str:
        if not self._name:
            return "Offline"
        return (self._name[:10] + "…") if len(self._name) > 11 else self._name

    def summary(self) -> str:
        return "Active network connection"

    def execute(self, ctx: ActionContext) -> None:
        launch.open_settings("wifi")


class WeatherWidget(LiveWidget):
    TYPE_ID = "weather"
    NAME = "Weather"
    DESCRIPTION = "Current temperature for a location"
    ICON = "weather-clear-symbolic"
    REFRESH_INTERVAL = 1800
    MIN_INTERVAL = 300

    def __init__(self, params: dict | None = None) -> None:
        super().__init__(params)
        self._info = None
        self._temp: int | None = None
        self._icon: str | None = None

    def _has_location(self) -> bool:
        return "serialized" in self.params or (
            "lat" in self.params and "lon" in self.params
        )

    def _build_location(self, GWeather):
        """Reconstruct the GWeather location, preferring the exact one GNOME
        Weather saved (with its station); fall back to detached lat/lon."""
        serialized = self.params.get("serialized")
        if serialized:
            try:
                variant = GLib.Variant.parse(None, serialized, None, None)
                loc = GWeather.Location.deserialize(
                    GWeather.Location.get_world(), variant
                )
                if loc is not None:
                    return loc
            except Exception:  # noqa: BLE001
                log.debug("could not deserialize saved location", exc_info=True)
        if "lat" in self.params and "lon" in self.params:
            return GWeather.Location.new_detached(
                self.params.get("name") or "Location", None,
                float(self.params["lat"]), float(self.params["lon"]),
            )
        return None

    def refresh(self) -> None:
        if not self._has_location():
            self._emit_update()
            return
        try:
            import gi
            gi.require_version("GWeather", "4.0")
            from gi.repository import GWeather

            loc = self._build_location(GWeather)
            if loc is None:
                self._emit_update()
                return
            info = GWeather.Info()
            info.set_application_id("com.encompass.Veranda")
            info.set_contact_info("https://github.com/encompass/veranda")
            # Without enabling providers GWeather fetches nothing. Use the
            # global providers GNOME Weather relies on: MET_NO works anywhere
            # from coordinates, METAR adds station observations where available.
            # (Provider.ALL also pulls the US-only weather.gov, whose invalid
            # responses elsewhere mask the good data.)
            info.set_enabled_providers(
                GWeather.Provider.METAR | GWeather.Provider.MET_NO
            )
            info.set_location(loc)
            info.connect("updated", self._on_updated)
            self._info = info  # keep a ref while the async fetch runs
            info.update()
        except Exception as exc:  # noqa: BLE001
            log.debug("weather refresh failed: %s", exc)
            self._emit_update()

    def _on_updated(self, info) -> None:
        try:
            import gi
            gi.require_version("GWeather", "4.0")
            from gi.repository import GWeather

            # DEFAULT uses the unit the user picked in GNOME (°C/°F), like
            # GNOME Weather itself.
            ok, temp = info.get_value_temp(GWeather.TemperatureUnit.DEFAULT)
            if ok:
                self._temp = round(temp)
            icon = info.get_symbolic_icon_name()
            if icon:
                self._icon = icon
        except Exception:  # noqa: BLE001
            log.debug("weather update parse failed", exc_info=True)
        self._emit_update()

    def display_icon(self) -> str:
        return self._icon or self.ICON

    def display_text(self) -> str:
        if not self._has_location():
            return "Set"
        return f"{self._temp}°" if self._temp is not None else "…"

    def summary(self) -> str:
        return self.params.get("name") or "No location set"

    def build_editor_rows(self, button, on_change: Callable[[], None]):
        from gi.repository import Adw, Gtk

        from veranda.weatherpicker import WeatherLocationPicker

        row = Adw.ActionRow(
            title="Location",
            subtitle=self.params.get("name") or "None chosen",
        )
        choose = Gtk.Button(label="Choose…", valign=Gtk.Align.CENTER)

        def pick(name, lat, lon, serialized):
            self.params["name"] = name
            self.params["lat"] = lat
            self.params["lon"] = lon
            self.params["serialized"] = serialized
            self._temp = None  # force a fresh fetch for the new place
            self._icon = None  # and a fresh condition icon
            row.set_subtitle(name)
            on_change()

        choose.connect(
            "clicked",
            lambda _b: WeatherLocationPicker(pick, self._open_weather).present(row.get_root()),
        )
        row.add_suffix(choose)
        row.set_activatable_widget(choose)
        return [row]

    @staticmethod
    def _open_weather() -> None:
        if not launch.open_app("org.gnome.Weather"):
            launch.run(["gnome-weather"])

    def execute(self, ctx: ActionContext) -> None:
        self._open_weather()


class UpdatesWidget(LiveWidget):
    TYPE_ID = "updates"
    NAME = "Software Updates"
    DESCRIPTION = "Pending update count; opens GNOME Software"
    ICON = "software-update-available-symbolic"
    REFRESH_INTERVAL = 3600
    MIN_INTERVAL = 300

    def __init__(self, params: dict | None = None) -> None:
        super().__init__(params)
        self._count: int | None = None
        self._conn = None

    def refresh(self) -> None:
        try:
            self._conn = Gio.bus_get_sync(Gio.BusType.SYSTEM, None)
        except GLib.Error:
            return
        self._conn.call(
            "org.freedesktop.PackageKit", "/org/freedesktop/PackageKit",
            "org.freedesktop.PackageKit", "CreateTransaction", None,
            GLib.VariantType.new("(o)"), Gio.DBusCallFlags.NONE, -1, None, self._on_tx,
        )

    def _on_tx(self, conn, result) -> None:
        try:
            path = conn.call_finish(result).unpack()[0]
        except GLib.Error as exc:
            log.debug("updates: CreateTransaction failed: %s", exc)
            return
        count = [0]
        subs = []

        def on_package(*_a):
            count[0] += 1

        def on_finished(*_a):
            for sid in subs:
                conn.signal_unsubscribe(sid)
            self._count = count[0]
            self._emit_update()

        subs.append(conn.signal_subscribe(
            None, "org.freedesktop.PackageKit.Transaction", "Package", path, None,
            Gio.DBusSignalFlags.NONE, on_package))
        subs.append(conn.signal_subscribe(
            None, "org.freedesktop.PackageKit.Transaction", "Finished", path, None,
            Gio.DBusSignalFlags.NONE, on_finished))
        conn.call(
            "org.freedesktop.PackageKit", path,
            "org.freedesktop.PackageKit.Transaction", "GetUpdates",
            GLib.Variant("(t)", (0,)), None, Gio.DBusCallFlags.NONE, -1, None, None,
        )

    def badge_text(self) -> str | None:
        return str(self._count) if self._count else None

    def display_text(self) -> str:
        return ""

    def summary(self) -> str:
        return "Available software updates"

    def execute(self, ctx: ActionContext) -> None:
        if not launch.open_app("org.gnome.Software"):
            ctx.notify("GNOME Software is not installed")
