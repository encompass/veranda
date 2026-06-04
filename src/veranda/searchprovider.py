"""GNOME Shell global search provider.

Type a profile name into the Activities overview and Veranda's profiles show up
as results; activating one switches the connected deck to that profile. This
implements ``org.gnome.Shell.SearchProvider2`` on the application's own bus
connection, registered with the Shell by a provider ``.ini`` that
``autostart.ensure_search_provider()`` installs.
"""

from __future__ import annotations

import logging

from gi.repository import Gio, GLib

from veranda import APP_ID

log = logging.getLogger(__name__)

IFACE = "org.gnome.Shell.SearchProvider2"
SUBPATH = "/SearchProvider"

_XML = """
<node>
 <interface name="org.gnome.Shell.SearchProvider2">
  <method name="GetInitialResultSet">
   <arg type="as" name="terms" direction="in"/>
   <arg type="as" name="results" direction="out"/>
  </method>
  <method name="GetSubsearchResultSet">
   <arg type="as" name="previous_results" direction="in"/>
   <arg type="as" name="terms" direction="in"/>
   <arg type="as" name="results" direction="out"/>
  </method>
  <method name="GetResultMetas">
   <arg type="as" name="identifiers" direction="in"/>
   <arg type="aa{sv}" name="metas" direction="out"/>
  </method>
  <method name="ActivateResult">
   <arg type="s" name="identifier" direction="in"/>
   <arg type="as" name="terms" direction="in"/>
   <arg type="u" name="timestamp" direction="in"/>
  </method>
  <method name="LaunchSearch">
   <arg type="as" name="terms" direction="in"/>
   <arg type="u" name="timestamp" direction="in"/>
  </method>
 </interface>
</node>
"""


class VerandaSearchProvider:
    """Exposes the connected deck's profiles to GNOME Shell search."""

    def __init__(self, window) -> None:
        self._window = window
        self._conn: Gio.DBusConnection | None = None
        self._reg = 0
        self._iface = Gio.DBusNodeInfo.new_for_xml(_XML).interfaces[0]

    def register(self) -> None:
        app = self._window.get_application()
        conn = app.get_dbus_connection() if app is not None else None
        base = app.get_dbus_object_path() if app is not None else None
        if conn is None or base is None:
            return  # no session-bus name (e.g. tests)
        self._conn = conn
        try:
            self._reg = conn.register_object(
                base + SUBPATH, self._iface, self._on_method, None, None
            )
            log.info("search provider registered at %s", base + SUBPATH)
        except GLib.Error as exc:
            log.warning("could not export search provider: %s", exc)

    def unregister(self) -> None:
        if self._conn is not None and self._reg:
            self._conn.unregister_object(self._reg)
        self._reg = 0

    # -- result computation (pure; unit-tested) ---------------------------

    def _match(self, terms: list[str]) -> list[str]:
        """Profile indices (as strings) whose name matches every search term."""
        words = [t.casefold() for t in terms if t]
        results = []
        for idx, name in enumerate(self._window.profile_names()):
            folded = name.casefold()
            if all(w in folded for w in words):
                results.append(str(idx))
        return results

    def _metas(self, ids: list[str]) -> list[dict]:
        names = self._window.profile_names()
        active = self._active_index()
        metas = []
        for ident in ids:
            try:
                idx = int(ident)
                name = names[idx]
            except (ValueError, IndexError):
                continue
            meta = {
                "id": GLib.Variant("s", ident),
                "name": GLib.Variant("s", name),
                "gicon": GLib.Variant("s", APP_ID),
            }
            if idx == active:
                meta["description"] = GLib.Variant("s", "Current profile")
            metas.append(meta)
        return metas

    def _activate(self, ident: str) -> None:
        try:
            idx = int(ident)
        except ValueError:
            return
        self._window.switch_profile(idx)
        self._window.present()

    def _active_index(self) -> int:
        state = self._window.current_state()
        return int(state.active_profile) if state is not None else -1

    # -- method dispatch --------------------------------------------------

    def _on_method(self, _conn, _sender, _path, _iface, method, params, invocation):
        if method == "GetInitialResultSet":
            (terms,) = params.unpack()
            invocation.return_value(GLib.Variant("(as)", (self._match(terms),)))
        elif method == "GetSubsearchResultSet":
            _previous, terms = params.unpack()
            invocation.return_value(GLib.Variant("(as)", (self._match(terms),)))
        elif method == "GetResultMetas":
            (ids,) = params.unpack()
            metas = self._metas(ids)
            invocation.return_value(
                GLib.Variant("(aa{sv})", (metas,))
            )
        elif method == "ActivateResult":
            ident, _terms, _ts = params.unpack()
            self._activate(ident)
            invocation.return_value(None)
        elif method == "LaunchSearch":
            self._window.present()
            invocation.return_value(None)
        else:
            invocation.return_value(None)
