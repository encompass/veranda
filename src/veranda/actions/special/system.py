"""System Special Buttons: Battery, System Monitor, Volume, Do Not Disturb."""

from __future__ import annotations

import logging
import os
from typing import Callable

from gi.repository import Gio, GLib

from veranda import launch
from veranda.actions.base import ActionContext
from veranda.actions.special.widget import LiveWidget, run_async

log = logging.getLogger(__name__)


class BatteryWidget(LiveWidget):
    TYPE_ID = "battery"
    NAME = "Battery"
    DESCRIPTION = "Charge level; opens power settings"
    ICON = "battery-good-symbolic"

    def __init__(self, params: dict | None = None) -> None:
        super().__init__(params)
        self._proxy = None
        self._sig = 0

    def subscribe(self) -> bool:
        try:
            self._proxy = Gio.DBusProxy.new_for_bus_sync(
                Gio.BusType.SYSTEM, Gio.DBusProxyFlags.NONE, None,
                "org.freedesktop.UPower",
                "/org/freedesktop/UPower/devices/DisplayDevice",
                "org.freedesktop.UPower.Device", None,
            )
        except GLib.Error:
            self._proxy = None
            return False
        self._sig = self._proxy.connect("g-properties-changed", lambda *_a: self._emit_update())
        self._emit_update()
        return True

    def unsubscribe(self) -> None:
        if self._proxy is not None and self._sig:
            try:
                self._proxy.disconnect(self._sig)
            except Exception:  # noqa: BLE001
                pass
        self._sig = 0
        self._proxy = None

    def _prop(self, name):
        if self._proxy is None:
            return None
        v = self._proxy.get_cached_property(name)
        return v.unpack() if v is not None else None

    def display_icon(self) -> str:
        return self._prop("IconName") or self.ICON

    def display_text(self) -> str:
        pct = self._prop("Percentage")
        return f"{round(pct)}%" if pct is not None else ""

    def summary(self) -> str:
        return "Battery level"

    def execute(self, ctx: ActionContext) -> None:
        launch.open_settings("power")


class SystemMonitorWidget(LiveWidget):
    TYPE_ID = "sysmon"
    NAME = "System Monitor"
    DESCRIPTION = "CPU / memory / disk usage"
    ICON = "org.gnome.SystemMonitor-symbolic"
    REFRESH_INTERVAL = 3
    EDIT_LABEL = False  # the widget draws the percentage

    def default_label(self) -> str:
        return ""

    def __init__(self, params: dict | None = None) -> None:
        super().__init__(params)
        self._prev = None
        self._value: int | None = None

    @property
    def _metric(self) -> str:
        return self.params.get("metric", "cpu")  # cpu | mem | disk

    def refresh(self) -> None:
        if self._metric == "mem":
            self._value = self._mem_percent()
        elif self._metric == "disk":
            self._value = self._disk_percent()
        else:
            self._value = self._cpu_percent()
        self._emit_update()

    def _cpu_percent(self) -> int | None:
        try:
            with open("/proc/stat") as fh:
                parts = [float(x) for x in fh.readline().split()[1:]]
        except OSError:
            return None
        idle = parts[3] + (parts[4] if len(parts) > 4 else 0)
        total = sum(parts)
        pct = 0
        if self._prev is not None:
            dt, di = total - self._prev[0], idle - self._prev[1]
            pct = 0 if dt <= 0 else round((1 - di / dt) * 100)
        self._prev = (total, idle)
        return pct

    def _mem_percent(self) -> int | None:
        try:
            info = {}
            with open("/proc/meminfo") as fh:
                for line in fh:
                    k, _, v = line.partition(":")
                    info[k] = int(v.split()[0])
        except OSError:
            return None
        total = info.get("MemTotal", 0)
        avail = info.get("MemAvailable", info.get("MemFree", 0))
        return round((1 - avail / total) * 100) if total else None

    def _disk_percent(self) -> int | None:
        try:
            st = os.statvfs(os.path.expanduser("~"))
        except OSError:
            return None
        used = st.f_blocks - st.f_bfree
        return round(used / st.f_blocks * 100) if st.f_blocks else None

    def display_icon(self):
        return None  # big centered percentage

    def display_text(self) -> str:
        return f"{self._value}%" if self._value is not None else "—"

    def summary(self) -> str:
        return {"cpu": "CPU usage", "mem": "Memory usage", "disk": "Disk usage"}[self._metric]

    def build_editor_rows(self, button, on_change: Callable[[], None]):
        from gi.repository import Adw, Gtk

        row = Adw.ComboRow(title="Metric")
        labels = Gtk.StringList()
        for text in ("CPU", "Memory", "Disk"):
            labels.append(text)
        order = ["cpu", "mem", "disk"]
        row.set_model(labels)
        row.set_selected(order.index(self._metric))

        def changed(r, _p):
            self.params["metric"] = order[r.get_selected()]
            self._prev = None
            on_change()

        row.connect("notify::selected", changed)
        return [row]

    def execute(self, ctx: ActionContext) -> None:
        if not launch.open_app("gnome-system-monitor"):
            if not launch.run(["gnome-system-monitor"]):
                ctx.notify("System Monitor is not installed")


