"""Whole-configuration backup and restore (transfer.export_config/import_config)."""

import json

import pytest

from veranda import transfer
from veranda.config import AppConfig
from veranda.models import AppSettings, ButtonConfig, DeckState, Page, Profile


def _sample_config() -> AppConfig:
    deck = DeckState(
        serial="ABC123",
        deck_type="Stream Deck Mini",
        name="Studio Deck",
        brightness=70,
        profiles=[
            Profile(name="Default", pages=[Page(buttons={0: ButtonConfig(label="Hi")})]),
            Profile(name="Gaming", pages=[Page()]),
        ],
        active_profile=1,
    )
    settings = AppSettings(auto_switch=True, app_profiles={"firefox.desktop": "Gaming"})
    return AppConfig(decks={"ABC123": deck}, settings=settings)


def test_config_roundtrip(tmp_path):
    cfg = _sample_config()
    path = tmp_path / "veranda-backup.json"
    transfer.export_config(cfg, path)

    decks, settings = transfer.import_config(path)
    assert set(decks) == {"ABC123"}
    deck = decks["ABC123"]
    assert deck.name == "Studio Deck"
    assert deck.brightness == 70
    assert deck.active_profile == 1
    assert [p.name for p in deck.profiles] == ["Default", "Gaming"]
    assert deck.profiles[0].pages[0].buttons[0].label == "Hi"
    assert settings.auto_switch is True
    assert settings.app_profiles == {"firefox.desktop": "Gaming"}


def test_backup_file_has_version_markers(tmp_path):
    path = tmp_path / "b.json"
    transfer.export_config(_sample_config(), path)
    raw = json.loads(path.read_text())
    assert raw["veranda_backup_version"] == transfer.BACKUP_VERSION
    assert "config_version" in raw
    assert "decks" in raw and "settings" in raw


def test_import_rejects_non_backup(tmp_path):
    path = tmp_path / "bad.json"
    path.write_text(json.dumps({"hello": "world"}))
    with pytest.raises(ValueError):
        transfer.import_config(path)


def test_import_tolerates_empty_settings(tmp_path):
    path = tmp_path / "min.json"
    path.write_text(json.dumps({"decks": {}}))
    decks, settings = transfer.import_config(path)
    assert decks == {}
    assert isinstance(settings, AppSettings)
