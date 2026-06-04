"""Wayland-safe keyboard injection via the kernel uinput device.

The legacy streamdeck-linux-gui injects input through X11, which silently
fails on Wayland. We instead create a virtual keyboard with python-evdev's
UInput, which works regardless of the display server as long as /dev/uinput
is writable (a udev rule or the input group grants this).
"""

from __future__ import annotations

import logging
import re
import time

log = logging.getLogger(__name__)

# GTK accelerator modifier tokens (the <...> parts) -> evdev KEY_* suffix.
_ACCEL_MODS = {
    "control": "LEFTCTRL", "ctrl": "LEFTCTRL", "primary": "LEFTCTRL",
    "alt": "LEFTALT", "shift": "LEFTSHIFT",
    "super": "LEFTMETA", "meta": "LEFTMETA", "hyper": "LEFTMETA",
}

# GDK keyval names (and XF86 media keys) -> evdev KEY_* attribute names.
_GTK_KEYS = {
    "space": "KEY_SPACE", "equal": "KEY_EQUAL", "minus": "KEY_MINUS",
    "plus": "KEY_KPPLUS", "Tab": "KEY_TAB", "Above_Tab": "KEY_GRAVE",
    "grave": "KEY_GRAVE", "Escape": "KEY_ESC", "Delete": "KEY_DELETE",
    "BackSpace": "KEY_BACKSPACE", "Return": "KEY_ENTER", "Print": "KEY_SYSRQ",
    "Home": "KEY_HOME", "End": "KEY_END", "Insert": "KEY_INSERT",
    "Page_Up": "KEY_PAGEUP", "Page_Down": "KEY_PAGEDOWN", "Menu": "KEY_COMPOSE",
    "Left": "KEY_LEFT", "Right": "KEY_RIGHT", "Up": "KEY_UP", "Down": "KEY_DOWN",
    "XF86AudioRaiseVolume": "KEY_VOLUMEUP", "XF86AudioLowerVolume": "KEY_VOLUMEDOWN",
    "XF86AudioMute": "KEY_MUTE", "XF86AudioMicMute": "KEY_MICMUTE",
    "XF86AudioPlay": "KEY_PLAYPAUSE", "XF86AudioPause": "KEY_PLAYPAUSE",
    "XF86AudioStop": "KEY_STOPCD", "XF86AudioNext": "KEY_NEXTSONG",
    "XF86AudioPrev": "KEY_PREVIOUSSONG", "XF86AudioMedia": "KEY_MEDIA",
    "XF86Eject": "KEY_EJECTCD", "XF86Calculator": "KEY_CALC",
    "XF86Mail": "KEY_MAIL", "XF86Search": "KEY_SEARCH", "XF86Explorer": "KEY_FILE",
    "XF86WWW": "KEY_WWW", "XF86Tools": "KEY_CONFIG",
    "XF86MonBrightnessUp": "KEY_BRIGHTNESSUP", "XF86MonBrightnessDown": "KEY_BRIGHTNESSDOWN",
}
_GTK_KEYS.update({f"F{i}": f"KEY_F{i}" for i in range(1, 13)})

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

    def send_accelerator(self, accel: str) -> None:
        """Send a GTK-style accelerator like ``<Super>Page_Up`` or ``XF86AudioMute``."""
        self._ensure()
        if self._ui is None:
            raise RuntimeError(self.unavailable_reason)
        mods, keyname = self._parse_accel(accel)
        code = self._accel_keycode(keyname)
        if code is None:
            raise ValueError(f"unsupported key: {keyname!r}")
        self._tap([code], hold=mods)

    def _parse_accel(self, accel: str) -> tuple[list[int], str]:
        mods: list[int] = []
        for token in re.findall(r"<([^>]+)>", accel):
            suffix = _ACCEL_MODS.get(token.lower())
            if suffix:
                code = getattr(self._ecodes, f"KEY_{suffix}", None)
                if code is not None:
                    mods.append(code)
        keyname = re.sub(r"<[^>]+>", "", accel).strip()
        return mods, keyname

    def _accel_keycode(self, name: str) -> int | None:
        if name in _GTK_KEYS:
            return getattr(self._ecodes, _GTK_KEYS[name], None)
        if len(name) == 1:
            return self._keycode(name)
        return getattr(self._ecodes, f"KEY_{name.upper()}", None)

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
