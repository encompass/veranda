#!/usr/bin/env python3
"""Raw Stream Deck key logger — bypasses all of Veranda.

Quit your running Veranda instance first (it holds the device), then run:
    .venv/bin/python tools/keylog.py

Press the problem keys (e.g. the "Volume Up" / "Weather" key). Each line is one
event straight from the python-elgato-streamdeck library. If a single physical
press prints TWO lines (e.g. key=2 then key=1), the double-fire is in the
hardware/library, not Veranda. Ctrl-C or wait 60s to stop.
"""

import time

from StreamDeck.DeviceManager import DeviceManager


def main() -> None:
    decks = DeviceManager().enumerate()
    if not decks:
        print("No Stream Deck found (is another instance still running?)")
        return
    deck = decks[0]
    deck.open()
    deck.reset()
    print(f"Listening on {deck.deck_type()} ({deck.get_serial_number()}), "
          f"{deck.key_count()} keys. Press keys now…", flush=True)

    states = [False] * deck.key_count()

    def on_key(_deck, key, state):
        states[key] = bool(state)
        snap = "".join("#" if s else "." for s in states)
        print(f"  key={key} {'DOWN' if state else 'up  '}  all=[{snap}]  "
              f"t={time.monotonic():.3f}", flush=True)

    deck.set_key_callback(on_key)
    try:
        time.sleep(60)
    except KeyboardInterrupt:
        pass
    finally:
        deck.reset()
        deck.close()
        print("done.")


if __name__ == "__main__":
    main()
