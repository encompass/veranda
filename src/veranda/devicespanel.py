"""Left sidebar listing the connected/virtual devices, with per-device options."""

from __future__ import annotations

from typing import Callable

import gi

gi.require_version("Gtk", "4.0")
from gi.repository import Gtk  # noqa: E402

from veranda.sidebar import CollapsibleSection  # noqa: E402


class DevicesPanel(Gtk.Box):
    """Collapsible "Devices" section: click a device to select it; each row has
    a ⋮ menu (Rename, plus Settings/Remove for virtual decks); the header's +
    adds a virtual device.
    """

    def __init__(
        self,
        on_select: Callable[[str], None],
        on_add: Callable[[], None],
        on_rename: Callable[[str], None],
        on_settings: Callable[[str], None],
        on_remove: Callable[[str], None],
    ) -> None:
        super().__init__(orientation=Gtk.Orientation.VERTICAL, width_request=190)
        self.add_css_class("devices-panel")
        self._on_select = on_select
        self._on_rename = on_rename
        self._on_settings = on_settings
        self._on_remove = on_remove
        self._selecting = False

        section = CollapsibleSection(
            "Devices", on_add=on_add, add_tooltip="Add a virtual device"
        )
        self._list = Gtk.ListBox(selection_mode=Gtk.SelectionMode.SINGLE)
        self._list.add_css_class("navigation-sidebar")
        self._list.connect("row-activated", self._on_row_activated)
        section.set_content(self._list)
        self.append(section)

    def update(self, devices: list[tuple[str, str, bool]], current: str | None) -> None:
        """``devices`` = list of (serial, display_name, is_virtual)."""
        self._selecting = True
        child = self._list.get_first_child()
        while child is not None:
            nxt = child.get_next_sibling()
            self._list.remove(child)
            child = nxt
        selected = None
        for serial, name, is_virtual in devices:
            row = self._make_row(serial, name, is_virtual)
            self._list.append(row)
            if serial == current:
                selected = row
        if selected is not None:
            self._list.select_row(selected)
        self._selecting = False

    def _make_row(self, serial: str, name: str, is_virtual: bool) -> Gtk.ListBoxRow:
        row = Gtk.ListBoxRow()
        row._serial = serial  # type: ignore[attr-defined]
        box = Gtk.Box(
            orientation=Gtk.Orientation.HORIZONTAL, spacing=8,
            margin_top=8, margin_bottom=8, margin_start=10, margin_end=4,
        )
        icon = Gtk.Image.new_from_icon_name(
            "video-display-symbolic" if is_virtual else "input-tablet-symbolic"
        )
        icon.add_css_class("dim-label")
        box.append(icon)
        label = Gtk.Label(label=name, xalign=0.0, hexpand=True, ellipsize=3)  # END
        box.append(label)
        box.append(self._row_menu(serial, is_virtual))
        row.set_child(box)
        return row

    def _row_menu(self, serial: str, is_virtual: bool) -> Gtk.MenuButton:
        button = Gtk.MenuButton(
            icon_name="view-more-symbolic", valign=Gtk.Align.CENTER,
            tooltip_text="Device options",
        )
        button.add_css_class("flat")
        popover = Gtk.Popover()
        vbox = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=0)
        vbox.add_css_class("menu")

        def item(label, handler):
            b = Gtk.Button(child=Gtk.Label(label=label, xalign=0.0))
            b.add_css_class("flat")
            b.connect("clicked", lambda _b: (popover.popdown(), handler(serial)))
            vbox.append(b)

        item("Rename…", self._on_rename)
        item("Settings…", self._on_settings)
        if is_virtual:
            item("Remove", self._on_remove)
        popover.set_child(vbox)
        button.set_popover(popover)
        return button

    def _on_row_activated(self, _list, row) -> None:
        if self._selecting:
            return
        self._on_select(row._serial)
