"""Wayland-safe keyboard injection via the kernel uinput device.

The legacy streamdeck-linux-gui injects input through X11, which silently
fails on Wayland. We instead create a virtual keyboard with python-evdev's
UInput, which works regardless of the display server as long as /dev/uinput
is writable (a udev rule or the input group grants this).
"""

from __future__ import annotations

import logging
import time

log = logging.getLogger(__name__)

# Map friendly modifier/key names to evdev KEY_* attribute suffixes.
_MODIFIERS = {
    "ctrl": "LEFTCTRL",
    "control": "LEFTCTRL",
    "alt": "LEFTALT",
    "altgr": "RIGHTALT",
    "shift": "LEFTSHIFT",
    "super": "LEFTMETA",
    "meta": "LEFTMETA",
    "win": "LEFTMETA",
    "cmd": "LEFTMETA",
}

# Characters that require Shift, mapped to the base key name.
_SHIFTED = {
    "!": "1", "@": "2", "#": "3", "$": "4", "%": "5", "^": "6", "&": "7",
    "*": "8", "(": "9", ")": "0", "_": "minus", "+": "equal", "{": "leftbrace",
    "}": "rightbrace", "|": "backslash", ":": "semicolon", '"': "apostrophe",
    "<": "comma", ">": "dot", "?": "slash", "~": "grave",
}

# Punctuation whose KEY_* name differs from the character.
_PUNCT = {
    " ": "space", "-": "minus", "=": "equal", "[": "leftbrace",
    "]": "rightbrace", "\\": "backslash", ";": "semicolon", "'": "apostrophe",
    ",": "comma", ".": "dot", "/": "slash", "`": "grave", "\n": "enter",
    "\t": "tab",
}


class InputBackend:
    """Lazily-opened uinput virtual keyboard."""

    def __init__(self) -> None:
        self._ui = None
        self._ecodes = None
        self.unavailable_reason = "Keyboard injection not initialized."
        self._tried = False

    @property
    def available(self) -> bool:
        if not self._tried:
            self._ensure()
        return self._ui is not None

    def _ensure(self) -> None:
        if self._tried:
            return
        self._tried = True
        try:
            from evdev import UInput, ecodes

            self._ecodes = ecodes
            # Advertise the full key range so any KEY_* we emit is accepted.
            cap = {ecodes.EV_KEY: list(range(0, 256))}
            self._ui = UInput(cap, name="Veranda Virtual Keyboard")
            log.info("uinput keyboard ready")
        except PermissionError:
            self.unavailable_reason = (
                "Cannot open /dev/uinput. Add yourself to the 'input' group or "
                "install the Veranda udev rule, then re-plug or re-login."
            )
            log.warning(self.unavailable_reason)
        except (ImportError, OSError) as exc:
            self.unavailable_reason = f"Keyboard injection unavailable: {exc}"
            log.warning(self.unavailable_reason)

    def _keycode(self, name: str) -> int | None:
        name = name.strip().lower()
        if name in _MODIFIERS:
            attr = "KEY_" + _MODIFIERS[name]
        elif name in _PUNCT:
            attr = "KEY_" + _PUNCT[name].upper()
        elif len(name) == 1 and name.isalnum():
            attr = "KEY_" + name.upper()
        else:
            attr = "KEY_" + name.upper()
        return getattr(self._ecodes, attr, None)

    def _tap(self, codes: list[int], hold: list[int] | None = None) -> None:
        hold = hold or []
        for c in hold:
            self._ui.write(self._ecodes.EV_KEY, c, 1)
        for c in codes:
            self._ui.write(self._ecodes.EV_KEY, c, 1)
            self._ui.write(self._ecodes.EV_KEY, c, 0)
        for c in reversed(hold):
            self._ui.write(self._ecodes.EV_KEY, c, 0)
        self._ui.syn()

    def send_combo(self, combo: str) -> None:
        """Send a chord like ``ctrl+shift+t``."""
        self._ensure()
        if self._ui is None:
            raise RuntimeError(self.unavailable_reason)
        parts = [p for p in combo.replace(" ", "").split("+") if p]
        if not parts:
            return
        mods, keys = [], []
        for p in parts:
            code = self._keycode(p)
            if code is None:
                log.warning("unknown key in combo: %s", p)
                continue
            (mods if p.lower() in _MODIFIERS else keys).append(code)
        if keys:
            self._tap(keys, hold=mods)

    def type_text(self, text: str) -> None:
        """Type a literal string, one character at a time."""
        self._ensure()
        if self._ui is None:
            raise RuntimeError(self.unavailable_reason)
        shift = self._keycode("shift")
        for ch in text:
            hold = []
            if ch in _SHIFTED:
                base = _SHIFTED[ch]
                hold = [shift]
            elif ch.isupper():
                base = ch.lower()
                hold = [shift]
            else:
                base = ch
            code = self._keycode(base)
            if code is None:
                continue
            self._tap([code], hold=hold)
            time.sleep(0.002)

    def close(self) -> None:
        if self._ui is not None:
            try:
                self._ui.close()
            except Exception:  # noqa: BLE001
                pass
            self._ui = None
