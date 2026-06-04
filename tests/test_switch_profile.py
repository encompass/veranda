"""Switch Profile action and its registry/serialization wiring."""

from veranda.actions.deck_control import SwitchProfileAction
from veranda.actions.registry import action_from_dict, get_action_class, ACTION_CATALOG


def test_in_catalog_and_resolvable():
    assert SwitchProfileAction in ACTION_CATALOG
    assert get_action_class("switch_profile") is SwitchProfileAction


def test_roundtrip_and_summary():
    a = SwitchProfileAction({"profile": "Gaming"})
    b = action_from_dict(a.to_dict())
    assert isinstance(b, SwitchProfileAction)
    assert b.profile == "Gaming"
    assert "Gaming" in b.summary()
    assert b.default_label() == "Gaming"
    # empty config is handled gracefully
    assert SwitchProfileAction().summary() == "Pick a profile"
    assert SwitchProfileAction().default_label() == "Profile"


def test_execute_calls_context(fake_ctx):
    SwitchProfileAction({"profile": "Music"}).execute(fake_ctx)
    assert fake_ctx.switched_profiles == ["Music"]
    assert fake_ctx.notes == []


def test_execute_unconfigured_notifies(fake_ctx):
    SwitchProfileAction().execute(fake_ctx)
    assert fake_ctx.switched_profiles == []
    assert any("No profile" in n for n in fake_ctx.notes)


def test_execute_unknown_profile_notifies():
    from veranda.actions.base import ActionContext

    notes = []
    ctx = ActionContext(
        serial="X", key=0, deck_manager=None, input_backend=None,
        switch_page=lambda *a: None,
        switch_profile=lambda *a: False,  # no match
        set_brightness=lambda *a: None,
        notify=notes.append,
    )
    SwitchProfileAction({"profile": "Ghost"}).execute(ctx)
    assert any("Ghost" in n for n in notes)
