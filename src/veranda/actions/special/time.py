"""Time-related Special Buttons: Clock and Date."""

from __future__ import annotations

from datetime import datetime
from typing import Callable

from veranda import launch
from veranda.actions.base import ActionContext
from veranda.actions.special.widget import LiveWidget


class ClockWidget(LiveWidget):
    TYPE_ID = "clock"
    NAME = "Clock"
    DESCRIPTION = "Current time; opens GNOME Clocks"
    ICON = "alarm-symbolic"
    REFRESH_INTERVAL = 30

    @property
    def _24h(self) -> bool:
        return bool(self.params.get("format24", True))

    def display_text(self) -> str:
        return datetime.now().strftime("%H:%M" if self._24h else "%-I:%M")

    def summary(self) -> str:
        return "24-hour clock" if self._24h else "12-hour clock"

    def build_editor_rows(self, button, on_change: Callable[[], None]):
        from gi.repository import Adw

        row = Adw.SwitchRow(title="24-hour time")
        row.set_active(self._24h)

        def toggled(r, _p):
            self.params["format24"] = r.get_active()
            on_change()

        row.connect("notify::active", toggled)
        return [row]

    def execute(self, ctx: ActionContext) -> None:
        if not launch.open_app("org.gnome.clocks"):
            launch.run(["gnome-clocks"])


class DateWidget(LiveWidget):
    TYPE_ID = "date"
    NAME = "Date"
    DESCRIPTION = "Today's date; opens GNOME Calendar"
    ICON = "x-office-calendar-symbolic"
    REFRESH_INTERVAL = 60

    @property
    def _mode(self) -> str:
        return self.params.get("mode", "day")  # "day" | "weekday"

    def display_text(self) -> str:
        now = datetime.now()
        return now.strftime("%a") if self._mode == "weekday" else str(now.day)

    def summary(self) -> str:
        return "Weekday" if self._mode == "weekday" else "Day of month"

    def build_editor_rows(self, button, on_change: Callable[[], None]):
        from gi.repository import Adw, Gtk

        row = Adw.ComboRow(title="Show")
        labels = Gtk.StringList()
        for text in ("Day of month", "Weekday"):
            labels.append(text)
        row.set_model(labels)
        row.set_selected(1 if self._mode == "weekday" else 0)

        def changed(r, _p):
            self.params["mode"] = "weekday" if r.get_selected() == 1 else "day"
            on_change()

        row.connect("notify::selected", changed)
        return [row]

    def execute(self, ctx: ActionContext) -> None:
        if not launch.open_app("org.gnome.Calendar"):
            launch.run(["gnome-calendar"])
