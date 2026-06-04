"""Model serialization, migration, and helpers."""

from veranda.models import (
    AppSettings,
    ButtonConfig,
    DeckState,
    Page,
    Profile,
)
from veranda.actions.run_command import RunCommandAction


def test_buttonconfig_roundtrip():
    b = ButtonConfig(label="Hi", icon="x-office-calendar-symbolic", font_size=18,
                     background="#3584e4", action=RunCommandAction({"command": "true"}))
    b2 = ButtonConfig.from_dict(b.to_dict())
    assert b2.label == "Hi" and b2.icon == b.icon and b2.font_size == 18
    assert b2.background == "#3584e4"
    assert b2.action is not None and b2.action.TYPE_ID == "run_command"


def test_buttonconfig_is_empty():
    assert ButtonConfig().is_empty
    assert not ButtonConfig(label="x").is_empty
    assert not ButtonConfig(background="accent").is_empty


def test_profile_clone_is_deep():
    p = Profile(name="A", pages=[Page(buttons={0: ButtonConfig(label="x")})])
    c = p.clone("B")
    c.pages[0].buttons[0].label = "changed"
    assert p.pages[0].buttons[0].label == "x"  # original untouched
    assert c.name == "B"


def test_deckstate_legacy_migration():
    legacy = {
        "deck_type": "Stream Deck Mini", "brightness": 50, "active_page": 1,
        "pages": [{"name": "A", "buttons": {}}, {"name": "B", "buttons": {}}],
    }
    st = DeckState.from_dict("S1", legacy)
    assert len(st.profiles) == 1 and st.profiles[0].name == "Default"
    assert len(st.profiles[0].pages) == 2 and st.profiles[0].active_page == 1


def test_deckstate_new_roundtrip():
    st = DeckState(serial="S", deck_type="Mini", name="My Deck", dim_on_lock=True)
    st.profiles.append(Profile(name="Gaming"))
    st2 = DeckState.from_dict("S", st.to_dict())
    assert st2.name == "My Deck" and st2.dim_on_lock is True
    assert [p.name for p in st2.profiles] == ["Default", "Gaming"]
    assert st2.display_name == "My Deck"


def test_appsettings_roundtrip():
    s = AppSettings(run_in_background=True, start_hidden=True, auto_switch=True,
                    app_profiles={"steam.desktop": "Gaming"}, window_width=900)
    s2 = AppSettings.from_dict(s.to_dict())
    assert s2.run_in_background and s2.start_hidden and s2.auto_switch
    assert s2.app_profiles == {"steam.desktop": "Gaming"} and s2.window_width == 900
