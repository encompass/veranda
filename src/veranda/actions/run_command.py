"""Run an arbitrary shell command."""

from __future__ import annotations

import logging
import shlex
import subprocess
from typing import Callable

from veranda.actions.base import Action, ActionContext

log = logging.getLogger(__name__)


class RunCommandAction(Action):
    TYPE_ID = "run_command"
    NAME = "Run Command"
    DESCRIPTION = "Execute a shell command"
    ICON = "utilities-terminal-symbolic"
    CATEGORY = "System"

    @property
    def command(self) -> str:
        return self.params.get("command", "")

    def default_label(self) -> str:
        return ""

    def summary(self) -> str:
        return self.command or "No command set"

    def build_editor_rows(self, on_change: Callable[[], None]):
        from gi.repository import Adw

        row = Adw.EntryRow(title="Command")
        row.set_text(self.command)

        def changed(entry):
            self.params["command"] = entry.get_text()
            on_change()

        row.connect("changed", changed)
        return [row]

    def execute(self, ctx: ActionContext) -> None:
        cmd = self.command.strip()
        if not cmd:
            return
        try:
            subprocess.Popen(
                shlex.split(cmd),
                stdin=subprocess.DEVNULL,
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
                start_new_session=True,
            )
        except (OSError, ValueError) as exc:
            log.warning("run_command failed: %s", exc)
            ctx.notify(f"Command failed: {exc}")
