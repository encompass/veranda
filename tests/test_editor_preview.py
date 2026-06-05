"""The button editor's live preview."""

from veranda.actions.run_command import RunCommandAction
from veranda.actions.special.time import DateWidget
from veranda.editor import ButtonEditor
from veranda.models import ButtonConfig


def test_preview_present_and_renders():
    ed = ButtonEditor(0, ButtonConfig(label="Hi"), lambda: None, lambda: None)
    assert ed._preview is not None
    assert ed._preview.get_paintable() is not None  # rendered at construction


def test_preview_updates_on_change():
    ed = ButtonEditor(0, ButtonConfig(label="Hi"), lambda: None, lambda: None)
    before = ed._preview.get_paintable()
    ed._button.label = "Changed"
    ed._update_preview()
    assert ed._preview.get_paintable() is not None
    assert ed._preview.get_paintable() is not before  # a fresh texture


def test_preview_for_actions():
    for action in (RunCommandAction(), DateWidget()):
        ed = ButtonEditor(0, ButtonConfig(action=action), lambda: None, lambda: None)
        assert ed._preview.get_paintable() is not None
