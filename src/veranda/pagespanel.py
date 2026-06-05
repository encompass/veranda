"""Left sidebar listing the active profile's pages, with drag-to-reorder."""

from __future__ import annotations

from typing import Callable

import gi

gi.require_version("Gtk", "4.0")
gi.require_version("Adw", "1")
from gi.repository import Gdk, GObject, Gtk  # noqa: E402

from veranda.models import PageMove  # noqa: E402
from veranda.sidebar import CollapsibleSection  # noqa: E402


class PagesPanel(Gtk.Box):
    """Collapsible list of pages. Click to switch, drag to reorder, menu to
    rename/remove. The window supplies the callbacks and calls :meth:`update`.
    """

    def __init__(
        self,
        on_select: Callable[[int], None],
        on_reorder: Callable[[int, int], None],
        on_add: Callable[[], None],
        on_rename: Callable[[int], None],
        on_remove: Callable[[int], None],
    ) -> None:
        super().__init__(orientation=Gtk.Orientation.VERTICAL, width_request=190, vexpand=True)
        self.add_css_class("pages-panel")
        self._on_select = on_select
        self._on_reorder = on_reorder
        self._on_add = on_add
        self._on_rename = on_rename
        self._on_remove = on_remove
        self._selecting = False

        section = CollapsibleSection(
            "Pages", on_add=lambda: self._on_add(), add_tooltip="Add a page",
            vexpand=True,
        )
        self._list = Gtk.ListBox(selection_mode=Gtk.SelectionMode.SINGLE)
        self._list.add_css_class("navigation-sidebar")
        self._list.connect("row-activated", self._on_row_activated)
        scroller = Gtk.ScrolledWindow(hexpand=False, vexpand=True)
        scroller.set_policy(Gtk.PolicyType.NEVER, Gtk.PolicyType.AUTOMATIC)
        scroller.set_child(self._list)
        section.set_content(scroller)
        self.append(section)

    # -- population -------------------------------------------------------

    def update(self, names: list[str], active: int) -> None:
        self._selecting = True
        child = self._list.get_first_child()
        while child is not None:
            nxt = child.get_next_sibling()
            self._list.remove(child)
            child = nxt
        for i, name in enumerate(names):
            self._list.append(self._make_row(i, name, can_remove=len(names) > 1))
        row = self._list.get_row_at_index(active)
        if row is not None:
            self._list.select_row(row)
        self._selecting = False

    def _make_row(self, index: int, name: str, can_remove: bool) -> Gtk.ListBoxRow:
        row = Gtk.ListBoxRow()
        row._index = index  # type: ignore[attr-defined]

        box = Gtk.Box(
            orientation=Gtk.Orientation.HORIZONTAL, spacing=6,
            margin_top=8, margin_bottom=8, margin_start=10, margin_end=4,
        )
        handle = Gtk.Image.new_from_icon_name("list-drag-handle-symbolic")
        handle.add_css_class("dim-label")
        box.append(handle)
        label = Gtk.Label(label=name or f"Page {index + 1}", xalign=0.0, hexpand=True)
        box.append(label)
        box.append(self._row_menu(index, can_remove))
        row.set_child(box)

        drag = Gtk.DragSource(actions=Gdk.DragAction.MOVE)
        drag.connect(
            "prepare",
            lambda *_a, i=index: Gdk.ContentProvider.new_for_value(
                GObject.Value(PageMove, PageMove(i))
            ),
        )
        drag.connect(
            "drag-begin",
            lambda source, _d, r=row: source.set_icon(
                Gtk.WidgetPaintable.new(r), r.get_width() // 2, r.get_height() // 2
            ),
        )
        row.add_controller(drag)

        drop = Gtk.DropTarget.new(PageMove, Gdk.DragAction.MOVE)
        drop.connect("drop", lambda _t, value, _x, _y, i=index: self._do_drop(value, i))
        row.add_controller(drop)
        return row

    def _row_menu(self, index: int, can_remove: bool) -> Gtk.MenuButton:
        button = Gtk.MenuButton(
            icon_name="view-more-symbolic", valign=Gtk.Align.CENTER,
            tooltip_text="Page options",
        )
        button.add_css_class("flat")
        popover = Gtk.Popover()
        vbox = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=0)
        vbox.add_css_class("menu")
        rename = Gtk.Button(child=Gtk.Label(label="Rename…", xalign=0.0))
        rename.add_css_class("flat")
        rename.connect("clicked", lambda _b: (popover.popdown(), self._on_rename(index)))
        vbox.append(rename)
        remove = Gtk.Button(child=Gtk.Label(label="Remove", xalign=0.0))
        remove.add_css_class("flat")
        remove.set_sensitive(can_remove)
        remove.connect("clicked", lambda _b: (popover.popdown(), self._on_remove(index)))
        vbox.append(remove)
        popover.set_child(vbox)
        button.set_popover(popover)
        return button

    # -- events -----------------------------------------------------------

    def _do_drop(self, value, dst_index: int) -> bool:
        if isinstance(value, PageMove) and value.source_index != dst_index:
            self._on_reorder(value.source_index, dst_index)
        return True

    def _on_row_activated(self, _list, row) -> None:
        if self._selecting:
            return
        self._on_select(row._index)
