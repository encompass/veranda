"""A small D-Bus control interface for the GNOME Shell extension to drive.

Exported on the application's own bus connection (well-known name
``com.encompass.Veranda``) so the Shell extension can show/hide/quit the app,
switch profiles, set brightness, and read status — all natively from the Quick
Settings panel.
"""

from __future__ import annotations

import logging

from gi.repository import Gio, GLib

log = logging.getLogger(__name__)

IFACE = "com.encompass.Veranda.Control"

_XML = """
<node>
 <interface name="com.encompass.Veranda.Control">
  <method name="Show"/>
  <method name="Hide"/>
  <method name="ToggleVisible"/>
  <method name="Quit"/>
  <method name="SetActiveProfile"><arg type="u" name="index" direction="in"/></method>
  <method name="SetBrightness"><arg type="i" name="percent" direction="in"/></method>
  <method name="SetFocusedApp"><arg type="s" name="desktop_id" direction="in"/></method>
  <method name="GetState"><arg type="a{sv}" name="state" direction="out"/></method>
  <method name="GetVirtualWindows"><arg type="a(siib)" name="windows" direction="out"/></method>
  <method name="ReportVirtualWindowMoved">
   <arg type="s" name="title" direction="in"/>
   <arg type="i" name="x" direction="in"/>
   <arg type="i" name="y" direction="in"/>
  </method>
  <signal name="StateChanged"/>
 </interface>
</node>
"""


class VerandaDBusService:
    """Bridges the running window to the ``com.encompass.Veranda.Control`` API."""

    def __init__(self, window) -> None:
        self._window = window
        self._conn: Gio.DBusConnection | None = None
        self._path: str | None = None
        self._reg = 0
        self._iface = Gio.DBusNodeInfo.new_for_xml(_XML).interfaces[0]

    def register(self) -> None:
        app = self._window.get_application()
        conn = app.get_dbus_connection() if app is not None else None
        path = app.get_dbus_object_path() if app is not None else None
        if conn is None or path is None:
            return  # running without a session-bus name (e.g. tests)
        self._conn = conn
        self._path = path
        try:
            self._reg = conn.register_object(path, self._iface, self._on_method, None, None)
            log.info("control interface registered at %s", path)
        except GLib.Error as exc:
            log.warning("could not export control interface: %s", exc)

    def unregister(self) -> None:
        if self._conn is not None and self._reg:
            self._conn.unregister_object(self._reg)
        self._reg = 0

    def notify_changed(self) -> None:
        if self._conn is None or self._path is None:
            return
        try:
            self._conn.emit_signal(None, self._path, IFACE, "StateChanged", None)
        except GLib.Error as exc:
            log.debug("emit StateChanged failed: %s", exc)

    # -- method dispatch --------------------------------------------------

    def _on_method(self, _conn, _sender, _path, _iface, method, params, invocation):
        w = self._window
        if method == "Show":
            w.present()
            invocation.return_value(None)
        elif method == "Hide":
            w.set_visible(False)
            invocation.return_value(None)
        elif method == "ToggleVisible":
            w.toggle_window()
            invocation.return_value(None)
        elif method == "SetActiveProfile":
            (index,) = params.unpack()
            w.switch_profile(int(index))
            invocation.return_value(None)
        elif method == "SetBrightness":
            (percent,) = params.unpack()
            w.set_brightness(int(percent))
            invocation.return_value(None)
        elif method == "SetFocusedApp":
            (desktop_id,) = params.unpack()
            w.set_focused_app(desktop_id)
            invocation.return_value(None)
        elif method == "GetState":
            invocation.return_value(GLib.Variant("(a{sv})", (self._state(),)))
        elif method == "GetVirtualWindows":
            wins = list(w.virtual_window_geometry())
            invocation.return_value(GLib.Variant("(a(siib))", (wins,)))
        elif method == "ReportVirtualWindowMoved":
            title, x, y = params.unpack()
            w.report_virtual_window_moved(title, int(x), int(y))
            invocation.return_value(None)
        elif method == "Quit":
            invocation.return_value(None)
            w.real_quit()
        else:
            invocation.return_value(None)

    def _state(self) -> dict:
        w = self._window
        state = w.current_state()
        visible = GLib.Variant("b", bool(w.get_visible()))
        if state is None:
            return {
                "connected": GLib.Variant("b", False),
                "device_name": GLib.Variant("s", ""),
                "brightness": GLib.Variant("i", 0),
                "profiles": GLib.Variant("as", []),
                "active_profile": GLib.Variant("u", 0),
                "visible": visible,
            }
        return {
            "connected": GLib.Variant("b", w.deck_info() is not None),
            "device_name": GLib.Variant("s", state.display_name),
            "brightness": GLib.Variant("i", int(state.brightness)),
            "profiles": GLib.Variant("as", [p.name for p in state.profiles]),
            "active_profile": GLib.Variant("u", int(state.active_profile)),
            "visible": visible,
        }
