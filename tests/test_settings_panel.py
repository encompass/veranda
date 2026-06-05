"""Open Settings Panel action (App Control)."""

from veranda.actions.registry import (
    ACTION_CATALOG,
    action_from_dict,
    get_action_class,
    iter_categories,
)
from veranda.actions.settings_panel import OpenSettingsPanelAction
from veranda.models import ButtonConfig


def test_in_catalog_under_app_control():
    assert OpenSettingsPanelAction in ACTION_CATALOG
    assert get_action_class("open_settings") is OpenSettingsPanelAction
    assert OpenSettingsPanelAction.CATEGORY == "App Control"
    assert OpenSettingsPanelAction in dict(iter_categories())["App Control"]


def test_default_panel():
    a = OpenSettingsPanelAction()
    assert a.panel == "wifi"
    assert a.default_label() == "Wi-Fi"
    assert a.default_icon() == "network-wireless-symbolic"
    assert a.summary() == "Open Wi-Fi"


def test_unknown_panel_falls_back():
    assert OpenSettingsPanelAction({"panel": "bogus"}).panel == "wifi"


def test_roundtrip():
    a = OpenSettingsPanelAction({"panel": "sound"})
    b = action_from_dict(a.to_dict())
    assert isinstance(b, OpenSettingsPanelAction)
    assert b.panel == "sound"
    assert b.summary() == "Open Sound"


def test_editor_updates_icon_and_label():
    a = OpenSettingsPanelAction()
    button = ButtonConfig()
    rows = a.build_editor_rows(button, lambda: None)
    combo = rows[0]
    combo.set_selected(OpenSettingsPanelAction.ORDER.index("bluetooth"))
    assert a.panel == "bluetooth"
    assert button.icon == "bluetooth-symbolic"
    assert button.label == "Bluetooth"


def test_execute_launches(fake_ctx, monkeypatch):
    calls = []
    monkeypatch.setattr(
        "veranda.actions.settings_panel.launch.open_settings",
        lambda panel: calls.append(panel) or True,
    )
    OpenSettingsPanelAction({"panel": "power"}).execute(fake_ctx)
    assert calls == ["power"]
    assert fake_ctx.notes == []
