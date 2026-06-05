"""Media Control action (App Control category)."""

from veranda.actions.media_control import MediaControlAction
from veranda.actions.registry import (
    ACTION_CATALOG,
    action_from_dict,
    get_action_class,
    iter_categories,
)
from veranda.models import ButtonConfig


def test_in_catalog_under_app_control():
    assert MediaControlAction in ACTION_CATALOG
    assert get_action_class("media_control") is MediaControlAction
    assert MediaControlAction.CATEGORY == "App Control"
    cats = dict(iter_categories())
    assert "App Control" in cats
    assert MediaControlAction in cats["App Control"]


def test_default_command_and_icon():
    a = MediaControlAction()
    assert a.command == "playpause"
    assert a.default_icon() == "media-playback-start-symbolic"
    assert a.default_label() == ""
    assert a.summary() == "Play / Pause"


def test_each_command_has_icon_and_summary():
    for cmd, (label, method, icon) in MediaControlAction.COMMANDS.items():
        a = MediaControlAction({"command": cmd})
        assert a.default_icon() == icon
        assert a.summary() == label
        assert method  # an MPRIS method name


def test_unknown_command_falls_back():
    assert MediaControlAction({"command": "bogus"}).command == "playpause"


def test_roundtrip():
    a = MediaControlAction({"command": "next"})
    b = action_from_dict(a.to_dict())
    assert isinstance(b, MediaControlAction)
    assert b.command == "next"
    assert b.default_icon() == "media-skip-forward-symbolic"


def test_editor_updates_icon_on_command_change():
    a = MediaControlAction()
    button = ButtonConfig()
    rows = a.build_editor_rows(button, lambda: None)
    assert len(rows) == 1
    combo = rows[0]
    # Select "Next" (index 3 in ORDER) and confirm the tile icon tracks it.
    combo.set_selected(MediaControlAction.ORDER.index("next"))
    assert a.command == "next"
    assert button.icon == "media-skip-forward-symbolic"


def test_execute_without_player_notifies(fake_ctx, monkeypatch):
    # Force "no player" regardless of what's running on the session bus.
    monkeypatch.setattr(
        "veranda.actions.media_control._active_player", lambda _conn: None
    )
    MediaControlAction().execute(fake_ctx)
    assert any("media player" in n.lower() for n in fake_ctx.notes)
