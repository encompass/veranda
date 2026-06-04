"""Manage Veranda's desktop entries.

- A regular application entry in ``~/.local/share/applications`` so the app is
  launchable from the grid and by the GNOME Shell extension (launch-on-demand).
- An optional autostart entry in ``~/.config/autostart`` (the "Open at login"
  setting). The file's presence is the single source of truth.
"""

from __future__ import annotations

import logging
import os
import sys
from pathlib import Path

from veranda import APP_ID

log = logging.getLogger(__name__)

DESKTOP_NAME = f"{APP_ID}.desktop"


def launch_command() -> str:
    """The command used to launch the app (current interpreter + module)."""
    return f"{sys.executable} -m veranda"


def _desktop_contents(autostart: bool) -> str:
    extra = "X-GNOME-Autostart-enabled=true\n" if autostart else ""
    return (
        "[Desktop Entry]\n"
        "Type=Application\n"
        "Name=Veranda\n"
        "GenericName=Stream Deck Manager\n"
        "Comment=Manage your Elgato Stream Deck\n"
        f"Exec={launch_command()}\n"
        f"Icon={APP_ID}\n"
        "Terminal=false\n"
        "Categories=Utility;GTK;\n"
        "Keywords=Stream Deck;Elgato;macro;shortcut;hotkey;\n"
        "StartupNotify=true\n"
        + extra
    )


def ensure_icon() -> None:
    """Install the app icon into the user icon theme (so .desktop/About show it)."""
    from importlib import resources

    dest = _data_home() / "icons" / "hicolor" / "scalable" / "apps" / f"{APP_ID}.svg"
    try:
        dest.parent.mkdir(parents=True, exist_ok=True)
        dest.write_bytes(resources.files("veranda").joinpath("icon.svg").read_bytes())
    except (OSError, FileNotFoundError) as exc:
        log.debug("icon install failed: %s", exc)


def _config_home() -> Path:
    return Path(os.environ.get("XDG_CONFIG_HOME") or os.path.expanduser("~/.config"))


def _data_home() -> Path:
    return Path(os.environ.get("XDG_DATA_HOME") or os.path.expanduser("~/.local/share"))


# -- application entry (always installed) --------------------------------

def applications_file() -> Path:
    return _data_home() / "applications" / DESKTOP_NAME


def ensure_app_desktop_entry() -> None:
    """Write the launchable application entry (idempotent; keeps Exec current)."""
    path = applications_file()
    try:
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(_desktop_contents(autostart=False))
    except OSError as exc:
        log.debug("could not write application desktop entry: %s", exc)


# -- autostart entry (toggled by the "Open at login" setting) ------------

def autostart_file() -> Path:
    return _config_home() / "autostart" / DESKTOP_NAME


def is_enabled() -> bool:
    return autostart_file().exists()


def set_enabled(enabled: bool) -> None:
    path = autostart_file()
    if enabled:
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(_desktop_contents(autostart=True))
        log.info("autostart enabled at %s", path)
    else:
        try:
            path.unlink()
            log.info("autostart disabled (%s removed)", path)
        except FileNotFoundError:
            pass
