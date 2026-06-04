"""Action registry round-trips and execution logic."""

import os

from veranda.actions.registry import ACTION_CATALOG, action_from_dict, iter_categories
from veranda.actions.run_command import RunCommandAction
from veranda.actions.open_app import OpenAppAction
from veranda.actions.extras import CopyTextAction
from veranda.models import ButtonConfig


def test_every_action_roundtrips():
    for cls in ACTION_CATALOG:
        a = cls({})
        a2 = action_from_dict(a.to_dict())
        assert a2 is not None and a2.TYPE_ID == cls.TYPE_ID


def test_categories_present():
    cats = {c for c, _ in iter_categories()}
    assert {"System", "Input", "Deck", "Special Buttons", "GNOME"} <= cats


def test_run_command_executes(fake_ctx, tmp_path):
    marker = tmp_path / "marker"
    RunCommandAction({"command": f"touch {marker}"}).execute(fake_ctx)
    import time
    time.sleep(0.3)
    assert marker.exists()


def test_run_command_empty_is_noop(fake_ctx):
    RunCommandAction({}).execute(fake_ctx)  # no crash


def test_copy_text_notifies(fake_ctx):
    CopyTextAction({"text": "hello"}).execute(fake_ctx)
    assert any("clip" in n.lower() or "copied" in n.lower() for n in fake_ctx.notes)


def test_open_app_autofill_and_launch(fake_ctx):
    a = OpenAppAction()
    b = ButtonConfig(label="Open App", icon="view-app-grid-symbolic", action=a)
    a.apply_choice(b, "org.gnome.Calculator.desktop", "Calculator", "org.gnome.Calculator")
    assert b.label == "Calculator" and b.icon == "org.gnome.Calculator"
    # user edit preserved on re-pick
    b.label = "Mine"
    a.apply_choice(b, "firefox.desktop", "Firefox", "firefox")
    assert b.label == "Mine" and b.icon == "firefox"
    # bogus launch notifies
    OpenAppAction({"desktop_id": "no-such-app.desktop", "name": "Ghost"}).execute(fake_ctx)
    assert fake_ctx.notes


def test_special_buttons_render(fake_ctx):
    from veranda import render
    specials = [c for c in ACTION_CATALOG if getattr(c, "DYNAMIC", False)]
    assert len(specials) >= 10
    for cls in specials:
        render._compose((80, 80), ButtonConfig(icon=cls.ICON, action=cls()))
