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
    DESCRIPTION = "Today's date on a calendar; opens GNOME Calendar"
    ICON = "x-office-calendar-symbolic"
    REFRESH_INTERVAL = 60
    EDIT_LABEL = False  # the day number is drawn over the icon
    EDIT_ICON = False   # the calendar icon is fixed

    def display_icon(self) -> str:
        return self.ICON

    def overlay_text(self) -> str:
        return str(datetime.now().day)

    def summary(self) -> str:
        return "Today's date"

    def build_editor_rows(self, button, on_change: Callable[[], None]):
        return []

    def execute(self, ctx: ActionContext) -> None:
        if not launch.open_app("org.gnome.Calendar"):
            launch.run(["gnome-calendar"])
