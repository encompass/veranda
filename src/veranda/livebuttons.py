"""Drives periodic/event refresh of Special Buttons on the active page."""

from __future__ import annotations

import logging
from typing import Callable

from gi.repository import GLib

from veranda import render

log = logging.getLogger(__name__)

ANIM_INTERVAL_MS = 66  # ~15 fps for animated GIF keys


class LiveButtonController:
    """Owns the refresh timers/subscriptions for the current page's widgets.

    ``repaint(key)`` is supplied by the window and repaints one key on both the
    on-screen grid and the hardware (the window decides whether the deck is
    lock-dimmed). Rebuild on every page/profile/device change; stop on shutdown.
    """

    def __init__(self, repaint: Callable[[int], None]) -> None:
        self._repaint = repaint
        self._timeouts: list[int] = []
        self._subscribed: list = []  # widgets we must unsubscribe()

    def rebuild(self, page) -> None:
        self.stop()
        if page is None:
            return
        for key, button in page.buttons.items():
            if render.is_animated_icon(button.icon):
                self._timeouts.append(
                    GLib.timeout_add(ANIM_INTERVAL_MS, self._anim_cb(key))
                )
            action = button.action
            if action is None or not getattr(action, "DYNAMIC", False):
                continue
            action.set_update_callback(self._repaint_cb(key))
            try:
                if action.subscribe():
                    self._subscribed.append(action)
                else:
                    action.refresh()
            except Exception:  # noqa: BLE001
                log.exception("live widget init failed for key %s", key)
            getter = getattr(action, "refresh_interval", None)
            interval = int(getter() or 0) if callable(getter) else int(
                getattr(action, "REFRESH_INTERVAL", 0) or 0
            )
            if interval > 0:
                self._timeouts.append(
                    GLib.timeout_add_seconds(interval, self._tick_cb(action))
                )

    def repaint_all(self, page) -> None:
        """Force a repaint of every live key (e.g. after the deck wakes)."""
        if page is None:
            return
        for key, button in page.buttons.items():
            if button.action is not None and getattr(button.action, "DYNAMIC", False):
                self._repaint(key)

    def stop(self) -> None:
        for sid in self._timeouts:
            GLib.source_remove(sid)
        self._timeouts.clear()
        for action in self._subscribed:
            try:
                action.unsubscribe()
            except Exception:  # noqa: BLE001
                pass
        self._subscribed.clear()

    # -- closures (avoid late-binding loop captures) ----------------------

    def _repaint_cb(self, key: int) -> Callable[[], None]:
        return lambda: self._repaint(key)

    def _anim_cb(self, key: int) -> Callable[[], bool]:
        def tick() -> bool:
            self._repaint(key)
            return True

        return tick

    def _tick_cb(self, action) -> Callable[[], bool]:
        def tick() -> bool:
            try:
                action.refresh()
            except Exception:  # noqa: BLE001
                log.exception("live widget refresh failed")
            return True  # keep ticking; stop() removes the source

        return tick
