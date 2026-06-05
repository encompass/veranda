"""Virtual device: model fields, VirtualDeck interface, DeckManager hooks."""

from gi.repository import GLib

import veranda.deck as deckmod
from veranda.deck import DeckManager
from veranda.models import ButtonConfig, DeckState
from veranda.virtualdeck import VirtualDeck


def test_deckstate_virtual_roundtrip():
    s = DeckState(serial="virtual-1", name="VDeck", virtual=True,
                  grid_rows=2, grid_cols=3, window={"x": 10, "y": 20, "on_top": True})
    s2 = DeckState.from_dict("virtual-1", s.to_dict())
    assert s2.virtual is True
    assert (s2.grid_rows, s2.grid_cols) == (2, 3)
    assert s2.window == {"x": 10, "y": 20, "on_top": True}


def test_real_deck_omits_virtual_keys():
    d = DeckState(serial="ABC", deck_type="Stream Deck Mini").to_dict()
    assert "virtual" not in d and "window" not in d and "grid_rows" not in d


def test_virtualdeck_interface():
    v = VirtualDeck("virtual-1", 2, 3, name="X")
    assert v.is_virtual is True
    assert v.key_layout() == (2, 3)
    assert v.key_count() == 6
    assert v.get_serial_number() == "virtual-1"
    assert v.id() == "virtual:virtual-1"
    assert "2×3" in v.deck_type()
    with v:  # context manager works
        pass


def test_fire_routes_to_callback():
    v = VirtualDeck("virtual-1", 1, 1)
    seen = []
    v.set_key_callback(lambda deck, key, state: seen.append((key, state)))
    v.fire(0)
    assert seen == [(0, True)]


def test_deckmanager_registers_virtual():
    dm = DeckManager(on_key_press=lambda s, k: None, on_decks_changed=lambda: None)
    dm.add_virtual_deck(VirtualDeck("virtual-1", 2, 2))
    assert "virtual-1" in dm.serials()
    info = dm.info("virtual-1")
    assert info is not None
    assert (info.rows, info.cols, info.key_count) == (2, 2, 4)


def test_set_key_takes_virtual_branch(monkeypatch):
    dm = DeckManager(lambda s, k: None, lambda: None)
    v = VirtualDeck("virtual-1", 1, 1)
    calls = []
    monkeypatch.setattr(v, "render_key", lambda key, button: calls.append(key))
    # A real deck here would call render_native (which needs key_image_format);
    # the virtual branch must call render_key instead and not raise.
    dm._set_key(v, 0, ButtonConfig(label="x"))
    assert calls == [0]


def test_scan_does_not_drop_virtual(monkeypatch):
    dm = DeckManager(lambda s, k: None, lambda: None)
    dm.add_virtual_deck(VirtualDeck("virtual-1", 1, 1))

    class FakeDeviceManager:
        def enumerate(self):
            return []

    monkeypatch.setattr(deckmod, "DeviceManager", FakeDeviceManager)
    dm._scan()
    assert "virtual-1" in dm.serials()  # survived the hotplug scan


def test_remove_virtual_deck():
    dm = DeckManager(lambda s, k: None, lambda: None)
    dm.add_virtual_deck(VirtualDeck("virtual-1", 1, 1))
    dm.remove_virtual_deck("virtual-1")
    assert "virtual-1" not in dm.serials()
    assert dm.info("virtual-1") is None


def test_manager_geometry_and_report_moved():
    from veranda.config import AppConfig
    from veranda.virtualdeck import VirtualDeckManager

    cfg = AppConfig(decks={"virtual-1": DeckState(
        serial="virtual-1", virtual=True, grid_rows=1, grid_cols=1, name="V",
        window={"x": 10, "y": 20, "on_top": True})})
    mgr = VirtualDeckManager(None, None, cfg, refresh=lambda: None,
                             open_settings=lambda s: None, windows_changed=lambda: None)

    title = "Veranda Virtual Deck — V"

    class FakeWin:
        def get_title(self):
            return title

    class FakeDeck:
        window = FakeWin()

    mgr._decks["virtual-1"] = FakeDeck()

    assert mgr.window_geometry() == [(title, 10, 20, True)]

    mgr.report_moved(title, 50, 60)
    assert cfg.decks["virtual-1"].window["x"] == 50
    assert cfg.decks["virtual-1"].window["y"] == 60
    assert cfg.decks["virtual-1"].window["on_top"] is True  # preserved


def test_manager_set_background_persists_and_applies():
    from veranda.config import AppConfig
    from veranda.virtualdeck import VirtualDeckManager

    cfg = AppConfig(decks={"virtual-1": DeckState(
        serial="virtual-1", virtual=True, grid_rows=1, grid_cols=1, window={})})
    mgr = VirtualDeckManager(None, None, cfg, refresh=lambda: None,
                             open_settings=lambda s: None, windows_changed=lambda: None)
    applied = []

    class FakeWin:
        def set_background(self, c):
            applied.append(c)

    class FakeDeck:
        window = FakeWin()

    mgr._decks["virtual-1"] = FakeDeck()
    mgr.set_background("virtual-1", "#abcdef")
    assert cfg.decks["virtual-1"].window["bg"] == "#abcdef"
    assert applied == ["#abcdef"]


def test_press_dispatches_through_manager():
    presses = []
    dm = DeckManager(on_key_press=lambda s, k: presses.append((s, k)),
                     on_decks_changed=lambda: None)
    v = VirtualDeck("virtual-1", 1, 1)
    dm.add_virtual_deck(v)
    v.fire(0)  # _key_callback marshals via GLib.idle_add
    loop = GLib.MainLoop()
    GLib.timeout_add(50, loop.quit)
    loop.run()
    assert ("virtual-1", 0) in presses
