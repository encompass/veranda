"""Editor dialog for a Multi-Action's list of steps."""

from __future__ import annotations

from typing import Callable

import gi

gi.require_version("Gtk", "4.0")
gi.require_version("Adw", "1")
from gi.repository import Adw, GLib, Gtk  # noqa: E402

from veranda.actions.registry import action_from_dict, get_action_class  # noqa: E402
from veranda.models import ButtonConfig  # noqa: E402

# Action types that make sense inside a macro (no nested macros / live widgets).
MACRO_TYPES = [
    "run_command", "open_app", "open_url", "open_folder",
    "hotkey", "type_text", "copy_text", "gnome_shortcut", "delay",
]


class MacroEditor(Adw.Dialog):
    def __init__(self, action, on_done: Callable[[], None]) -> None:
        super().__init__()
        self._action = action
        self._on_done = on_done
        self.set_title("Edit Macro")
        self.set_content_width(480)
        self.set_content_height(560)
        self.connect("closed", lambda _d: self._on_done())

        toolbar = Adw.ToolbarView()
        header = Adw.HeaderBar()
        add = Gtk.MenuButton(icon_name="list-add-symbolic", tooltip_text="Add a step")
        add.set_popover(self._type_popover())
        header.pack_end(add)
        toolbar.add_top_bar(header)

        page = Adw.PreferencesPage()
        self._group = Adw.PreferencesGroup(
            title="Steps", description="Run top to bottom when the key is pressed."
        )
        page.add(self._group)
        toolbar.set_content(page)
        self.set_child(toolbar)

        self._rows: list = []
        self._rebuild()

    def _steps(self) -> list:
        return self._action.params.setdefault("steps", [])

    def _type_popover(self) -> Gtk.Popover:
        popover = Gtk.Popover()
        box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=0)
        box.add_css_class("menu")
        for type_id in MACRO_TYPES:
            cls = get_action_class(type_id)
            if cls is None:
                continue
            button = Gtk.Button()
            button.add_css_class("flat")
            button.set_child(Gtk.Label(label=cls.NAME, xalign=0.0))
            button.connect("clicked", lambda _b, t=type_id: (popover.popdown(), self._add_step(t)))
            box.append(button)
        popover.set_child(box)
        return popover

    def _add_step(self, type_id: str) -> None:
        cls = get_action_class(type_id)
        if cls is None:
            return
        self._steps().append(cls().to_dict())
        self._rebuild()
        self._edit_step(len(self._steps()) - 1)

    def _rebuild(self) -> None:
        for row in self._rows:
            self._group.remove(row)
        self._rows.clear()
        steps = self._steps()
        if not steps:
            row = Adw.ActionRow(title="No steps yet", subtitle="Use + to add an action")
            self._group.add(row)
            self._rows.append(row)
            return
        for i, data in enumerate(steps):
            action = action_from_dict(data)
            name = action.NAME if action is not None else data.get("type", "?")
            summary = action.summary() if action is not None else ""
            row = Adw.ActionRow(
                title=f"{i + 1}. {GLib.markup_escape_text(name)}",
                subtitle=GLib.markup_escape_text(summary),
            )
            row.set_activatable(True)
            row.connect("activated", lambda _r, idx=i: self._edit_step(idx))
            up = self._mini("go-up-symbolic", lambda _b, idx=i: self._move(idx, -1))
            up.set_sensitive(i > 0)
            down = self._mini("go-down-symbolic", lambda _b, idx=i: self._move(idx, 1))
            down.set_sensitive(i < len(steps) - 1)
            remove = self._mini("user-trash-symbolic", lambda _b, idx=i: self._remove(idx))
            row.add_suffix(up)
            row.add_suffix(down)
            row.add_suffix(remove)
            self._group.add(row)
            self._rows.append(row)

    def _mini(self, icon: str, cb) -> Gtk.Button:
        button = Gtk.Button(icon_name=icon, valign=Gtk.Align.CENTER)
        button.add_css_class("flat")
        button.connect("clicked", cb)
        return button

    def _move(self, index: int, delta: int) -> None:
        steps = self._steps()
        other = index + delta
        if 0 <= other < len(steps):
            steps[index], steps[other] = steps[other], steps[index]
            self._rebuild()

    def _remove(self, index: int) -> None:
        steps = self._steps()
        if 0 <= index < len(steps):
            del steps[index]
            self._rebuild()

    def _edit_step(self, index: int) -> None:
        steps = self._steps()
        if not (0 <= index < len(steps)):
            return
        action = action_from_dict(steps[index])
        if action is None:
            return

        def save() -> None:
            current = self._steps()
            if 0 <= index < len(current):
                current[index] = action.to_dict()
                self._rebuild()

        _StepConfig(action, save).present(self)


class _StepConfig(Adw.Dialog):
    """A small dialog hosting one step action's own editor rows."""

    def __init__(self, action, on_done: Callable[[], None]) -> None:
        super().__init__()
        self.set_title(action.NAME)
        self.set_content_width(420)
        self.connect("closed", lambda _d: on_done())

        toolbar = Adw.ToolbarView()
        toolbar.add_top_bar(Adw.HeaderBar())
        page = Adw.PreferencesPage()
        group = Adw.PreferencesGroup(title=action.NAME, description=action.DESCRIPTION)
        for row in action.build_editor_rows(ButtonConfig(), lambda: None):
            group.add(row)
        page.add(group)
        toolbar.set_content(page)
        self.set_child(toolbar)
