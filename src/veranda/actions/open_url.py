"""Open a URL or file with the system default handler."""

from __future__ import annotations

import logging
import subprocess
from typing import Callable

from veranda.actions.base import Action, ActionContext

log = logging.getLogger(__name__)


class OpenUrlAction(Action):
    TYPE_ID = "open_url"
    NAME = "Open URL / File"
    DESCRIPTION = "Open a link or file with xdg-open"
    ICON = "web-browser-symbolic"
    CATEGORY = "System"

    @property
    def target(self) -> str:
        return self.params.get("target", "")

    def default_label(self) -> str:
        return ""

    def summary(self) -> str:
        return self.target or "No URL set"

    def build_editor_rows(self, button, on_change: Callable[[], None]):
        from gi.repository import Adw

        row = Adw.EntryRow(title="URL or file path")
        row.set_text(self.target)

        def changed(entry):
            self.params["target"] = entry.get_text()
            on_change()

        row.connect("changed", changed)
        return [row]

    def execute(self, ctx: ActionContext) -> None:
        target = self.target.strip()
        if not target:
            return
        try:
            subprocess.Popen(
                ["xdg-open", target],
                stdin=subprocess.DEVNULL,
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
                start_new_session=True,
            )
        except OSError as exc:
            log.warning("open_url failed: %s", exc)
            ctx.notify(f"Could not open: {exc}")
