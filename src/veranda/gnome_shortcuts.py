"""Read GNOME's keyboard-shortcut catalog and current bindings.

GNOME Control Center describes its fixed shortcuts in XML under
``/usr/share/gnome-control-center/keybindings`` (category name, schema, and
GSettings key per entry); the live key bindings live in GSettings. User-defined
"custom shortcuts" have a name + command + binding under a relocatable schema.
"""

from __future__ import annotations

import glob
import logging
import os
import xml.etree.ElementTree as ET
from dataclasses import dataclass

from gi.repository import Gio

log = logging.getLogger(__name__)

KEYBINDINGS_DIR = "/usr/share/gnome-control-center/keybindings"
MEDIA_KEYS_SCHEMA = "org.gnome.settings-daemon.plugins.media-keys"
CUSTOM_SCHEMA = "org.gnome.settings-daemon.plugins.media-keys.custom-keybinding"


@dataclass
class GnomeShortcut:
    category: str
    description: str
    accel: str           # GTK accelerator, e.g. "<Super>Page_Up" or "XF86AudioMute"
    kind: str            # "builtin" or "custom"
    schema: str = ""     # builtin: schema id to re-resolve the live binding
    key: str = ""        # builtin: GSettings key
    command: str = ""    # custom: command to run


def _schema_present(schema: str) -> bool:
    return Gio.SettingsSchemaSource.get_default().lookup(schema, True) is not None


def _first_accel(settings: Gio.Settings, key: str) -> str | None:
    if key not in settings.list_keys():
        return None
    value = settings.get_value(key)
    ts = value.get_type_string()
    if ts == "as":
        items = [a for a in value.unpack() if a]
        return items[0] if items else None
    if ts == "s":
        s = value.unpack()
        return s or None
    return None


def resolve_accel(schema: str, key: str) -> str | None:
    """Current accelerator for a builtin shortcut (tries the static key too)."""
    if not _schema_present(schema):
        return None
    try:
        settings = Gio.Settings(schema_id=schema)
    except Exception:  # noqa: BLE001
        return None
    return _first_accel(settings, key) or _first_accel(settings, f"{key}-static")


def _builtin_catalog() -> list[GnomeShortcut]:
    shortcuts: list[GnomeShortcut] = []
    for path in sorted(glob.glob(os.path.join(KEYBINDINGS_DIR, "*.xml"))):
        try:
            root = ET.parse(path).getroot()
        except ET.ParseError as exc:
            log.debug("could not parse %s: %s", path, exc)
            continue
        category = root.get("name") or root.get("group") or "Other"
        default_schema = root.get("schema") or ""
        for entry in root.findall("KeyListEntry"):
            name = entry.get("name")
            if not name:
                continue
            schema = entry.get("schema") or default_schema
            if not schema:
                continue
            accel = resolve_accel(schema, name)
            if not accel:
                continue  # nothing bound -> can't trigger it
            shortcuts.append(GnomeShortcut(
                category=category,
                description=entry.get("description") or name,
                accel=accel,
                kind="builtin",
                schema=schema,
                key=name,
            ))
    return shortcuts


def _custom_catalog() -> list[GnomeShortcut]:
    if not _schema_present(MEDIA_KEYS_SCHEMA) or not _schema_present(CUSTOM_SCHEMA):
        return []
    media = Gio.Settings(schema_id=MEDIA_KEYS_SCHEMA)
    out: list[GnomeShortcut] = []
    for cpath in media.get_value("custom-keybindings").unpack():
        try:
            cs = Gio.Settings(schema_id=CUSTOM_SCHEMA, path=cpath)
        except Exception:  # noqa: BLE001
            continue
        command = cs.get_string("command")
        if not command:
            continue
        out.append(GnomeShortcut(
            category="Custom Shortcuts",
            description=cs.get_string("name") or command,
            accel=cs.get_string("binding"),
            kind="custom",
            command=command,
        ))
    return out


def catalog() -> list[GnomeShortcut]:
    """All triggerable GNOME shortcuts (builtin with a binding + custom)."""
    return _builtin_catalog() + _custom_catalog()


def friendly_accel(accel: str) -> str:
    """A human label for an accelerator (e.g. ``<Super>space`` -> ``Super+Space``)."""
    if not accel:
        return ""
    try:
        import gi

        gi.require_version("Gtk", "4.0")
        from gi.repository import Gtk

        ok, keyval, mods = Gtk.accelerator_parse(accel)
        if ok and keyval:
            label = Gtk.accelerator_get_label(keyval, mods)
            if label:
                return label
    except Exception:  # noqa: BLE001
        pass
    return accel
