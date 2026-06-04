"""Actions that control the Stream Deck itself."""

from __future__ import annotations

from typing import Callable

from veranda.actions.base import Action, ActionContext


class SwitchPageAction(Action):
    TYPE_ID = "switch_page"
    NAME = "Switch Page"
    DESCRIPTION = "Jump to another page of buttons"
    ICON = "view-paged-symbolic"
    CATEGORY = "Deck"

    @property
    def page(self) -> int:
        try:
            return int(self.params.get("page", 0))
        except (TypeError, ValueError):
            return 0

    def default_label(self) -> str:
        return ""

    def summary(self) -> str:
        return f"Go to page {self.page + 1}"

    def build_editor_rows(self, on_change: Callable[[], None]):
        from gi.repository import Adw, Gtk

        row = Adw.SpinRow(
            title="Target page",
            subtitle="1-based page number",
            adjustment=Gtk.Adjustment(lower=1, upper=64, step_increment=1, value=self.page + 1),
        )

        def changed(spin, _pspec):
            self.params["page"] = int(spin.get_value()) - 1
            on_change()

        row.connect("notify::value", changed)
        return [row]

    def execute(self, ctx: ActionContext) -> None:
        ctx.switch_page(ctx.serial, self.page)


class BrightnessAction(Action):
    TYPE_ID = "brightness"
    NAME = "Brightness"
    DESCRIPTION = "Raise, lower, or set screen brightness"
    ICON = "display-brightness-symbolic"
    CATEGORY = "Deck"

    MODES = [("up", "Increase"), ("down", "Decrease"), ("set", "Set to value")]

    @property
    def mode(self) -> str:
        return self.params.get("mode", "up")

    @property
    def amount(self) -> int:
        try:
            return int(self.params.get("amount", 10))
        except (TypeError, ValueError):
            return 10

    def default_label(self) -> str:
        return ""

    def summary(self) -> str:
        if self.mode == "set":
            return f"Set brightness to {self.amount}%"
        sign = "+" if self.mode == "up" else "−"
        return f"Brightness {sign}{self.amount}%"

    def build_editor_rows(self, on_change: Callable[[], None]):
        from gi.repository import Adw, Gtk

        mode_row = Adw.ComboRow(title="Mode")
        labels = Gtk.StringList()
        for _, label in self.MODES:
            labels.append(label)
        mode_row.set_model(labels)
        mode_ids = [m for m, _ in self.MODES]
        mode_row.set_selected(mode_ids.index(self.mode) if self.mode in mode_ids else 0)

        amount_row = Adw.SpinRow(
            title="Amount",
            subtitle="Percent (step or target depending on mode)",
            adjustment=Gtk.Adjustment(lower=1, upper=100, step_increment=5, value=self.amount),
        )

        def mode_changed(row, _param):
            self.params["mode"] = mode_ids[row.get_selected()]
            on_change()

        def amount_changed(spin, _pspec):
            self.params["amount"] = int(spin.get_value())
            on_change()

        mode_row.connect("notify::selected", mode_changed)
        amount_row.connect("notify::value", amount_changed)
        return [mode_row, amount_row]

    def execute(self, ctx: ActionContext) -> None:
        current = ctx.deck_manager.get_brightness(ctx.serial)
        if self.mode == "set":
            new = self.amount
        elif self.mode == "down":
            new = current - self.amount
        else:
            new = current + self.amount
        new = max(0, min(100, new))
        ctx.set_brightness(ctx.serial, new)  # changes the device and persists it
        ctx.notify(f"Brightness {new}%")