class VolumeWidget(LiveWidget):
    TYPE_ID = "volume"
    NAME = "Volume"
    DESCRIPTION = "Output volume; press toggles mute"
    ICON = "audio-volume-high-symbolic"
    REFRESH_INTERVAL = 2
    SINK = "@DEFAULT_AUDIO_SINK@"

    def __init__(self, params: dict | None = None) -> None:
        super().__init__(params)
        self._pct: int | None = None
        self._muted = False

    def refresh(self) -> None:
        run_async(["wpctl", "get-volume", self.SINK], self._parse)

    def _parse(self, out: str) -> None:
        self._muted = "MUTED" in out
        try:
            self._pct = round(float(out.split()[1]) * 100)
        except (IndexError, ValueError):
            self._pct = None
        self._emit_update()

    def display_icon(self) -> str:
        if self._muted:
            return "audio-volume-muted-symbolic"
        if self._pct is None:
            return "audio-volume-medium-symbolic"
        if self._pct < 34:
            return "audio-volume-low-symbolic"
        if self._pct < 67:
            return "audio-volume-medium-symbolic"
        return "audio-volume-high-symbolic"

    def display_text(self) -> str:
        return f"{self._pct}%" if self._pct is not None else ""

    def summary(self) -> str:
        return "Output volume + mute"

    def execute(self, ctx: ActionContext) -> None:
        launch.run(["wpctl", "set-mute", self.SINK, "toggle"])
        GLib.timeout_add(200, self._delayed_refresh)

    def _delayed_refresh(self) -> bool:
        self.refresh()
        return False


class DoNotDisturbWidget(LiveWidget):
    TYPE_ID = "dnd"
    NAME = "Do Not Disturb"
    DESCRIPTION = "Toggle notification banners"
    ICON = "preferences-system-notifications-symbolic"
    SCHEMA = "org.gnome.desktop.notifications"
    EDIT_LABEL = False  # the bell / bell-slash icon says it all

    def default_label(self) -> str:
        return ""

    def __init__(self, params: dict | None = None) -> None:
        super().__init__(params)
        self._settings = None
        self._sig = 0

    def _ensure_settings(self):
        if self._settings is None:
            try:
                self._settings = Gio.Settings(schema_id=self.SCHEMA)
            except Exception:  # noqa: BLE001
                self._settings = None
        return self._settings

    def subscribe(self) -> bool:
        settings = self._ensure_settings()
        if settings is None:
            return False
        self._sig = settings.connect("changed::show-banners", lambda *_a: self._emit_update())
        self._emit_update()
        return True

    def unsubscribe(self) -> None:
        if self._settings is not None and self._sig:
            self._settings.disconnect(self._sig)
        self._sig = 0

    def _dnd_on(self) -> bool:
        settings = self._ensure_settings()
        return settings is not None and not settings.get_boolean("show-banners")

    def display_icon(self) -> str:
        return "notifications-disabled-symbolic" if self._dnd_on() else self.ICON

    def display_text(self) -> str:
        return ""

    def summary(self) -> str:
        return "Do Not Disturb"

    def execute(self, ctx: ActionContext) -> None:
        settings = self._ensure_settings()
        if settings is not None:
            settings.set_boolean("show-banners", not settings.get_boolean("show-banners"))
