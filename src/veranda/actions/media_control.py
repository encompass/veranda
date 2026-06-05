"""App Control actions — Media Control (MPRIS transport)."""

from __future__ import annotations

import logging
from typing import Callable

from gi.repository import Gio, GLib

from veranda.actions.base import Action, ActionContext

log = logging.getLogger(__name__)

MPRIS_PREFIX = "org.mpris.MediaPlayer2."
PLAYER_PATH = "/org/mpris/MediaPlayer2"
PLAYER_IFACE = "org.mpris.MediaPlayer2.Player"


def _active_player(conn) -> str | None:
    """Return the bus name of the MPRIS player to control.

    Prefers a player that is currently ``Playing``; otherwise the first one.
    """
    try:
        res = conn.call_sync(
            "org.freedesktop.DBus", "/org/freedesktop/DBus", "org.freedesktop.DBus",
            "ListNames", None, GLib.VariantType.new("(as)"),
            Gio.DBusCallFlags.NONE, -1, None,
        )
        names = [n for n in res.unpack()[0] if n.startswith(MPRIS_PREFIX)]
    except GLib.Error:
        return None
    if not names:
        return None
    for name in names:
        try:
            status = conn.call_sync(
                name, PLAYER_PATH, "org.freedesktop.DBus.Properties", "Get",
                GLib.Variant("(ss)", (PLAYER_IFACE, "PlaybackStatus")),
                GLib.VariantType.new("(v)"), Gio.DBusCallFlags.NONE, -1, None,
            )
            if status.unpack()[0] == "Playing":
                return name
        except GLib.Error:
            continue
    return names[0]


class MediaControlAction(Action):
    TYPE_ID = "media_control"
    NAME = "Media Control"
    DESCRIPTION = "Control the active media player (play, pause, skip)"
    ICON = "media-playback-start-symbolic"
    CATEGORY = "App Control"

    # command id -> (label, MPRIS method, icon)
    COMMANDS = {
        "playpause": ("Play / Pause", "PlayPause", "media-playback-start-symbolic"),
        "play": ("Play", "Play", "media-playback-start-symbolic"),
        "pause": ("Pause", "Pause", "media-playback-pause-symbolic"),
        "next": ("Next", "Next", "media-skip-forward-symbolic"),
        "previous": ("Previous", "Previous", "media-skip-backward-symbolic"),
        "stop": ("Stop", "Stop", "media-playback-stop-symbolic"),
    }
    ORDER = ["playpause", "play", "pause", "next", "previous", "stop"]

    @property
    def command(self) -> str:
        cmd = self.params.get("command", "playpause")
        return cmd if cmd in self.COMMANDS else "playpause"

    def default_icon(self) -> str:
        return self.COMMANDS[self.command][2]

    def default_label(self) -> str:
        return ""  # media keys read best as just an icon

    def summary(self) -> str:
        return self.COMMANDS[self.command][0]

    def build_editor_rows(self, button, on_change: Callable[[], None]):
        from gi.repository import Adw, Gtk

        row = Adw.ComboRow(title="Command")
        labels = Gtk.StringList()
        for cmd in self.ORDER:
            labels.append(self.COMMANDS[cmd][0])
        row.set_model(labels)
        row.set_selected(self.ORDER.index(self.command))

        def changed(combo, _p):
            self.params["command"] = self.ORDER[combo.get_selected()]
            button.icon = self.default_icon()  # keep the tile icon in step
            on_change()

        row.connect("notify::selected", changed)
        return [row]

    def execute(self, ctx: ActionContext) -> None:
        try:
            conn = Gio.bus_get_sync(Gio.BusType.SESSION, None)
        except GLib.Error:
            ctx.notify("No session bus")
            return
        player = _active_player(conn)
        if player is None:
            ctx.notify("No media player is running")
            return
        method = self.COMMANDS[self.command][1]
        try:
            conn.call_sync(
                player, PLAYER_PATH, PLAYER_IFACE, method, None, None,
                Gio.DBusCallFlags.NONE, -1, None,
            )
        except GLib.Error as exc:
            ctx.notify(f"Media control failed: {exc}")
