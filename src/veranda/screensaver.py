"""Watch the GNOME screensaver / lock state over D-Bus.

GNOME Shell owns ``org.gnome.ScreenSaver`` on the session bus and emits
``ActiveChanged(bool)`` when the session locks or the screensaver engages
(true) and when it unlocks (false). D-Bus signals are delivered on the GLib
main context, so the callback runs on the GTK main thread.
"""

from __future__ import annotations

import logging
from typing import Callable

from gi.repository import Gio, GLib

log = logging.getLogger(__name__)


class ScreensaverMonitor:
    """Reports lock/unlock transitions via ``on_change(active: bool)``."""

    def __init__(self, on_change: Callable[[bool], None]) -> None:
        self._on_change = on_change
        self._proxy: Gio.DBusProxy | None = None
        self._handler_id = 0
        self._active = False

    @property
    def available(self) -> bool:
        return self._proxy is not None

    @property
    def active(self) -> bool:
        return self._active

    def start(self) -> None:
        try:
            self._proxy = Gio.DBusProxy.new_for_bus_sync(
                Gio.BusType.SESSION,
                Gio.DBusProxyFlags.DO_NOT_AUTO_START
                | Gio.DBusProxyFlags.DO_NOT_LOAD_PROPERTIES,
                None,
                "org.gnome.ScreenSaver",
                "/org/gnome/ScreenSaver",
                "org.gnome.ScreenSaver",
                None,
            )
        except GLib.Error as exc:
            log.info("screensaver monitor unavailable: %s", exc)
            self._proxy = None
            return

        # Without a name owner, signals never arrive — treat as unavailable.
        if self._proxy.get_name_owner() is None:
            log.info("org.gnome.ScreenSaver has no owner; lock sync disabled")
            self._proxy = None
            return

        self._handler_id = self._proxy.connect("g-signal", self._on_g_signal)
        try:
            result = self._proxy.call_sync(
                "GetActive", None, Gio.DBusCallFlags.NONE, -1, None
            )
            self._active = bool(result.unpack()[0])
        except GLib.Error as exc:
            log.debug("GetActive failed: %s", exc)
            self._active = False

    def _on_g_signal(self, _proxy, _sender, signal_name, params) -> None:
        if signal_name != "ActiveChanged":
            return
        try:
            active = bool(params.unpack()[0])
        except (IndexError, TypeError):
            return
        if active != self._active:
            self._active = active
            self._on_change(active)

    def stop(self) -> None:
        if self._proxy is not None and self._handler_id:
            self._proxy.disconnect(self._handler_id)
        self._handler_id = 0
        self._proxy = None
