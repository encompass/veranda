"""A searchable picker for GNOME keyboard shortcuts, grouped by category."""

from __future__ import annotations

from typing import Callable

import gi

gi.require_version("Gtk", "4.0")
gi.require_version("Adw", "1")
from gi.repository import Adw, GLib, Gtk  # noqa: E402

from veranda import gnome_shortcuts  # noqa: E402
from veranda.gnome_shortcuts import GnomeShortcut  # noqa: E402


class ShortcutPicker(Adw.Dialog):
    """Pick a GNOME shortcut. Calls ``on_pick(GnomeShortcut)`` on selection."""

    def __init__(self, on_pick: Callable[[GnomeShortcut], None]) -> None:
        super().__init__()
        self._on_pick = on_pick
        self.set_title("Choose a Shortcut")
        self.set_content_width(540)
        self.set_content_height(620)

        self._catalog = gnome_shortcuts.catalog()

        toolbar = Adw.ToolbarView()
        toolbar.add_top_bar(Adw.HeaderBar())

        search_bar = Gtk.SearchBar()
        self._search = Gtk.SearchEntry(hexpand=True, placeholder_text="Search shortcuts…")
        self._search.connect("search-changed", lambda _e: self._populate())
        search_bar.set_child(self._search)
        search_bar.set_search_mode(True)
        search_bar.set_key_capture_widget(self)
        toolbar.add_top_bar(search_bar)

        self._page = Adw.PreferencesPage()
        toolbar.set_content(self._page)
        self.set_child(toolbar)

        self._groups: list[Adw.PreferencesGroup] = []
        self._populate()

    def _populate(self) -> None:
        for group in self._groups:
            self._page.remove(group)
        self._groups.clear()

        query = self._search.get_text().strip().lower()

        # Preserve catalog (category) order.
        order: list[str] = []
        by_cat: dict[str, list[GnomeShortcut]] = {}
        for sc in self._catalog:
            if query and query not in sc.description.lower() and query not in sc.category.lower():
                continue
            if sc.category not in by_cat:
                by_cat[sc.category] = []
                order.append(sc.category)
            by_cat[sc.category].append(sc)

        if not order:
            group = Adw.PreferencesGroup()
            group.add(Adw.ActionRow(title="No matching shortcuts"))
            self._page.add(group)
            self._groups.append(group)
            return

        for category in order:
            group = Adw.PreferencesGroup(title=category)
            for sc in by_cat[category]:
                detail = sc.command if sc.kind == "custom" else gnome_shortcuts.friendly_accel(sc.accel)
                row = Adw.ActionRow(
                    title=GLib.markup_escape_text(sc.description),
                    subtitle=GLib.markup_escape_text(detail),
                )
                row.set_activatable(True)
                row.connect("activated", self._on_row_activated, sc)
                group.add(row)
            self._page.add(group)
            self._groups.append(group)

    def _on_row_activated(self, _row, sc: GnomeShortcut) -> None:
        self._on_pick(sc)
        self.close()
