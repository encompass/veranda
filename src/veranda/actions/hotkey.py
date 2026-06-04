"""Send a keyboard shortcut (modifier + key combo)."""

from __future__ import annotations

import logging
from typing import Callable

from veranda.actions.base import Action, ActionContext

log = logging.getLogger(__name__)


class HotkeyAction(Action):
    TYPE_ID = "hotkey"
    NAME = "Hotkey"
    DESCRIPTION = "Send a key combination (e.g. ctrl+shift+t)"
    ICON = "preferences-desktop-keyboard-symbolic"
    CATEGORY = "Input"

    @property
    def combo(self) -> str:
        return self.params.get("combo", "")

    def default_label(self) -> str:
        return self.combo or ""

    def summary(self) -> str:
        return self.combo or "No keys set"

    def build_editor_rows(self, button, on_change: Callable[[], None]):
        from gi.repository import Adw

        row = Adw.EntryRow(title="Key combo")
        row.set_text(self.combo)

        def changed(entry):
            self.params["combo"] = entry.get_text()
            on_change()

        row.connect("changed", changed)

        hint = Adw.ActionRow(
            title="Format",
            subtitle="Modifiers + key joined by '+', e.g. ctrl+alt+t or super+l",
        )
        hint.set_sensitive(False)
        return [row, hint]

    def execute(self, ctx: ActionContext) -> None:
        combo = self.combo.strip()
        if not combo:
            return
        if not ctx.input_backend.available:
            ctx.notify(ctx.input_backend.unavailable_reason)
            return
        try:
            ctx.input_backend.send_combo(combo)
        except Exception as exc:  # noqa: BLE001 - surface any backend failure
            log.warning("hotkey failed: %s", exc)
            ctx.notify(f"Hotkey failed: {exc}")
