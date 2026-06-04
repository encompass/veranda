"""The right-hand action library: draggable rows grouped by category."""

from __future__ import annotations

import gi

gi.require_version("Gtk", "4.0")
gi.require_version("Adw", "1")
from gi.repository import Adw, Gdk, GObject, Gtk  # noqa: E402

from veranda.actions import iter_categories  # noqa: E402
from veranda.actions.base import Action  # noqa: E402
from veranda.models import ActionItem  # noqa: E402


class ActionLibrary(Gtk.ScrolledWindow):
    """Scrollable list of action types the user can drag onto a tile."""

    def __init__(self) -> None:
        super().__init__(hexpand=False, vexpand=True)
        self.set_policy(Gtk.PolicyType.NEVER, Gtk.PolicyType.AUTOMATIC)

        box = Gtk.Box(
            orientation=Gtk.Orientation.VERTICAL,
            spacing=18,
            margin_top=12,
            margin_bottom=12,
            margin_start=12,
            margin_end=12,
        )
        for category, action_classes in iter_categories():
            group = Adw.PreferencesGroup(title=category)
            for action_class in action_classes:
                group.add(self._make_row(action_class))
            box.append(group)
        self.set_child(box)

    def _make_row(self, action_class: type[Action]) -> Adw.ActionRow:
        row = Adw.ActionRow(
            title=action_class.NAME,
            subtitle=action_class.DESCRIPTION,
        )
        row.add_css_class("action-row")
        row.add_prefix(Gtk.Image.new_from_icon_name(action_class.ICON))
        handle = Gtk.Image.new_from_icon_name("list-drag-handle-symbolic")
        handle.add_css_class("dim-label")
        row.add_suffix(handle)

        drag = Gtk.DragSource(actions=Gdk.DragAction.COPY)

        def on_prepare(_source, _x, _y):
            item = ActionItem(action_class)
            return Gdk.ContentProvider.new_for_value(GObject.Value(ActionItem, item))

        def on_drag_begin(source, _drag):
            paintable = Gtk.WidgetPaintable.new(row)
            source.set_icon(paintable, row.get_width() // 2, row.get_height() // 2)

        drag.connect("prepare", on_prepare)
        drag.connect("drag-begin", on_drag_begin)
        row.add_controller(drag)
        return row
