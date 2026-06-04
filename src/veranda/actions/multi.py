"""Multi-Action: run a sequence of actions on a single press."""

from __future__ import annotations

import logging
from typing import Callable

from veranda.actions.base import Action, ActionContext

log = logging.getLogger(__name__)


class DelayAction(Action):
    """A pause between macro steps (no-op outside a Multi-Action)."""

    TYPE_ID = "delay"
    NAME = "Delay"
    DESCRIPTION = "Wait before the next step"
    ICON = "alarm-symbolic"
    CATEGORY = "Macros"

    @property
    def ms(self) -> int:
        try:
            return int(self.params.get("ms", 200))
        except (TypeError, ValueError):
            return 200

    def summary(self) -> str:
        return f"Wait {self.ms} ms"

    def build_editor_rows(self, button, on_change: Callable[[], None]):
        from gi.repository import Adw, Gtk

        row = Adw.SpinRow(
            title="Delay",
            subtitle="milliseconds",
            adjustment=Gtk.Adjustment(lower=0, upper=10000, step_increment=50, value=self.ms),
        )
        row.connect(
            "notify::value",
            lambda r, _p: (self.params.__setitem__("ms", int(r.get_value())), on_change()),
        )
        return [row]

    def execute(self, ctx: ActionContext) -> None:
        pass  # the delay is applied by MultiAction between steps


class MultiAction(Action):
    TYPE_ID = "multi"
    NAME = "Multi-Action"
    DESCRIPTION = "Run several actions in sequence"
    ICON = "view-list-ordered-symbolic"
    CATEGORY = "Macros"

    def default_label(self) -> str:
        return ""

    def summary(self) -> str:
        n = len(self.params.get("steps", []))
        return f"{n} step{'s' if n != 1 else ''}" if n else "No steps yet"

    def build_editor_rows(self, button, on_change: Callable[[], None]):
        from gi.repository import Adw, Gtk

        from veranda.macroeditor import MacroEditor

        row = Adw.ActionRow(title="Macro steps", subtitle=self.summary())
        edit = Gtk.Button(label="Edit…", valign=Gtk.Align.CENTER)
        row.add_suffix(edit)
        row.set_activatable_widget(edit)

        def on_done() -> None:
            row.set_subtitle(self.summary())
            on_change()

        edit.connect("clicked", lambda _b: MacroEditor(self, on_done).present(row.get_root()))
        return [row]

    def execute(self, ctx: ActionContext) -> None:
        self._run(ctx, 0)

    def _run(self, ctx: ActionContext, index: int) -> None:
        from gi.repository import GLib

        from veranda.actions.registry import action_from_dict

        steps = self.params.get("steps", [])
        if index >= len(steps):
            return
        action = action_from_dict(steps[index])
        if action is None:
            self._run(ctx, index + 1)
            return
        if action.TYPE_ID == "delay":
            GLib.timeout_add(
                max(0, getattr(action, "ms", 0)),
                lambda: (self._run(ctx, index + 1), False)[-1],
            )
            return
        try:
            action.execute(ctx)
        except Exception as exc:  # noqa: BLE001 - one bad step shouldn't abort the rest
            log.warning("macro step failed: %s", exc)
        self._run(ctx, index + 1)
