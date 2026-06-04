"""Shared pytest fixtures: headless GTK/Adw init and isolated config."""

import gi

gi.require_version("Gtk", "4.0")
gi.require_version("Adw", "1")
from gi.repository import Adw, Gtk  # noqa: E402

import pytest  # noqa: E402

Gtk.init()
Adw.init()


@pytest.fixture(autouse=True)
def isolate_config(tmp_path, monkeypatch):
    """Each test gets its own XDG config/data dirs."""
    monkeypatch.setenv("XDG_CONFIG_HOME", str(tmp_path / "config"))
    monkeypatch.setenv("XDG_DATA_HOME", str(tmp_path / "data"))
    yield


@pytest.fixture
def fake_ctx():
    """An ActionContext with recording stubs (no hardware/input)."""
    from veranda.actions.base import ActionContext

    notes = []
    switched = []
    ctx = ActionContext(
        serial="TEST",
        key=0,
        deck_manager=None,
        input_backend=None,
        switch_page=lambda *a: None,
        switch_profile=lambda serial, target: (switched.append(target) or True),
        set_brightness=lambda *a: None,
        notify=notes.append,
    )
    ctx.notes = notes  # type: ignore[attr-defined]
    ctx.switched_profiles = switched  # type: ignore[attr-defined]
    return ctx
