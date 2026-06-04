"""Manage an XDG autostart entry so Veranda can launch on login.

We write/remove ``~/.config/autostart/<app-id>.desktop`` directly — the file's
presence is the single source of truth (no separate persisted flag to drift).
Combined with the "start hidden" + "run in background" settings, this lets
Veranda come up quietly in the background at login.
"""

from __future__ import annotations

import logging
import os
import sys
from pathlib import Path

from veranda import APP_ID

log = logging.getLogger(__name__)

DESKTOP_NAME = f"{APP_ID}.desktop"

_TEMPLATE = """[Desktop Entry]
Type=Application
Name=Veranda
Comment=Manage your Elgato Stream Deck
Exec={exec}
Icon={icon}
Terminal=false
Categories=Utility;
X-GNOME-Autostart-enabled=true
"""


def _autostart_dir() -> Path:
    base = os.environ.get("XDG_CONFIG_HOME") or os.path.expanduser("~/.config")
    return Path(base) / "autostart"


def autostart_file() -> Path:
    return _autostart_dir() / DESKTOP_NAME


def launch_command() -> str:
    """The command the autostart entry runs (current interpreter + module)."""
    return f"{sys.executable} -m veranda"


def is_enabled() -> bool:
    return autostart_file().exists()


def set_enabled(enabled: bool) -> None:
    path = autostart_file()
    if enabled:
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(_TEMPLATE.format(exec=launch_command(), icon=APP_ID))
        log.info("autostart enabled at %s", path)
    else:
        try:
            path.unlink()
            log.info("autostart disabled (%s removed)", path)
        except FileNotFoundError:
            pass
