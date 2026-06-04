"""Import and export profiles (button sets) as shareable JSON files."""

from __future__ import annotations

import json
from pathlib import Path

from veranda.models import Profile

TRANSFER_VERSION = 1


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
