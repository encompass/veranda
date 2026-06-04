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

    def build_editor_rows(self, button, on_change: Callable[[], None]):
        from gi.repository import Adw, Gtk

        from veranda.actions.validation import attach_validity, command_status

        row = Adw.EntryRow(title="Command")
        row.set_text(self.command)

        run = Gtk.Button(
            icon_name="media-playback-start-symbolic", valign=Gtk.Align.CENTER,
            tooltip_text="Run now to test",
        )
        run.add_css_class("flat")
        run.connect("clicked", lambda _b: self._run_test())
        row.add_suffix(run)
        attach_validity(row, command_status)

        def changed(entry):
            self.params["command"] = entry.get_text()
            on_change()

        row.connect("changed", changed)
        return [row]

    def _run_test(self) -> None:
        cmd = self.command.strip()
        if not cmd:
            return
        try:
            subprocess.Popen(
                shlex.split(cmd), stdin=subprocess.DEVNULL,
                stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
                start_new_session=True,
            )
        except (OSError, ValueError) as exc:
            log.warning("test run failed: %s", exc)

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
