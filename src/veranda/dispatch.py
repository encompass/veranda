"""Resolve a physical key press to its bound action and execute it."""

from __future__ import annotations

import logging
from typing import Callable

from veranda.actions import ActionContext
from veranda.config import AppConfig
from veranda.deck import DeckManager
from veranda.input_backend import InputBackend

log = logging.getLogger(__name__)


class Dispatcher:
    """Maps key presses on the active page to action execution.

    Runs entirely on the GTK main thread (the DeckManager marshals presses
    here via GLib.idle_add), so actions may safely touch app state.
    """

    def __init__(
        self,
        config: AppConfig,
        deck_manager: DeckManager,
        input_backend: InputBackend,
        switch_page: Callable[[str, int], None],
        set_brightness: Callable[[str, int], None],
        notify: Callable[[str], None],
    ) -> None:
        self._config = config
        self._deck_manager = deck_manager
        self._input_backend = input_backend
        self._switch_page = switch_page
        self._set_brightness = set_brightness
        self._notify = notify

    def dispatch(self, serial: str, key: int) -> None:
        state = self._config.decks.get(serial)
        if state is None:
            return
        button = state.current_page().buttons.get(key)
        if button is None or button.action is None:
            return
        ctx = ActionContext(
            serial=serial,
            key=key,
            deck_manager=self._deck_manager,
            input_backend=self._input_backend,
            switch_page=self._switch_page,
            set_brightness=self._set_brightness,
            notify=self._notify,
        )
        try:
            button.action.execute(ctx)
        except Exception as exc:  # noqa: BLE001 - never let an action crash the loop
            log.exception("action execution failed")
            self._notify(f"Action failed: {exc}")
