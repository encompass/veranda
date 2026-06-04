"""GNOME Shell search provider: profile matching, metas, activation, install."""

from types import SimpleNamespace

from veranda import APP_ID, autostart
from veranda.searchprovider import VerandaSearchProvider


class FakeWindow:
    def __init__(self, profiles=("Default", "Game Streaming", "Music"), active=0):
        self._profiles = list(profiles)
        self._active = active
        self.calls = []

    def get_application(self):
        return None  # so register() is a no-op (no bus in tests)

    def profile_names(self):
        return list(self._profiles)

    def switch_profile(self, idx):
        self._active = idx
        self.calls.append(("switch", idx))

    def present(self):
        self.calls.append(("present",))

    def current_state(self):
        return SimpleNamespace(active_profile=self._active)


def test_match_substring_and_case_insensitive():
    p = VerandaSearchProvider(FakeWindow())
    assert p._match(["game"]) == ["1"]
    assert p._match(["MUSIC"]) == ["2"]
    # every term must match (AND semantics)
    assert p._match(["game", "stream"]) == ["1"]
    assert p._match(["game", "zzz"]) == []
    # empty terms -> all profiles
    assert p._match([""]) == ["0", "1", "2"]


def test_metas_include_name_and_current_marker():
    p = VerandaSearchProvider(FakeWindow(active=2))
    metas = p._metas(["1", "2", "99"])  # 99 is out of range -> dropped
    assert len(metas) == 2
    by_id = {m["id"].get_string(): m for m in metas}
    assert by_id["1"]["name"].get_string() == "Game Streaming"
    assert "description" not in by_id["1"]
    assert by_id["2"]["description"].get_string() == "Current profile"
    assert by_id["2"]["gicon"].get_string() == APP_ID


def test_activate_switches_and_presents():
    w = FakeWindow()
    p = VerandaSearchProvider(w)
    p._activate("2")
    assert ("switch", 2) in w.calls
    assert ("present",) in w.calls


def test_activate_ignores_garbage():
    w = FakeWindow()
    p = VerandaSearchProvider(w)
    p._activate("not-an-int")
    assert w.calls == []


def test_register_noop_without_bus():
    # get_application() returns None -> register must not raise
    VerandaSearchProvider(FakeWindow()).register()


def test_ensure_search_provider_writes_ini(isolate_config):
    autostart.ensure_search_provider()
    path = autostart.search_provider_file()
    assert path.exists()
    text = path.read_text()
    assert f"BusName={APP_ID}" in text
    assert "ObjectPath=/com/encompass/Veranda/SearchProvider" in text
    assert "Version=2" in text
    assert f"DesktopId={APP_ID}.desktop" in text
