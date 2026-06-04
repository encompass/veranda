"""A searchable picker for installed applications."""

from __future__ import annotations

from typing import Callable

import gi

gi.require_version("Gtk", "4.0")
gi.require_version("Adw", "1")
from gi.repository import Adw, Gio, GLib, Gtk  # noqa: E402


def gicon_to_spec(gicon) -> str:
    """Reduce a GIcon to a render-friendly icon name or file path."""
    if isinstance(gicon, Gio.ThemedIcon):
        names = gicon.get_names()
        return names[0] if names else "application-x-executable-symbolic"
    if isinstance(gicon, Gio.FileIcon):
        path = gicon.get_file().get_path()
        return path or "application-x-executable-symbolic"
    return "application-x-executable-symbolic"


class AppPicker(Adw.Dialog):
    """Pick an installed app. Calls ``on_pick(desktop_id, name, icon_spec)``."""

    def __init__(self, on_pick: Callable[[str, str, str], None]) -> None:
        super().__init__()
        self._on_pick = on_pick
        self.set_title("Choose an App")
        self.set_content_width(520)
        self.set_content_height(600)

        self._apps = sorted(
            (a for a in Gio.AppInfo.get_all() if a.should_show() and a.get_id()),
            key=lambda a: a.get_display_name().lower(),
        )

        toolbar = Adw.ToolbarView()
        toolbar.add_top_bar(Adw.HeaderBar())
        search_bar = Gtk.SearchBar()
        self._search = Gtk.SearchEntry(hexpand=True, placeholder_text="Search apps…")
        self._search.connect("search-changed", lambda _e: self._populate())
        search_bar.set_child(self._search)
        search_bar.set_search_mode(True)
        search_bar.set_key_capture_widget(self)
        toolbar.add_top_bar(search_bar)

        self._list = Gtk.ListBox(selection_mode=Gtk.SelectionMode.NONE)
        self._list.add_css_class("boxed-list")
        self._list.connect("row-activated", self._on_activated)
        box = Gtk.Box(
            orientation=Gtk.Orientation.VERTICAL, margin_top=12, margin_bottom=12,
            margin_start=12, margin_end=12,
        )
        box.append(self._list)
        toolbar.set_content(Gtk.ScrolledWindow(child=box, vexpand=True))
        self.set_child(toolbar)
        self._populate()

    def _populate(self) -> None:
        child = self._list.get_first_child()
        while child is not None:
            nxt = child.get_next_sibling()
            self._list.remove(child)
            child = nxt
        query = self._search.get_text().strip().lower()
        for app in self._apps:
            name = app.get_display_name()
            if query and query not in name.lower():
                continue
            row = Adw.ActionRow(title=GLib.markup_escape_text(name))
            gicon = app.get_icon()
            if gicon is not None:
                row.add_prefix(Gtk.Image.new_from_gicon(gicon))
            row._app = app
            self._list.append(row)

    def _on_activated(self, _list, row) -> None:
        app = row._app
        self._on_pick(app.get_id(), app.get_display_name(), gicon_to_spec(app.get_icon()))
        self.close()
