"""Config persistence and profile import/export."""

import json

from veranda import transfer
from veranda.config import AppConfig, config_path
from veranda.models import ButtonConfig, Page, Profile
from veranda.actions.run_command import RunCommandAction


def test_config_save_load_roundtrip():
    cfg = AppConfig()
    st = cfg.deck("SER", "Stream Deck Mini")
    st.current_page().buttons[0] = ButtonConfig(label="A", action=RunCommandAction({"command": "true"}))
    cfg.settings.run_in_background = True
    cfg.save()
    assert config_path().exists()

    reloaded = AppConfig.load()
    assert reloaded.settings.run_in_background is True
    b = reloaded.deck("SER").current_page().buttons[0]
    assert b.action.params["command"] == "true"


def test_config_load_missing_is_empty():
    cfg = AppConfig.load()
    assert cfg.decks == {}


def test_config_atomic_version():
    cfg = AppConfig()
    cfg.deck("S")
    cfg.save()
    raw = json.loads(config_path().read_text())
    assert raw["version"] == 2 and "settings" in raw and "decks" in raw


def test_transfer_roundtrip(tmp_path):
    prof = Profile(name="Stream", pages=[Page(name="P1")])
    prof.pages[0].buttons[0] = ButtonConfig(label="Go", action=RunCommandAction({"command": "echo hi"}))
    path = tmp_path / "p.veranda.json"
    transfer.export_profile(prof, path)
    loaded = transfer.import_profile(path)
    assert loaded.name == "Stream"
    assert loaded.pages[0].buttons[0].action.params["command"] == "echo hi"


def test_transfer_rejects_bad(tmp_path):
    bad = tmp_path / "bad.json"
    bad.write_text('{"nope": 1}')
    import pytest

    with pytest.raises(ValueError):
        transfer.import_profile(bad)
