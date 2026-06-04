"""Load and save application config under the XDG config directory."""

from __future__ import annotations

import json
import logging
import os
from pathlib import Path
from typing import Any

from veranda.models import AppSettings, DeckState

log = logging.getLogger(__name__)

CONFIG_VERSION = 2


def config_dir() -> Path:
    base = os.environ.get("XDG_CONFIG_HOME") or os.path.expanduser("~/.config")
    return Path(base) / "veranda"


def config_path() -> Path:
    return config_dir() / "config.json"


class AppConfig:
    """In-memory config plus load/save to ``~/.config/veranda/config.json``."""

    def __init__(
        self,
        decks: dict[str, DeckState] | None = None,
        settings: AppSettings | None = None,
    ) -> None:
        self.decks: dict[str, DeckState] = decks or {}
        self.settings: AppSettings = settings or AppSettings()

    # -- access -----------------------------------------------------------

    def deck(self, serial: str, deck_type: str = "") -> DeckState:
        """Return the state for ``serial``, creating it on first use."""
        state = self.decks.get(serial)
        if state is None:
            state = DeckState(serial=serial, deck_type=deck_type)
            self.decks[serial] = state
        elif deck_type and not state.deck_type:
            state.deck_type = deck_type
        return state

    # -- persistence ------------------------------------------------------

    @classmethod
    def load(cls) -> "AppConfig":
        path = config_path()
        if not path.exists():
            return cls()
        try:
            raw = json.loads(path.read_text())
        except (OSError, json.JSONDecodeError) as exc:
            log.warning("Could not read config (%s); starting fresh", exc)
            return cls()
        raw = _migrate(raw)
        decks = {
            serial: DeckState.from_dict(serial, data)
            for serial, data in (raw.get("decks") or {}).items()
        }
        return cls(decks, AppSettings.from_dict(raw.get("settings")))

    def save(self) -> None:
        path = config_path()
        path.parent.mkdir(parents=True, exist_ok=True)
        data = {
            "version": CONFIG_VERSION,
            "settings": self.settings.to_dict(),
            "decks": {s: d.to_dict() for s, d in self.decks.items()},
        }
        tmp = path.with_suffix(".json.tmp")
        tmp.write_text(json.dumps(data, indent=2))
        os.replace(tmp, path)  # atomic on the same filesystem


def _migrate(raw: dict[str, Any]) -> dict[str, Any]:
    """Bring an older config forward to ``CONFIG_VERSION``."""
    version = raw.get("version", 1)
    # No migrations yet; placeholder for future schema changes.
    if version != CONFIG_VERSION:
        log.info("Config version %s -> %s", version, CONFIG_VERSION)
    return raw
