"""Base class and helpers for live "Special Buttons"."""

from __future__ import annotations

import logging
from typing import Callable

from gi.repository import Gio, GLib

from veranda.actions.base import Action

log = logging.getLogger(__name__)


class LiveWidget(Action):
    """An Action whose display refreshes over time.

    Subclasses set ``REFRESH_INTERVAL`` (seconds, for polled widgets) and/or
    override ``subscribe()`` (for event-driven widgets), implement the
    ``display_*``/``badge_text`` hooks for their appearance, and ``execute()``
    for the press behavior. Whenever their data changes they call
    ``self._emit_update()`` to repaint the key.
    """

    DYNAMIC = True
    CATEGORY = "Special Buttons"
    REFRESH_INTERVAL: int = 0  # seconds; 0 = event-driven (or static)

    def __init__(self, params: dict | None = None) -> None:
        super().__init__(params)
        self._on_update: Callable[[], None] | None = None

    def default_label(self) -> str:
        return ""  # widgets drive their own text via display_text()

    # -- refresh lifecycle (driven by LiveButtonController) ---------------

    def set_update_callback(self, cb: Callable[[], None]) -> None:
        self._on_update = cb

    def _emit_update(self) -> None:
        if self._on_update is not None:
            self._on_update()

    def refresh(self) -> None:
        """Recompute/fetch the latest value, then repaint. Default: repaint."""
        self._emit_update()

    def subscribe(self) -> bool:
        """Set up an event source; return True if subscribed (else polled)."""
        return False

    def unsubscribe(self) -> None:
        pass


def run_async(argv: list[str], on_output: Callable[[str], None]) -> None:
    """Run ``argv`` and hand its stripped stdout to ``on_output`` (non-blocking)."""
    try:
        proc = Gio.Subprocess.new(
            argv,
            Gio.SubprocessFlags.STDOUT_PIPE | Gio.SubprocessFlags.STDERR_SILENCE,
        )
    except GLib.Error as exc:
        log.debug("spawn failed %s: %s", argv, exc)
        return

    def done(p, result):
        try:
            ok, out, _err = p.communicate_utf8_finish(result)
        except GLib.Error as exc:
            log.debug("command failed %s: %s", argv, exc)
            return
        if ok:
            on_output((out or "").strip())

    proc.communicate_utf8_async(None, None, done)
