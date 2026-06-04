"""CLI control-option handling (veranda --switch-profile, --brightness, ...)."""

from types import SimpleNamespace

from gi.repository import GLib

from veranda import cli


def _opts(**kv) -> GLib.VariantDict:
    d = GLib.VariantDict.new(None)
    for key, value in kv.items():
        if isinstance(value, bool):
            d.insert_value(key, GLib.Variant("b", True))
        elif isinstance(value, int):
            d.insert_value(key, GLib.Variant("i", value))
        else:
            d.insert_value(key, GLib.Variant("s", value))
    return d


class FakeWindow:
    def __init__(self, profiles=("Default", "Gaming"), active=0, connected=True):
        self._profiles = list(profiles)
        self._active = active
        self._connected = connected
        self.brightness = 50
        self.calls = []

    def profile_names(self):
        return list(self._profiles)

    def switch_profile(self, idx):
        self._active = idx
        self.calls.append(("switch", idx))

    def set_brightness(self, pct):
        self.brightness = pct
        self.calls.append(("brightness", pct))

    def toggle_window(self):
        self.calls.append(("toggle",))

    def present(self):
        self.calls.append(("show",))

    def set_visible(self, value):
        self.calls.append(("hide", value))

    def real_quit(self):
        self.calls.append(("quit",))

    def deck_info(self):
        return object() if self._connected else None

    def current_state(self):
        if not self._profiles:
            return None
        return SimpleNamespace(
            display_name="Stream Deck Mini",
            brightness=self.brightness,
            active_profile=self._active,
            profiles=[SimpleNamespace(name=n) for n in self._profiles],
        )


def _run(window, **kv):
    out, err = [], []
    status = cli.handle(window, _opts(**kv), out.append, err.append)
    return status, "".join(out), "".join(err)


def test_has_control_options():
    assert cli.has_control_options(_opts(status=True)) is True
    assert cli.has_control_options(_opts()) is False
    # an unrelated option (e.g. GApplication's own) is not a control option
    assert cli.has_control_options(_opts(somethingelse=True)) is False


def test_list_profiles():
    status, out, err = _run(FakeWindow(), **{"list-profiles": True})
    assert status == 0
    assert "0: Default" in out and "1: Gaming" in out


def test_list_profiles_no_device():
    status, out, err = _run(FakeWindow(profiles=()), **{"list-profiles": True})
    assert status == 1
    assert "No Stream Deck" in err


def test_switch_profile_by_name_case_insensitive():
    w = FakeWindow()
    status, out, err = _run(w, **{"switch-profile": "gaming"})
    assert status == 0
    assert ("switch", 1) in w.calls
    assert "Switched to profile 1: Gaming" in out


def test_switch_profile_by_index():
    w = FakeWindow()
    status, out, err = _run(w, **{"switch-profile": "1"})
    assert status == 0
    assert ("switch", 1) in w.calls


def test_switch_profile_next_wraps():
    w = FakeWindow(profiles=("A", "B", "C"), active=2)
    status, out, err = _run(w, **{"switch-profile": "next"})
    assert status == 0
    assert ("switch", 0) in w.calls  # wraps past the end


def test_switch_profile_previous():
    w = FakeWindow(profiles=("A", "B", "C"), active=0)
    status, out, err = _run(w, **{"switch-profile": "previous"})
    assert status == 0
    assert ("switch", 2) in w.calls  # wraps before the start


def test_switch_profile_unknown():
    w = FakeWindow()
    status, out, err = _run(w, **{"switch-profile": "Nope"})
    assert status == 1
    assert "No such profile: Nope" in err
    assert not any(c[0] == "switch" for c in w.calls)


def test_brightness_clamped():
    w = FakeWindow()
    status, out, err = _run(w, brightness=250)
    assert status == 0
    assert ("brightness", 100) in w.calls
    assert "100%" in out


def test_status_text():
    status, out, err = _run(FakeWindow(active=1), status=True)
    assert status == 0
    assert "Stream Deck Mini" in out
    assert "1: Gaming" in out
    assert "Connected:  yes" in out


def test_window_controls():
    w = FakeWindow()
    _run(w, toggle=True)
    _run(w, show=True)
    _run(w, hide=True)
    _run(w, quit=True)
    kinds = [c[0] for c in w.calls]
    assert kinds == ["toggle", "show", "hide", "quit"]
