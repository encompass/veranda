"""LiveButtonController scheduling and teardown."""

from veranda.livebuttons import LiveButtonController
from veranda.models import ButtonConfig, Page
from veranda.actions.special.time import ClockWidget, DateWidget
from veranda.actions.special.system import BatteryWidget
from veranda.actions.run_command import RunCommandAction


def test_controller_schedules_polled_only():
    painted = []
    ctrl = LiveButtonController(painted.append)
    page = Page(buttons={
        0: ButtonConfig(action=ClockWidget()),      # polled (interval 30)
        1: ButtonConfig(action=DateWidget()),        # polled (interval 60)
        2: ButtonConfig(action=BatteryWidget()),     # event-driven (no timer)
        3: ButtonConfig(action=RunCommandAction()),  # not dynamic
        4: ButtonConfig(label="static"),
    })
    ctrl.rebuild(page)
    assert len(ctrl._timeouts) == 2          # clock + date
    assert {0, 1}.issubset(set(painted))     # both did an initial paint
    ctrl.stop()
    assert ctrl._timeouts == [] and ctrl._subscribed == []


def test_controller_honors_custom_interval():
    ctrl = LiveButtonController(lambda k: None)
    page = Page(buttons={0: ButtonConfig(action=ClockWidget({"interval": 5}))})
    assert page.buttons[0].action.refresh_interval() == 5
    ctrl.rebuild(page)
    assert len(ctrl._timeouts) == 1
    ctrl.stop()


def test_widget_interval_min_clamp():
    from veranda.actions.special.connectivity import UpdatesWidget
    w = UpdatesWidget()
    w.set_refresh_interval(10)
    assert w.refresh_interval() == 300  # MIN_INTERVAL
    assert not BatteryWidget().supports_interval()
    assert ClockWidget().supports_interval()
