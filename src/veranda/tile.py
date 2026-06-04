"""A single on-screen button tile that mirrors a physical deck key."""

from __future__ import annotations

from typing import Callable

import gi

gi.require_version("Gtk", "4.0")
from gi.repository import Gdk, GObject, Gtk  # noqa: E402

from veranda.models import ActionItem, ButtonConfig, TileMove  # noqa: E402
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
        on_move: Callable[[int, int], None],
        on_file_drop: Callable[[int, object], None],
        on_clear: Callable[[int], None],
        on_command: Callable[[int, str], None],
        can_paste: Callable[[], bool],
    ) -> None:
        super().__init__()
        self.key = key
        self._on_drop = on_drop
        self._on_select = on_select
        self._on_move = on_move
        self._on_file_drop = on_file_drop
        self._on_clear = on_clear
        self._on_command = on_command
        self._can_paste = can_paste
        self._bound = False

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
        self._install_drag_source()
        self._install_context_menu()
        self.set_empty()

    # -- context menu / clear ---------------------------------------------

    def _install_context_menu(self) -> None:
        gesture = Gtk.GestureClick(button=Gdk.BUTTON_SECONDARY)
        gesture.connect("pressed", self._on_secondary_press)
        self.add_controller(gesture)

        keys = Gtk.EventControllerKey()
        keys.connect("key-pressed", self._on_key_pressed)
        self.add_controller(keys)

    def _menu_button(self, label: str, on_click, destructive: bool = False) -> Gtk.Button:
        button = Gtk.Button()
        button.add_css_class("flat")
        text = Gtk.Label(label=label, xalign=0.0, hexpand=True)
        if destructive:
            text.add_css_class("error")
        button.set_child(text)
        button.connect("clicked", on_click)
        return button

    def _on_secondary_press(self, _gesture, _n, x, y) -> None:
        can_paste = self._can_paste()
        if not self._bound and not can_paste:
            return
        popover = Gtk.Popover(has_arrow=True)
        popover.connect("closed", lambda p: p.unparent())
        box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=0)
        box.add_css_class("menu")

        def item(label, cmd, destructive=False):
            def click(_b):
                popover.popdown()
                if cmd == "edit":
                    self._on_select(self.key)
                elif cmd == "clear":
                    self._on_clear(self.key)
                else:
                    self._on_command(self.key, cmd)
            box.append(self._menu_button(label, click, destructive))

        if self._bound:
            item("Edit…", "edit")
            item("Copy", "copy")
            item("Duplicate", "duplicate")
        if can_paste:
            item("Paste", "paste")
        if self._bound:
            item("Clear Key", "clear", destructive=True)

        popover.set_child(box)
        popover.set_parent(self)
        rect = Gdk.Rectangle()
        rect.x, rect.y, rect.width, rect.height = int(x), int(y), 1, 1
        popover.set_pointing_to(rect)
        popover.popup()

    def _on_key_pressed(self, _ctrl, keyval, _code, state) -> bool:
        ctrl = bool(state & Gdk.ModifierType.CONTROL_MASK)
        if ctrl and self._bound and keyval == Gdk.KEY_c:
            self._on_command(self.key, "copy")
            return True
        if ctrl and self._bound and keyval == Gdk.KEY_d:
            self._on_command(self.key, "duplicate")
            return True
        if ctrl and keyval == Gdk.KEY_v and self._can_paste():
            self._on_command(self.key, "paste")
            return True
        if self._bound and keyval in (Gdk.KEY_Delete, Gdk.KEY_BackSpace):
            self._on_clear(self.key)
            return True
        return False

    # -- drag source (move a binding to another key) ----------------------

    def _install_drag_source(self) -> None:
        drag = Gtk.DragSource(actions=Gdk.DragAction.MOVE)
        drag.connect("prepare", self._handle_prepare)
        drag.connect("drag-begin", self._handle_drag_begin)
        self.add_controller(drag)

    def _handle_prepare(self, _source, _x, _y):
        if not self._bound:
            return None  # nothing to move on an empty tile
        value = GObject.Value(TileMove, TileMove(self.key))
        return Gdk.ContentProvider.new_for_value(value)

    def _handle_drag_begin(self, source, _drag) -> None:
        paintable = self._picture.get_paintable()
        if paintable is not None:
            source.set_icon(paintable, TILE_SIZE // 2, TILE_SIZE // 2)

    # -- drop target ------------------------------------------------------

    def _install_drop_target(self) -> None:
        target = Gtk.DropTarget.new(ActionItem, Gdk.DragAction.COPY | Gdk.DragAction.MOVE)
        target.set_gtypes([ActionItem, TileMove, Gdk.FileList])
        target.connect("drop", self._handle_drop)
        target.connect("enter", self._handle_enter)
        target.connect("motion", self._handle_enter)
        target.connect("leave", self._handle_leave)
        self.add_controller(target)

    def _preferred_action(self, target) -> Gdk.DragAction:
        # One action: COPY for a file drag (don't let the source delete it) or a
        # library drag; MOVE for a tile-to-tile drag.
        drop = target.get_current_drop()
        if drop is None:
            return Gdk.DragAction.COPY
        if drop.get_formats().contain_gtype(Gdk.FileList):
            return Gdk.DragAction.COPY
        offered = drop.get_actions()
        if offered & Gdk.DragAction.MOVE:
            return Gdk.DragAction.MOVE
        return Gdk.DragAction.COPY

    def _handle_drop(self, _target, value, _x, _y) -> bool:
        self.remove_css_class("drop-hover")
        if isinstance(value, ActionItem):
            self._on_drop(self.key, value)
            return True
        if isinstance(value, TileMove):
            if value.source_key != self.key:
                self._on_move(value.source_key, self.key)
            return True
        if isinstance(value, Gdk.FileList):
            files = value.get_files()
            if files:
                self._on_file_drop(self.key, files[0])
            return True
        return False

    def _handle_enter(self, target, _x, _y) -> Gdk.DragAction:
        self.add_css_class("drop-hover")
        return self._preferred_action(target)

    def _handle_leave(self, _target) -> None:
        self.remove_css_class("drop-hover")

    # -- state ------------------------------------------------------------

    def set_button(self, button: ButtonConfig | None) -> None:
        if button is None or button.is_empty:
            self.set_empty()
            return
        self._bound = True
        self.add_css_class("bound")
        self._picture.set_paintable(render_preview_texture(button))
        self._stack.set_visible_child_name("image")

    def set_empty(self) -> None:
        self._bound = False
        self.remove_css_class("bound")
        self._stack.set_visible_child_name("empty")

    def set_selected(self, selected: bool) -> None:
        if selected:
            self.add_css_class("selected")
        else:
            self.remove_css_class("selected")
