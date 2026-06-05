"""Virtual ("software") Stream Deck — a deck that lives in its own window.

`VirtualDeck` implements the same duck-typed interface `DeckManager` expects of
a hardware deck (open/reset/get_serial_number/key_layout/deck_type/key_count/id/
set_key_callback/set_brightness/close/__enter__/__exit__), so it plugs straight
into the existing pipeline. Its keys render to a borderless `VirtualDeckWindow`
via the GUI preview path, and clicks feed presses back through the deck's
key callback exactly like hardware.
"""

from __future__ import annotations

import threading
from typing import Callable

import gi

gi.require_version("Gtk", "4.0")
gi.require_version("Gdk", "4.0")
from gi.repository import Gdk, Gtk  # noqa: E402

from veranda.livebuttons import LiveButtonController  # noqa: E402
from veranda.models import ButtonConfig  # noqa: E402
from veranda.render import render_preview_texture  # noqa: E402

# Window titles share the app's wm_class, so the GNOME Shell extension matches
# virtual windows by this title prefix to keep them on top / positioned.
TITLE_PREFIX = "Veranda Virtual Deck — "
TILE_SIZE = 96


class VirtualDeck:
    """A software deck object compatible with DeckManager."""

    is_virtual = True

    def __init__(self, serial: str, rows: int, cols: int, name: str = "") -> None:
        self._serial = serial
        self._rows = max(1, rows)
        self._cols = max(1, cols)
        self._name = name
        self._callback: Callable | None = None
        self._lock = threading.RLock()
        self.window: VirtualDeckWindow | None = None

    # -- hardware-deck interface -----------------------------------------

    def open(self) -> None:  # noqa: D401 - no-op for virtual
        pass

    def reset(self) -> None:
        if self.window is not None:
            self.window.clear()

    def close(self) -> None:
        if self.window is not None:
            self.window.destroy()
            self.window = None

    def get_serial_number(self) -> str:
        return self._serial

    def key_layout(self) -> tuple[int, int]:
        return (self._rows, self._cols)

    def deck_type(self) -> str:
        return f"Virtual {self._rows}×{self._cols}"

    def key_count(self) -> int:
        return self._rows * self._cols

    def id(self) -> str:
        return f"virtual:{self._serial}"

    def set_key_callback(self, fn: Callable) -> None:
        self._callback = fn

    def set_brightness(self, value: int) -> None:
        if self.window is not None:
            self.window.set_brightness(value)

    def __enter__(self) -> "VirtualDeck":
        self._lock.acquire()
        return self

    def __exit__(self, *_exc) -> None:
        self._lock.release()

    # -- virtual-specific -------------------------------------------------

    def render_key(self, key: int, button: ButtonConfig | None) -> None:
        if self.window is not None:
            self.window.render_key(key, button)

    def fire(self, key: int) -> None:
        """A key was clicked in the window — route it like a hardware press."""
        if self._callback is not None:
            self._callback(self, key, True)


class _PressTile(Gtk.Button):
    """A single virtual key: shows the composited image, dispatches on click."""

    def __init__(self, key: int, on_press: Callable[[int], None]) -> None:
        super().__init__()
        self.key = key
        self.add_css_class("flat")
        self.add_css_class("virtual-tile")
        self.set_size_request(TILE_SIZE, TILE_SIZE)
        self._picture = Gtk.Picture(content_fit=Gtk.ContentFit.CONTAIN)
        self._picture.set_size_request(TILE_SIZE, TILE_SIZE)
        self.set_child(self._picture)
        self.connect("clicked", lambda _b: on_press(self.key))
        self.set_button(None)

    def set_button(self, button: ButtonConfig | None) -> None:
        cfg = button if (button is not None and not button.is_empty) else ButtonConfig()
        self._picture.set_paintable(render_preview_texture(cfg, size=TILE_SIZE))


