#!/usr/bin/env python3
"""Launch a fully-populated Veranda window for screenshots / manual QA.

Backed by a FAKE Stream Deck Mini and an ISOLATED temporary config, so it never
touches your real ~/.config/veranda or your running instance, and never opens
the USB device. Handy for documentation screenshots and eyeballing UI changes
without hardware.

Usage (from the repo root, in the venv):
    .venv/bin/python tools/demo_window.py                 # main editor, page 1
    .venv/bin/python tools/demo_window.py --page 1        # show the 2nd page
    .venv/bin/python tools/demo_window.py --settings backup   # open Settings → Backup
    .venv/bin/python tools/demo_window.py --size 1280x800 --seconds 300

Panes for --settings: general, profiles, automation, device, backup.
The window closes itself after --seconds (default 600); or just kill the process.
"""

from __future__ import annotations

import argparse
import os
import tempfile
from importlib import resources

# --- Isolate config/data BEFORE importing veranda (AppConfig.load reads XDG) ---
_tmp = tempfile.mkdtemp(prefix="veranda-demo-")
os.environ["XDG_CONFIG_HOME"] = os.path.join(_tmp, "config")
os.environ["XDG_DATA_HOME"] = os.path.join(_tmp, "data")

import gi  # noqa: E402

gi.require_version("Gtk", "4.0")
gi.require_version("Adw", "1")
from gi.repository import Adw, Gdk, Gio, GLib, Gtk  # noqa: E402

import veranda.window as window_mod  # noqa: E402
from veranda.actions.registry import get_action_class  # noqa: E402
from veranda.config import AppConfig  # noqa: E402
from veranda.deck import DeckInfo  # noqa: E402
from veranda.models import ButtonConfig, DeckState, Page, Profile  # noqa: E402
from veranda.settings import SettingsDialog  # noqa: E402

SERIAL = "DEMO-MINI-0001"


def _action(type_id, **params):
    return get_action_class(type_id)(params)


def _btn(label, icon, type_id, background="", **params):
    return ButtonConfig(
        label=label, icon=icon, background=background,
        action=_action(type_id, **params),
    )


def _seed_config(active_page: int) -> None:
    main = Page(name="Main", buttons={
        0: _btn("Firefox", "web-browser-symbolic", "open_app",
                background="#3584e4", desktop_id="firefox.desktop", name="Firefox"),
        1: ButtonConfig(action=_action("clock")),
        2: ButtonConfig(action=_action("date")),
        3: _btn("Copy", "edit-copy-symbolic", "hotkey", combo="ctrl+c"),
        4: _btn("Next", "view-grid-symbolic", "switch_profile", mode="next"),
        5: _btn("Terminal", "utilities-terminal-symbolic", "run_command",
                background="#e66100", command="gnome-terminal"),
    })
    media = Page(name="Media", buttons={
        0: ButtonConfig(action=_action("now_playing")),
        1: _btn("Volume", "audio-volume-high-symbolic", "run_command",
                command="pavucontrol"),
        2: _btn("Browser", "web-browser-symbolic", "open_url",
                background="#613583", url="https://github.com/encompass/veranda"),
        3: ButtonConfig(action=_action("battery")),
        4: ButtonConfig(action=_action("dnd")),
        5: _btn("Lights", "weather-clear-symbolic", "run_command",
                background="#c01c28", command="true"),
    })
    streaming = Profile(name="Streaming", pages=[main, media],
                        active_page=max(0, min(active_page, 1)))
    default = Profile(name="Default", pages=[Page(name="Main")])
    deck = DeckState(
        serial=SERIAL, deck_type="Stream Deck Mini", name="Studio Deck",
        brightness=70, profiles=[streaming, default], active_profile=0,
    )
    cfg = AppConfig(decks={SERIAL: deck})
    cfg.settings.auto_switch = True
    cfg.settings.app_profiles = {
        "firefox.desktop": "Streaming",
        "org.gnome.Nautilus.desktop": "Default",
    }
    cfg.save()


class FakeDeckManager:
    """Reports one fake Mini; swallows all hardware writes."""

    def __init__(self, on_key_press=None, on_decks_changed=None):
        self._info = DeckInfo(serial=SERIAL, deck_type="Stream Deck Mini",
                              rows=2, cols=3, key_count=6)

    def start(self): pass
    def stop(self): pass
    def serials(self): return [SERIAL]
    def info(self, serial): return self._info if serial == SERIAL else None
    def probe_failed(self): return False
    def apply_page(self, serial, page): pass
    def update_button(self, serial, key, button): pass
    def get_brightness(self, serial): return 70
    def set_brightness(self, serial, value): pass


def _load_css() -> None:
    provider = Gtk.CssProvider()
    provider.load_from_data(resources.files("veranda").joinpath("style.css").read_bytes())
    Gtk.StyleContext.add_provider_for_display(
        Gdk.Display.get_default(), provider, Gtk.STYLE_PROVIDER_PRIORITY_APPLICATION,
    )


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--page", type=int, default=0, help="active page (0-based)")
    ap.add_argument("--settings", metavar="PANE", default=None,
                    help="open Settings on a pane: general/profiles/automation/device/backup")
    ap.add_argument("--edit", type=int, metavar="KEY", default=None,
                    help="open the tile editor for a key (0-based) on the active page")
    ap.add_argument("--no-library", action="store_true",
                    help="collapse the action library sidebar (wider key grid)")
    ap.add_argument("--apppicker", action="store_true",
                    help="open the installed-app picker dialog")
    ap.add_argument("--size", default="1120x720", help="window size WxH")
    ap.add_argument("--seconds", type=int, default=600, help="auto-close timeout")
    args = ap.parse_args()
    width, _, height = args.size.partition("x")

    _seed_config(args.page)
    window_mod.DeckManager = FakeDeckManager  # swap before the window builds one

    app = Adw.Application(application_id="com.encompass.VerandaDemo",
                          flags=Gio.ApplicationFlags.NON_UNIQUE)

    def on_activate(a):
        _load_css()
        win = window_mod.VerandaWindow(a)
        win.set_default_size(int(width), int(height))
        win.present()
        if args.settings:
            dlg = SettingsDialog(win)
            dlg.present(win)
            dlg.show_pane(args.settings)
        if args.no_library:
            win._split.set_show_sidebar(False)
        if args.edit is not None:
            page = win._config.deck(SERIAL).current_profile().current_page()
            button = page.buttons.get(args.edit) or ButtonConfig()
            win._open_editor(args.edit, button)
        if args.apppicker:
            from veranda.apppicker import AppPicker
            AppPicker(lambda *a: None).present(win)
        print(f"\n>>> Demo window up (page={args.page}, settings={args.settings}).")
        print(f">>> Screenshot it, then post here. Auto-closes in {args.seconds}s.\n",
              flush=True)
        GLib.timeout_add_seconds(args.seconds, a.quit)

    app.connect("activate", on_activate)
    app.run(None)


if __name__ == "__main__":
    main()
