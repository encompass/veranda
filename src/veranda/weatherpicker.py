"""Pick a weather location from the ones saved in GNOME Weather."""

from __future__ import annotations

import logging
from typing import Callable

import gi

gi.require_version("Gtk", "4.0")
gi.require_version("Adw", "1")
from gi.repository import Adw, Gio, GLib, Gtk  # noqa: E402

log = logging.getLogger(__name__)

WEATHER_SCHEMA = "org.gnome.Weather"


def saved_locations() -> list[tuple[str, float, float]]:
    """Return ``(name, lat, lon)`` for each location saved in GNOME Weather.

    Reads ``org.gnome.Weather``'s ``locations`` GSettings key and deserializes
    each entry with GWeather. Returns an empty list if GNOME Weather (its
    schema) or GWeather is unavailable, so callers can degrade gracefully.
    """
    source = Gio.SettingsSchemaSource.get_default()
    if source is None or source.lookup(WEATHER_SCHEMA, True) is None:
        return []
    try:
        gi.require_version("GWeather", "4.0")
        from gi.repository import GWeather
    except (ValueError, ImportError):
        return []

    world = GWeather.Location.get_world()
    if world is None:
        return []
    settings = Gio.Settings.new(WEATHER_SCHEMA)
    out: list[tuple[str, float, float]] = []
    value = settings.get_value("locations")  # type 'av'
    for i in range(value.n_children()):
        try:
            inner = value.get_child_value(i).get_variant()  # unwrap the 'v'
            loc = GWeather.Location.deserialize(world, inner)
            if loc is None:
                continue
            coords = loc.get_coords()  # (lat, lon) in degrees
            lat, lon = float(coords[-2]), float(coords[-1])
            out.append((loc.get_name(), lat, lon))
        except Exception:  # noqa: BLE001
            log.debug("could not parse a saved weather location", exc_info=True)
    return out


class WeatherLocationPicker(Adw.Dialog):
    """Pick from GNOME Weather's saved locations.

    Calls ``on_pick(name, lat, lon)`` on selection. ``on_open_weather`` is
    invoked from the "Open GNOME Weather" row so the user can add locations.
    """

    def __init__(
        self,
        on_pick: Callable[[str, float, float], None],
        on_open_weather: Callable[[], None],
    ) -> None:
        super().__init__()
        self._on_pick = on_pick
        self.set_title("Choose a Location")
        self.set_content_width(460)
        self.set_content_height(520)

        toolbar = Adw.ToolbarView()
        toolbar.add_top_bar(Adw.HeaderBar())
        page = Adw.PreferencesPage()
        group = Adw.PreferencesGroup(
            title="From GNOME Weather",
            description="Locations you've added in the GNOME Weather app.",
        )
        page.add(group)

        locations = saved_locations()
        for name, lat, lon in locations:
            row = Adw.ActionRow(
                title=GLib.markup_escape_text(name),
                subtitle=f"{lat:.2f}, {lon:.2f}",
            )
            row.add_prefix(Gtk.Image.new_from_icon_name("weather-few-clouds-symbolic"))
            row.set_activatable(True)
            row.connect(
                "activated",
                lambda _r, n=name, la=lat, lo=lon: self._choose(n, la, lo),
            )
            group.add(row)

        if not locations:
            group.add(Adw.ActionRow(
                title="No locations in GNOME Weather",
                subtitle="Add a location there, then pick it here.",
            ))

        open_row = Adw.ActionRow(
            title="Open GNOME Weather",
            subtitle="Add or manage your locations",
        )
        open_btn = Gtk.Button(label="Open", valign=Gtk.Align.CENTER)
        open_btn.connect("clicked", lambda _b: (on_open_weather(), self.close()))
        open_row.add_suffix(open_btn)
        open_row.set_activatable_widget(open_btn)
        group.add(open_row)

        toolbar.set_content(page)
        self.set_child(toolbar)

    def _choose(self, name: str, lat: float, lon: float) -> None:
        self._on_pick(name, lat, lon)
        self.close()
