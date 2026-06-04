"""Device layer: discover, open, render to, and watch Stream Deck hardware.

Stream Deck key callbacks arrive on the library's background HID thread. This
module is the only place that touches the hardware; it marshals every event to
the GTK main loop via GLib.idle_add so the UI and dispatcher stay single-
threaded. All device I/O is serialized with the deck's own lock (`with deck:`).
"""

from __future__ import annotations

import logging
import threading
from dataclasses import dataclass
from typing import Callable

from gi.repository import GLib
from StreamDeck.DeviceManager import DeviceManager, ProbeError

from veranda.models import ButtonConfig, Page
from veranda.render import blank_native, render_native

log = logging.getLogger(__name__)

POLL_INTERVAL_S = 1.0


@dataclass
class DeckInfo:
    serial: str
    deck_type: str
    rows: int
    cols: int
    key_count: int


class DeckManager:
    """Owns the set of open decks and a background hotplug monitor."""

    def __init__(
        self,
        on_key_press: Callable[[str, int], None],
        on_decks_changed: Callable[[], None],
    ) -> None:
        self._on_key_press = on_key_press
        self._on_decks_changed = on_decks_changed
        self._decks: dict[str, object] = {}  # serial -> StreamDeck
        self._by_id: dict[str, object] = {}  # deck.id() -> StreamDeck
        self._info: dict[str, DeckInfo] = {}
        self._brightness: dict[str, int] = {}
        self._probe_failed = False
        self._lock = threading.Lock()
        self._stop = threading.Event()
        self._thread: threading.Thread | None = None

    # -- lifecycle --------------------------------------------------------

    def start(self) -> None:
        self._thread = threading.Thread(target=self._poll_loop, daemon=True)
        self._thread.start()

    def stop(self) -> None:
        self._stop.set()
        thread = self._thread
        if thread is not None and thread.is_alive():
            thread.join(timeout=2.0)  # let the poll loop finish its iteration
        with self._lock:
            for deck in list(self._decks.values()):
                self._teardown(deck)
            self._decks.clear()
            self._by_id.clear()
            self._info.clear()

    # -- queries ----------------------------------------------------------

    def serials(self) -> list[str]:
        with self._lock:
            return list(self._decks.keys())

    def info(self, serial: str) -> DeckInfo | None:
        return self._info.get(serial)

    def get_open_deck(self, serial: str):
        return self._decks.get(serial)

    def probe_failed(self) -> bool:
        return self._probe_failed

    # -- rendering --------------------------------------------------------

    def apply_page(self, serial: str, page: Page) -> None:
        """Push every key image for ``page`` to the device."""
        deck = self._decks.get(serial)
        info = self._info.get(serial)
        if deck is None or info is None:
            return
        for key in range(info.key_count):
            button = page.buttons.get(key)
            self._set_key(deck, key, button)

    def update_button(self, serial: str, key: int, button: ButtonConfig | None) -> None:
        deck = self._decks.get(serial)
        if deck is not None:
            self._set_key(deck, key, button)

    def _set_key(self, deck, key: int, button: ButtonConfig | None) -> None:
        try:
            image = (
                render_native(deck, button)
                if button is not None and not button.is_empty
                else blank_native(deck)
            )
            with deck:
                deck.set_key_image(key, image)
        except Exception as exc:  # noqa: BLE001 - hardware can disappear mid-call
            log.warning("set_key_image(%s) failed: %s", key, exc)

    # -- brightness -------------------------------------------------------

    def get_brightness(self, serial: str) -> int:
        return self._brightness.get(serial, 60)

    def set_brightness(self, serial: str, value: int) -> None:
        deck = self._decks.get(serial)
        if deck is None:
            return
        value = max(0, min(100, int(value)))
        self._brightness[serial] = value
        try:
            with deck:
                deck.set_brightness(value)
        except Exception as exc:  # noqa: BLE001
            log.warning("set_brightness failed: %s", exc)

    # -- hotplug monitor --------------------------------------------------

    def _poll_loop(self) -> None:
        while not self._stop.is_set():
            self._scan()
            self._stop.wait(POLL_INTERVAL_S)

    def _scan(self) -> None:
        try:
            found = DeviceManager().enumerate()
        except ProbeError:
            if not self._probe_failed:
                self._probe_failed = True
                GLib.idle_add(self._on_decks_changed)
            return
        except Exception as exc:  # noqa: BLE001
            log.debug("enumerate failed: %s", exc)
            return

        live_ids = {}
        changed = False
        for deck in found:
            try:
                live_ids[deck.id()] = deck
            except Exception:  # noqa: BLE001
                continue

        with self._lock:
            # Newly connected devices.
            for dev_id, deck in live_ids.items():
                if dev_id not in self._by_id:
                    if self._open(deck):
                        changed = True
            # Devices that went away.
            for dev_id in list(self._by_id.keys()):
                if dev_id not in live_ids:
                    self._drop(dev_id)
                    changed = True

        if changed:
            GLib.idle_add(self._on_decks_changed)

    def _open(self, deck) -> bool:
        try:
            deck.open()
            deck.reset()
            serial = deck.get_serial_number()
            rows, cols = deck.key_layout()
            info = DeckInfo(
                serial=serial,
                deck_type=deck.deck_type(),
                rows=rows,
                cols=cols,
                key_count=deck.key_count(),
            )
            deck.set_key_callback(self._key_callback)
            brightness = self._brightness.get(serial, 60)
            deck.set_brightness(brightness)
            self._brightness[serial] = brightness
            self._decks[serial] = deck
            self._by_id[deck.id()] = deck
            self._info[serial] = info
            log.info("opened %s (%s)", info.deck_type, serial)
            return True
        except Exception as exc:  # noqa: BLE001 - often a permissions error
            log.warning("could not open deck: %s", exc)
            return False

    def _drop(self, dev_id: str) -> None:
        deck = self._by_id.pop(dev_id, None)
        if deck is None:
            return
        serial = None
        for s, d in list(self._decks.items()):
            if d is deck:
                serial = s
                break
        if serial:
            self._decks.pop(serial, None)
            self._info.pop(serial, None)
        self._teardown(deck)
        log.info("deck disconnected (%s)", serial)

    def _teardown(self, deck) -> None:
        try:
            with deck:
                deck.reset()
            deck.close()
        except Exception:  # noqa: BLE001
            pass

    def _key_callback(self, deck, key: int, state: bool) -> None:
        # Runs on the HID reader thread. Hop to the GTK main loop.
        if not state:
            return
        try:
            serial = deck.get_serial_number()
        except Exception:  # noqa: BLE001
            return
        GLib.idle_add(self._on_key_press, serial, key)
