"""Small helpers for launching apps / settings / URIs from widget presses."""

from __future__ import annotations

import logging
import subprocess

from gi.repository import Gio

log = logging.getLogger(__name__)


def run(argv: list[str]) -> bool:
    try:
        subprocess.Popen(
            argv, stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL, start_new_session=True,
        )
        return True
    except (OSError, ValueError) as exc:
        log.debug("run %s failed: %s", argv, exc)
        return False


def open_app(desktop_id: str) -> bool:
    """Launch an installed app by desktop id (with or without .desktop)."""
    if not desktop_id:
        return False
    if not desktop_id.endswith(".desktop"):
        desktop_id += ".desktop"
    try:
        from gi.repository import GioUnix

        app = GioUnix.DesktopAppInfo.new(desktop_id)
        if app is not None:
            app.launch([], None)
            return True
    except Exception as exc:  # noqa: BLE001
        log.debug("open_app %s failed: %s", desktop_id, exc)
    return False


def open_settings(panel: str = "") -> bool:
    argv = ["gnome-control-center"]
    if panel:
        argv.append(panel)
    return run(argv)


def open_uri(uri: str) -> None:
    try:
        Gio.AppInfo.launch_default_for_uri(uri, None)
    except Exception as exc:  # noqa: BLE001
        log.debug("open_uri %s failed: %s", uri, exc)
