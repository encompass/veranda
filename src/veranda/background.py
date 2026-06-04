"""Request to keep running in the background via the desktop portal.

On GNOME this makes the app appear under the system menu's "Background Apps"
section in the top-right. Best-effort: failures (no portal, denied) are
logged and ignored.
"""

from __future__ import annotations

import logging

from gi.repository import Gio, GLib

log = logging.getLogger(__name__)

PORTAL = "org.freedesktop.portal.Desktop"
PORTAL_PATH = "/org/freedesktop/portal/desktop"
BACKGROUND_IFACE = "org.freedesktop.portal.Background"


def request_background(reason: str = "Keep managing your Stream Deck") -> None:
    """Ask the portal to allow background running (fire-and-forget)."""
    try:
        conn = Gio.bus_get_sync(Gio.BusType.SESSION, None)
    except GLib.Error as exc:
        log.debug("no session bus for background request: %s", exc)
        return

    options = {
        "reason": GLib.Variant("s", reason),
        "autostart": GLib.Variant("b", False),
    }

    def done(c, result):
        try:
            c.call_finish(result)
        except GLib.Error as exc:
            log.debug("background request failed: %s", exc)

    try:
        conn.call(
            PORTAL, PORTAL_PATH, BACKGROUND_IFACE, "RequestBackground",
            GLib.Variant("(sa{sv})", ("", options)),
            None, Gio.DBusCallFlags.NONE, -1, None, done,
        )
    except GLib.Error as exc:
        log.debug("could not call RequestBackground: %s", exc)
