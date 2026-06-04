"""Media & notification Special Buttons: Now Playing and App Unread badge."""

from __future__ import annotations

import logging
from typing import Callable

from gi.repository import Gio, GLib

from veranda import launch
from veranda.actions.base import ActionContext
from veranda.actions.special.widget import LiveWidget

log = logging.getLogger(__name__)

MPRIS_PREFIX = "org.mpris.MediaPlayer2."


class NowPlayingWidget(LiveWidget):
    TYPE_ID = "now_playing"
    NAME = "Now Playing"
    DESCRIPTION = "Media title + play/pause; press toggles"
    ICON = "multimedia-player-symbolic"

    def __init__(self, params: dict | None = None) -> None:
        super().__init__(params)
        self._conn = None
        self._proxy = None
        self._player = None
        self._watch = 0
        self._sig = 0

    # -- subscription -----------------------------------------------------

    def subscribe(self) -> bool:
        try:
            self._conn = Gio.bus_get_sync(Gio.BusType.SESSION, None)
        except GLib.Error:
            return False
        self._watch = self._conn.signal_subscribe(
            "org.freedesktop.DBus", "org.freedesktop.DBus", "NameOwnerChanged",
            "/org/freedesktop/DBus", None, Gio.DBusSignalFlags.NONE, self._on_name_owner,
        )
        self._pick_player()
        return True

    def unsubscribe(self) -> None:
        if self._conn is not None and self._watch:
            self._conn.signal_unsubscribe(self._watch)
        self._watch = 0
        self._teardown_proxy()
        self._conn = None

    def _on_name_owner(self, _c, _s, _p, _i, _sig, params) -> None:
        if params.unpack()[0].startswith(MPRIS_PREFIX):
            self._pick_player()

    def _pick_player(self) -> None:
        names: list[str] = []
        try:
            res = self._conn.call_sync(
                "org.freedesktop.DBus", "/org/freedesktop/DBus", "org.freedesktop.DBus",
                "ListNames", None, GLib.VariantType.new("(as)"),
                Gio.DBusCallFlags.NONE, -1, None,
            )
            names = [n for n in res.unpack()[0] if n.startswith(MPRIS_PREFIX)]
        except GLib.Error:
            pass
        new = names[0] if names else None
        if new != self._player or self._proxy is None:
            self._teardown_proxy()
            self._player = new
            if new:
                try:
                    self._proxy = Gio.DBusProxy.new_sync(
                        self._conn, Gio.DBusProxyFlags.NONE, None, new,
                        "/org/mpris/MediaPlayer2", "org.mpris.MediaPlayer2.Player", None,
                    )
                    self._sig = self._proxy.connect(
                        "g-properties-changed", lambda *_a: self._emit_update()
                    )
                except GLib.Error:
                    self._proxy = None
        self._emit_update()

    def _teardown_proxy(self) -> None:
        if self._proxy is not None and self._sig:
            try:
                self._proxy.disconnect(self._sig)
            except Exception:  # noqa: BLE001
                pass
        self._sig = 0
        self._proxy = None

    # -- display + press --------------------------------------------------

    def _status(self) -> str | None:
        if self._proxy is None:
            return None
        v = self._proxy.get_cached_property("PlaybackStatus")
        return v.unpack() if v is not None else None

    def display_icon(self) -> str:
        status = self._status()
        if status == "Playing":
            return "media-playback-start-symbolic"
        if status == "Paused":
            return "media-playback-pause-symbolic"
        return "multimedia-player-symbolic"

    def display_text(self) -> str:
        if self._proxy is None:
            return ""
        meta = self._proxy.get_cached_property("Metadata")
        if meta is None:
            return ""
        title = meta.unpack().get("xesam:title") or ""
        return (title[:11] + "…") if len(title) > 12 else title

    def summary(self) -> str:
        return "Controls the active media player"

    def execute(self, ctx: ActionContext) -> None:
        if self._proxy is None:
            return
        try:
            self._proxy.call_sync("PlayPause", None, Gio.DBusCallFlags.NONE, -1, None)
        except GLib.Error as exc:
            ctx.notify(f"Media: {exc}")


