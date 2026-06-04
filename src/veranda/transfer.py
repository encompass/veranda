"""Import and export profiles (button sets) as shareable JSON files."""

from __future__ import annotations

import json
from pathlib import Path

from veranda.config import CONFIG_VERSION
from veranda.models import AppSettings, DeckState, Profile

TRANSFER_VERSION = 1
BACKUP_VERSION = 1


def export_profile(profile: Profile, path: str | Path) -> None:
    """Write a single profile to ``path`` as a Veranda profile file."""
    data = {
        "veranda_profile_version": TRANSFER_VERSION,
        "profile": profile.to_dict(),
    }
    Path(path).write_text(json.dumps(data, indent=2))


def import_profile(path: str | Path) -> Profile:
    """Read a profile file written by :func:`export_profile`.

    Also tolerates a bare profile dict (``{"name": ..., "pages": [...]}``).
    Raises ValueError if the file isn't a recognizable profile.
    """
    raw = json.loads(Path(path).read_text())
    if not isinstance(raw, dict):
        raise ValueError("Not a Veranda profile file")
    payload = raw.get("profile", raw)
    if "pages" not in payload:
        raise ValueError("File does not contain a profile")
    return Profile.from_dict(payload)


def export_config(config, path: str | Path) -> None:
    """Write the entire configuration (all decks + settings) to ``path``."""
    data = {
        "veranda_backup_version": BACKUP_VERSION,
        "config_version": CONFIG_VERSION,
        "settings": config.settings.to_dict(),
        "decks": {serial: deck.to_dict() for serial, deck in config.decks.items()},
    }
    Path(path).write_text(json.dumps(data, indent=2))


def import_config(path: str | Path):
    """Read a backup written by :func:`export_config`.

    Returns ``(decks, settings)`` ready to install into an ``AppConfig``.
    Raises ValueError if the file isn't a recognizable Veranda backup.
    """
    raw = json.loads(Path(path).read_text())
    if not isinstance(raw, dict) or "decks" not in raw:
        raise ValueError("Not a Veranda backup file")
    decks = {
        serial: DeckState.from_dict(serial, data)
        for serial, data in (raw.get("decks") or {}).items()
    }
    settings = AppSettings.from_dict(raw.get("settings"))
    return decks, settings
