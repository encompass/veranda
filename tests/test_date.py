"""Date Special Button: calendar icon with the day number overlaid."""

from datetime import datetime

from veranda import render
from veranda.actions.registry import action_from_dict
from veranda.actions.special.time import DateWidget
from veranda.editor import ButtonEditor
from veranda.models import ButtonConfig


def test_overlays_day_number():
    w = DateWidget()
    assert w.overlay_text() == str(datetime.now().day)
    # No bottom label — the number is drawn over the icon instead.
    assert w.display_text() is None
    assert w.display_icon() == "x-office-calendar-symbolic"


def test_no_options():
    w = DateWidget()
    assert w.build_editor_rows(ButtonConfig(), lambda: None) == []
    assert w.summary() == "Today's date"
    assert w.EDIT_LABEL is False and w.EDIT_ICON is False
    # 'mode'/weekday is gone.
    assert "mode" not in w.params


def test_roundtrip():
    w2 = action_from_dict(DateWidget().to_dict())
    assert isinstance(w2, DateWidget)
    assert w2.overlay_text() == str(datetime.now().day)


def test_renders_with_overlay():
    img = render._compose((96, 96), ButtonConfig(action=DateWidget()))
    assert img.size == (96, 96)
    # Something is drawn (the day number / calendar), so it differs from a
    # blank background tile of the same size.
    blank = render._compose((96, 96), ButtonConfig())
    assert img.tobytes() != blank.tobytes()


def test_editor_hides_label_icon_for_date():
    ed = ButtonEditor(0, ButtonConfig(action=DateWidget()), lambda: None, lambda: None)
    assert ed._label_row is None
    assert ed._icon_row is None
    # Background editing is still available.
    assert ed._bg_row is not None


def test_editor_shows_label_icon_for_normal_action():
    from veranda.actions.run_command import RunCommandAction

    ed = ButtonEditor(0, ButtonConfig(action=RunCommandAction()), lambda: None, lambda: None)
    assert ed._label_row is not None
    assert ed._icon_row is not None