# -- App unread badge (Unity LauncherEntry) ------------------------------

class LauncherEntryMonitor:
    """Shared listener for ``com.canonical.Unity.LauncherEntry`` count badges."""

    def __init__(self) -> None:
        self._conn = None
        self._sub = 0
        self._counts: dict[str, int] = {}
        self._listeners: dict[str, set] = {}

    def _ensure(self) -> None:
        if self._conn is not None:
            return
        try:
            self._conn = Gio.bus_get_sync(Gio.BusType.SESSION, None)
        except GLib.Error:
            return
        self._sub = self._conn.signal_subscribe(
            None, "com.canonical.Unity.LauncherEntry", "Update", None, None,
            Gio.DBusSignalFlags.NONE, self._on_update,
        )

    def _on_update(self, _c, _s, _p, _i, _sig, params) -> None:
        try:
            app_uri, props = params.unpack()
        except Exception:  # noqa: BLE001
            return
        count = int(props.get("count", 0))
        visible = bool(props.get("count-visible", False))
        self._counts[app_uri] = count if visible else 0
        for cb in list(self._listeners.get(app_uri, ())):
            cb()

    def register(self, app_uri: str, cb) -> None:
        self._ensure()
        self._listeners.setdefault(app_uri, set()).add(cb)

    def unregister(self, app_uri: str, cb) -> None:
        listeners = self._listeners.get(app_uri)
        if listeners:
            listeners.discard(cb)

    def count(self, app_uri: str) -> int:
        return self._counts.get(app_uri, 0)


_MONITOR: LauncherEntryMonitor | None = None


def _monitor() -> LauncherEntryMonitor:
    global _MONITOR
    if _MONITOR is None:
        _MONITOR = LauncherEntryMonitor()
    return _MONITOR


class AppBadgeWidget(LiveWidget):
    TYPE_ID = "app_badge"
    NAME = "App Unread"
    DESCRIPTION = "Unread/badge count for an app; press launches it"
    ICON = "mail-unread-symbolic"

    @property
    def desktop_id(self) -> str:
        return self.params.get("desktop_id", "")

    @property
    def app_uri(self) -> str:
        return f"application://{self.desktop_id}" if self.desktop_id else ""

    def display_icon(self) -> str:
        return self.params.get("icon") or self.ICON

    def display_text(self) -> str:
        return ""  # icon + badge only

    def badge_text(self) -> str | None:
        if not self.app_uri:
            return None
        count = _monitor().count(self.app_uri)
        return str(count) if count > 0 else None

    def summary(self) -> str:
        return self.params.get("name") or "No app chosen"

    def subscribe(self) -> bool:
        if self.app_uri:
            self._cb = self._emit_update
            _monitor().register(self.app_uri, self._cb)
        self._emit_update()
        return True

    def unsubscribe(self) -> None:
        if self.app_uri and getattr(self, "_cb", None):
            _monitor().unregister(self.app_uri, self._cb)

    def build_editor_rows(self, button, on_change: Callable[[], None]):
        from gi.repository import Adw, Gtk

        from veranda.apppicker import AppPicker

        row = Adw.ActionRow(title="App", subtitle=GLib.markup_escape_text(self.summary()))
        choose = Gtk.Button(label="Choose…", valign=Gtk.Align.CENTER)
        row.add_suffix(choose)
        row.set_activatable_widget(choose)

        def on_pick(desktop_id: str, name: str, icon: str) -> None:
            self.params.update(desktop_id=desktop_id, name=name, icon=icon)
            if button.icon in ("", self.ICON):
                button.icon = icon
            row.set_subtitle(GLib.markup_escape_text(self.summary()))
            on_change()

        choose.connect("clicked", lambda _b: AppPicker(on_pick).present(row.get_root()))
        return [row]

    def execute(self, ctx: ActionContext) -> None:
        if self.desktop_id:
            launch.open_app(self.desktop_id)
