"""Type a literal string of text."""

from __future__ import annotations

import logging
from typing import Callable

from veranda.actions.base import Action, ActionContext

log = logging.getLogger(__name__)


class TypeTextAction(Action):
    TYPE_ID = "type_text"
    NAME = "Type Text"
    DESCRIPTION = "Type a string of literal text"
    ICON = "input-keyboard-symbolic"
    CATEGORY = "Input"

    @property
    def text(self) -> str:
        return self.params.get("text", "")

    def default_label(self) -> str:
        return ""

    def summary(self) -> str:
        text = self.text
        return (text[:24] + "…") if len(text) > 25 else (text or "No text set")

    def build_editor_rows(self, on_change: Callable[[], None]):
        from gi.repository import Adw

        row = Adw.EntryRow(title="Text to type")
        row.set_text(self.text)

        def changed(entry):
            self.params["text"] = entry.get_text()
            on_change()

        row.connect("changed", changed)
        return [row]

    def execute(self, ctx: ActionContext) -> None:
        text = self.text
        if not text:
            return
        if not ctx.input_backend.available:
            ctx.notify(ctx.input_backend.unavailable_reason)
            return
        try:
            ctx.input_backend.type_text(text)
        except Exception as exc:  # noqa: BLE001 - surface any backend failure
            log.warning("type_text failed: %s", exc)
            ctx.notify(f"Type text failed: {exc}")
