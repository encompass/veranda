"""A single on-screen button tile that mirrors a physical deck key."""

from __future__ import annotations

from typing import Callable

import gi

gi.require_version("Gtk", "4.0")
from gi.repository import Gdk, Gtk  # noqa: E402

from veranda.models import ActionItem, ButtonConfig  # noqa: E402
from veranda.render import render_preview_texture  # noqa: E402

TILE_SIZE = 108


class DeckTile(Gtk.Button):
    """A flat, rounded tile representing one key.

    When bound, it shows the exact composited image that appears on the
    physical key (so the GUI is a faithful preview). It is a drop target for
    actions dragged from the library and opens the editor when clicked.
    """

    def __init__(
        self,
        key: int,
        on_drop: Callable[[int, ActionItem], None],
        on_select: Callable[[int], None],
    ) -> None:
        super().__init__()
        self.key = key
        self._on_drop = on_drop
        self._on_select = on_select

        self.add_css_class("deck-tile")
        self.add_css_class("flat")
        self.set_size_request(TILE_SIZE, TILE_SIZE)

        self._stack = Gtk.Stack()

        # Bound state: the composited key image.
        self._picture = Gtk.Picture(content_fit=Gtk.ContentFit.CONTAIN)
        self._picture.set_size_request(TILE_SIZE, TILE_SIZE)
        self._stack.add_named(self._picture, "image")

        # Empty state: a dim "add" hint.
        empty = Gtk.Box(
            orientation=Gtk.Orientation.VERTICAL,
            valign=Gtk.Align.CENTER,
            halign=Gtk.Align.CENTER,
        )
        empty.add_css_class("deck-tile-empty")
        add_icon = Gtk.Image.new_from_icon_name("list-add-symbolic")
        add_icon.set_pixel_size(28)
        add_icon.add_css_class("dim-label")
        empty.append(add_icon)
        self._stack.add_named(empty, "empty")

        self.set_child(self._stack)

        self.connect("clicked", lambda _btn: self._on_select(self.key))
        self._install_drop_target()
        self.set_empty()

    # -- drop target ------------------------------------------------------

    def _install_drop_target(self) -> None:
        target = Gtk.DropTarget.new(ActionItem, Gdk.DragAction.COPY)
        target.connect("drop", self._handle_drop)
        target.connect("enter", self._handle_enter)
        target.connect("leave", self._handle_leave)
        self.add_controller(target)

    def _handle_drop(self, _target, value, _x, _y) -> bool:
        self.remove_css_class("drop-hover")
        if isinstance(value, ActionItem):
            self._on_drop(self.key, value)
            return True
        return False

    def _handle_enter(self, _target, _x, _y) -> Gdk.DragAction:
        self.add_css_class("drop-hover")
        return Gdk.DragAction.COPY

    def _handle_leave(self, _target) -> None:
        self.remove_css_class("drop-hover")

    # -- state ------------------------------------------------------------

    def set_button(self, button: ButtonConfig | None) -> None:
        if button is None or button.is_empty:
            self.set_empty()
            return
        self.add_css_class("bound")
        self._picture.set_paintable(render_preview_texture(button))
        self._stack.set_visible_child_name("image")

    def set_empty(self) -> None:
        self.remove_css_class("bound")
        self._stack.set_visible_child_name("empty")

    def set_selected(self, selected: bool) -> None:
        if selected:
            self.add_css_class("selected")
        else:
            self.remove_css_class("selected")