class VirtualDeckWindow(Gtk.ApplicationWindow):
    """Borderless floating window that displays a virtual deck and presses keys."""

    def __init__(
        self,
        app,
        deck: VirtualDeck,
        name: str,
        *,
        on_settings: Callable[[], None],
        on_close: Callable[[], None],
        on_toggle_top: Callable[[bool], None],
        on_hide: Callable[[], None] = lambda: None,
        on_top: bool = False,
        bg: str = "",
    ) -> None:
        super().__init__(application=app)
        self._deck = deck
        self._on_settings = on_settings
        self._on_close = on_close
        self._on_toggle_top = on_toggle_top
        self._on_hide = on_hide
        self._on_top = on_top
        rows, cols = deck.key_layout()

        self.set_decorated(False)  # borderless (Wayland-safe)
        self.set_resizable(False)
        self.set_title(TITLE_PREFIX + (name or deck.get_serial_number()))
        self.add_css_class("virtual-deck")

        grid = Gtk.Grid(
            row_spacing=8, column_spacing=8,
            margin_top=8, margin_bottom=8, margin_start=8, margin_end=8,
        )
        self._tiles: dict[int, _PressTile] = {}
        key = 0
        for r in range(rows):
            for c in range(cols):
                tile = _PressTile(key, self._deck.fire)
                grid.attach(tile, c, r, 1, 1)
                self._tiles[key] = tile
                key += 1

        # Gtk.WindowHandle makes the whole surface draggable to move the window;
        # it is also the rounded, coloured surface behind the keys.
        handle = Gtk.WindowHandle()
        handle.add_css_class("virtual-deck-surface")
        handle.set_child(grid)
        self.set_child(handle)
        self._bg_provider = Gtk.CssProvider()
        handle.get_style_context().add_provider(
            self._bg_provider, Gtk.STYLE_PROVIDER_PRIORITY_APPLICATION + 1
        )
        self.set_background(bg)

        # Right-click anywhere → options menu.
        gesture = Gtk.GestureClick(button=3)
        gesture.connect("pressed", self._on_right_click)
        self.add_controller(gesture)

        self.connect("close-request", self._on_close_request)

    # -- rendering --------------------------------------------------------

    def render_key(self, key: int, button: ButtonConfig | None) -> None:
        tile = self._tiles.get(key)
        if tile is not None:
            tile.set_button(button)

    def clear(self) -> None:
        for tile in self._tiles.values():
            tile.set_button(None)

    def set_brightness(self, value: int) -> None:
        self.set_opacity(max(0.35, min(1.0, value / 100)))

    def set_background(self, color: str) -> None:
        """Override the surface colour (``""`` → the stylesheet default)."""
        css = f".virtual-deck-surface {{ background-color: {color}; }}" if color else \
            ".virtual-deck-surface {}"
        self._bg_provider.load_from_data(css.encode())

    # -- chrome / menu ----------------------------------------------------

    def _on_close_request(self, _w) -> bool:
        self._on_hide()  # closing a virtual deck hides it; "Remove" deletes it
        return True

    def _on_right_click(self, gesture, _n, x, y) -> None:
        popover = Gtk.Popover(has_arrow=False)
        popover.set_parent(self)
        rect = Gdk.Rectangle()
        rect.x, rect.y, rect.width, rect.height = int(x), int(y), 1, 1
        popover.set_pointing_to(rect)

        box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=0)
        box.add_css_class("menu")

        top = Gtk.ToggleButton(label="Always on top")
        top.set_active(self._on_top)
        top.add_css_class("flat")
        top.connect("toggled", lambda b: (popover.popdown(), self._set_top(b.get_active())))
        box.append(top)

        settings = Gtk.Button(child=Gtk.Label(label="Settings…", xalign=0.0))
        settings.add_css_class("flat")
        settings.connect("clicked", lambda _b: (popover.popdown(), self._on_settings()))
        box.append(settings)

        hide = Gtk.Button(child=Gtk.Label(label="Close", xalign=0.0))
        hide.add_css_class("flat")
        hide.connect("clicked", lambda _b: (popover.popdown(), self._on_hide()))
        box.append(hide)

        remove = Gtk.Button(child=Gtk.Label(label="Remove", xalign=0.0))
        remove.add_css_class("flat")
        remove.connect("clicked", lambda _b: (popover.popdown(), self._on_close()))
        box.append(remove)

        popover.set_child(box)
        popover.connect("closed", lambda p: p.unparent())
        popover.popup()

    def _set_top(self, active: bool) -> None:
        self._on_top = active
        self._on_toggle_top(active)


