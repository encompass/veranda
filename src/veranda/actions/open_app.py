"""Launch an installed application chosen from the app list."""

from __future__ import annotations

import logging
from typing import Callable

from veranda import launch
from veranda.actions.base import Action, ActionContext

log = logging.getLogger(__name__)


class OpenAppAction(Action):
    TYPE_ID = "open_app"
    NAME = "Open App"
    DESCRIPTION = "Launch an installed application"
    ICON = "view-app-grid-symbolic"
    CATEGORY = "System"

    @property
    def desktop_id(self) -> str:
        return self.params.get("desktop_id", "")

    def default_label(self) -> str:
        return ""

    def default_icon(self) -> str:
        return self.params.get("icon") or self.ICON

    def summary(self) -> str:
        return self.params.get("name") or "No app chosen"

    def apply_choice(self, button, desktop_id: str, name: str, icon: str) -> None:
        prev_label = self.params.get("_autolabel")
        prev_icon = self.params.get("_autoicon")
        self.params.update(desktop_id=desktop_id, name=name, icon=icon)
        if button.label in ("", self.NAME) or button.label == prev_label:
            button.label = name
        if button.icon in ("", self.ICON) or button.icon == prev_icon:
            button.icon = icon
        self.params["_autolabel"] = name
        self.params["_autoicon"] = icon

    def build_editor_rows(self, button, on_change: Callable[[], None]):
        from gi.repository import Adw, GLib, Gtk

        from veranda.apppicker import AppPicker

        row = Adw.ActionRow(title="Application", subtitle=GLib.markup_escape_text(self.summary()))
        choose = Gtk.Button(label="Choose…", valign=Gtk.Align.CENTER)
        row.add_suffix(choose)
        row.set_activatable_widget(choose)

        def on_pick(desktop_id: str, name: str, icon: str) -> None:
            self.apply_choice(button, desktop_id, name, icon)
            row.set_subtitle(GLib.markup_escape_text(self.summary()))
            on_change()

        choose.connect("clicked", lambda _b: AppPicker(on_pick).present(row.get_root()))
        return [row]

    def execute(self, ctx: ActionContext) -> None:
        if not self.desktop_id:
            return
        if not launch.open_app(self.desktop_id):
            ctx.notify(f"Couldn't launch {self.params.get('name') or self.desktop_id}")
