"""App Control action — open GNOME Settings to a specific panel."""

from __future__ import annotations

from typing import Callable

from veranda import launch
from veranda.actions.base import Action, ActionContext


class OpenSettingsPanelAction(Action):
    TYPE_ID = "open_settings"
    NAME = "Open Settings Panel"
    DESCRIPTION = "Jump straight to a GNOME Settings panel"
    ICON = "preferences-system-symbolic"
    CATEGORY = "App Control"

    # panel id -> (label, icon). Unknown ids just open the main Settings window.
    PANELS = {
        "wifi": ("Wi-Fi", "network-wireless-symbolic"),
        "network": ("Network", "network-wired-symbolic"),
        "bluetooth": ("Bluetooth", "bluetooth-symbolic"),
        "sound": ("Sound", "audio-volume-high-symbolic"),
        "power": ("Power", "battery-symbolic"),
        "display": ("Displays", "video-display-symbolic"),
        "background": ("Background", "image-x-generic-symbolic"),
        "appearance": ("Appearance", "applications-graphics-symbolic"),
        "notifications": ("Notifications", "preferences-system-notifications-symbolic"),
        "keyboard": ("Keyboard", "input-keyboard-symbolic"),
        "mouse": ("Mouse & Touchpad", "input-mouse-symbolic"),
        "online-accounts": ("Online Accounts", "system-users-symbolic"),
        "sharing": ("Sharing", "network-server-symbolic"),
        "region": ("Region & Language", "preferences-desktop-locale-symbolic"),
        "universal-access": ("Accessibility", "preferences-desktop-accessibility-symbolic"),
        "applications": ("Apps", "view-app-grid-symbolic"),
        "system": ("System", "preferences-system-symbolic"),
    }
    ORDER = list(PANELS)

    @property
    def panel(self) -> str:
        p = self.params.get("panel", "wifi")
        return p if p in self.PANELS else "wifi"

    def default_icon(self) -> str:
        return self.PANELS[self.panel][1]

    def default_label(self) -> str:
        return self.PANELS[self.panel][0]

    def summary(self) -> str:
        return f"Open {self.PANELS[self.panel][0]}"

    def build_editor_rows(self, button, on_change: Callable[[], None]):
        from gi.repository import Adw, Gtk

        row = Adw.ComboRow(title="Panel")
        labels = Gtk.StringList()
        for pid in self.ORDER:
            labels.append(self.PANELS[pid][0])
        row.set_model(labels)
        row.set_selected(self.ORDER.index(self.panel))

        def changed(combo, _p):
            self.params["panel"] = self.ORDER[combo.get_selected()]
            button.icon = self.default_icon()
            button.label = self.default_label()
            on_change()

        row.connect("notify::selected", changed)
        return [row]

    def execute(self, ctx: ActionContext) -> None:
        if not launch.open_settings(self.panel):
            ctx.notify("Could not open Settings")