class VirtualDeckManager:
    """Owns all virtual decks (objects, windows, per-deck live controllers).

    Lives in the main window. Each virtual deck runs its own
    :class:`LiveButtonController` so its floating window's special buttons stay
    live even when it isn't the device selected in the editor — except the
    currently-selected one, which the window's own controller already drives
    (avoiding two controllers fighting over the same action callbacks).
    """

    def __init__(self, app, deck_manager, config, *,
                 refresh: Callable[[], None],
                 open_settings: Callable[[str], None],
                 windows_changed: Callable[[], None]) -> None:
        self._app = app
        self._dm = deck_manager
        self._config = config
        self._refresh = refresh
        self._open_settings = open_settings
        self._windows_changed = windows_changed
        self._decks: dict[str, VirtualDeck] = {}
        self._live: dict[str, LiveButtonController] = {}

    # -- lifecycle --------------------------------------------------------

    def restore_all(self) -> None:
        for serial, state in list(self._config.decks.items()):
            if state.virtual and serial not in self._decks:
                self._build(serial, state)

    def add(self, rows: int, cols: int, name: str = "Virtual Deck",
            bg: str = "", visible: bool = True) -> str:
        serial = self._next_serial()
        state = self._config.deck(serial)
        state.virtual = True
        state.grid_rows, state.grid_cols = rows, cols
        state.name = name
        state.deck_type = f"Virtual {rows}×{cols}"
        state.window["bg"] = bg
        state.window["visible"] = visible
        self._config.save()
        self._build(serial, state)
        return serial

    def set_background(self, serial: str, bg: str) -> None:
        state = self._config.decks.get(serial)
        if state is None:
            return
        state.window["bg"] = bg
        self._config.save()
        deck = self._decks.get(serial)
        if deck is not None and deck.window is not None:
            deck.window.set_background(bg)

    def set_visible(self, serial: str, visible: bool) -> None:
        state = self._config.decks.get(serial)
        if state is None:
            return
        state.window["visible"] = visible
        self._config.save()
        deck = self._decks.get(serial)
        if deck is not None and deck.window is not None:
            if visible:
                deck.window.present()
            else:
                deck.window.set_visible(False)
        self._windows_changed()

    def is_visible(self, serial: str) -> bool:
        state = self._config.decks.get(serial)
        return bool(state.window.get("visible", True)) if state else False

    def remove(self, serial: str) -> None:
        ctrl = self._live.pop(serial, None)
        if ctrl is not None:
            ctrl.stop()
        self._dm.remove_virtual_deck(serial)  # closes the window via deck.close()
        self._decks.pop(serial, None)
        self._config.decks.pop(serial, None)
        self._config.save()
        self._windows_changed()
        self._refresh()

    def resize(self, serial: str, rows: int, cols: int) -> None:
        state = self._config.decks.get(serial)
        if state is None or (state.grid_rows, state.grid_cols) == (rows, cols):
            return
        state.grid_rows, state.grid_cols = rows, cols
        state.deck_type = f"Virtual {rows}×{cols}"
        ctrl = self._live.pop(serial, None)
        if ctrl is not None:
            ctrl.stop()
        self._dm.remove_virtual_deck(serial)
        self._decks.pop(serial, None)
        self._config.save()
        self._build(serial, state)
        self._refresh()

    def _build(self, serial: str, state) -> None:
        deck = VirtualDeck(serial, state.grid_rows, state.grid_cols, name=state.display_name)
        win = VirtualDeckWindow(
            self._app, deck, state.display_name,
            on_settings=lambda s=serial: self._open_settings(s),
            on_close=lambda s=serial: self.remove(s),
            on_toggle_top=lambda active, s=serial: self._set_on_top(s, active),
            on_hide=lambda s=serial: self.set_visible(s, False),
            on_top=bool(state.window.get("on_top", False)),
            bg=str(state.window.get("bg", "")),
        )
        deck.window = win
        self._decks[serial] = deck
        self._dm.add_virtual_deck(deck)
        if state.window.get("visible", True):
            win.present()  # otherwise created hidden until shown from Settings
        self._live[serial] = LiveButtonController(self._repaint_cb(serial))
        self._windows_changed()

    def _next_serial(self) -> str:
        n = 1
        while f"virtual-{n}" in self._config.decks:
            n += 1
        return f"virtual-{n}"

    # -- live buttons -----------------------------------------------------

    def sync_live(self, current_serial: str | None) -> None:
        """Drive each non-current virtual deck's live buttons; pause the current
        one (the window's own controller handles it).

        Must run after the window's own controller has been stopped: it stops
        *every* per-deck controller first, then re-arms only the non-current
        ones, so a shared widget action is never subscribed twice.
        """
        for ctrl in self._live.values():
            ctrl.stop()
        for serial, ctrl in self._live.items():
            state = self._config.decks.get(serial)
            if serial != current_serial and state is not None:
                ctrl.rebuild(state.current_page())

    def _repaint_cb(self, serial: str) -> Callable[[int], None]:
        def repaint(key: int) -> None:
            state = self._config.decks.get(serial)
            if state is not None:
                self._dm.update_button(serial, key, state.current_page().buttons.get(key))
        return repaint

    # -- always-on-top / geometry ----------------------------------------

    def _set_on_top(self, serial: str, active: bool) -> None:
        state = self._config.decks.get(serial)
        if state is not None:
            state.window["on_top"] = active
            self._config.save()
        self._windows_changed()

    def window_geometry(self) -> list[tuple[str, int, int, bool]]:
        """For the Shell extension: (title, x, y, on_top) per virtual window."""
        out = []
        for serial, deck in self._decks.items():
            state = self._config.decks.get(serial)
            if state is None or deck.window is None:
                continue
            w = state.window
            if not w.get("visible", True):
                continue  # nothing to place/raise for a hidden window
            out.append((
                deck.window.get_title(),
                int(w.get("x", 80)), int(w.get("y", 80)),
                bool(w.get("on_top", False)),
            ))
        return out

    def report_moved(self, title: str, x: int, y: int) -> None:
        for serial, deck in self._decks.items():
            if deck.window is not None and deck.window.get_title() == title:
                self._config.decks[serial].window.update({"x": x, "y": y})
                self._config.save()
                return

    def shutdown(self) -> None:
        for ctrl in self._live.values():
            ctrl.stop()
        for deck in self._decks.values():
            deck.close()
        self._live.clear()
        self._decks.clear()
