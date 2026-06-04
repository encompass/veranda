"""Trigger a GNOME keyboard shortcut imported from system settings."""

from __future__ import annotations

import logging
import shlex
import subprocess
from typing import Callable

from veranda.actions.base import Action, ActionContext

log = logging.getLogger(__name__)


class GnomeShortcutAction(Action):
    TYPE_ID = "gnome_shortcut"
    NAME = "GNOME Shortcut"
    DESCRIPTION = "Trigger a GNOME keyboard shortcut"
    ICON = "preferences-desktop-keyboard-symbolic"
    CATEGORY = "GNOME"

    @property
    def kind(self) -> str:
        return self.params.get("kind", "")

    def default_label(self) -> str:
        return self.params.get("label", "")

    def default_icon(self) -> str:
        return self.ICON

    def summary(self) -> str:
        if not self.kind:
            return "No shortcut chosen"
        label = self.params.get("label", "")
        if self.kind == "custom":
            detail = self.params.get("command", "")
        else:
            detail = self.params.get("accel_label", "") or self.params.get("accel", "")
        return f"{label} ({detail})" if detail else label

    def apply_choice(self, button, sc) -> None:
        """Store a picked shortcut and auto-fill the button's label/icon.

        The label/icon are only overwritten when still at defaults or at the
        value this action filled in last time — never clobbering a user edit.
        """
        from veranda import gnome_shortcuts as gs

        icon = gs.category_icon(sc.category)
        prev_label = self.params.get("_autolabel")
        prev_icon = self.params.get("_autoicon")
        self.params.update(
            kind=sc.kind, label=sc.description, accel=sc.accel,
            accel_label=gs.friendly_accel(sc.accel),
            schema=sc.schema, key=sc.key, command=sc.command,
        )
        if button.label in ("", self.NAME) or button.label == prev_label:
            button.label = sc.description
        if button.icon in ("", self.ICON) or button.icon == prev_icon:
            button.icon = icon
        self.params["_autolabel"] = sc.description
        self.params["_autoicon"] = icon

    def build_editor_rows(self, button, on_change: Callable[[], None]):
        from gi.repository import Adw, GLib, Gtk

        from veranda import gnome_shortcuts as gs
        from veranda.shortcutpicker import ShortcutPicker

        row = Adw.ActionRow(title="Shortcut", subtitle=GLib.markup_escape_text(self.summary()))
        choose = Gtk.Button(label="Choose…", valign=Gtk.Align.CENTER)
        row.add_suffix(choose)
        row.set_activatable_widget(choose)

        def on_pick(sc) -> None:
            self.apply_choice(button, sc)
            row.set_subtitle(GLib.markup_escape_text(self.summary()))
            on_change()

        choose.connect(
            "clicked", lambda _b: ShortcutPicker(on_pick).present(row.get_root())
        )
        return [row]

    def execute(self, ctx: ActionContext) -> None:
        if self.kind == "custom":
            cmd = self.params.get("command", "").strip()
            if not cmd:
                return
            try:
                subprocess.Popen(
                    shlex.split(cmd), stdin=subprocess.DEVNULL,
                    stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
                    start_new_session=True,
                )
            except (OSError, ValueError) as exc:
                ctx.notify(f"Shortcut command failed: {exc}")
            return

        if self.kind == "builtin":
            # Re-read the live binding so it follows changes made in Settings.
            from veranda import gnome_shortcuts as gs

            accel = gs.resolve_accel(
                self.params.get("schema", ""), self.params.get("key", "")
            ) or self.params.get("accel", "")
            if not accel:
                ctx.notify("This shortcut has no key binding")
                return
            if not ctx.input_backend.available:
                ctx.notify(ctx.input_backend.unavailable_reason)
                return
            try:
                ctx.input_backend.send_accelerator(accel)
            except Exception as exc:  # noqa: BLE001
                log.warning("gnome_shortcut failed: %s", exc)
                ctx.notify(f"Shortcut failed: {exc}")
