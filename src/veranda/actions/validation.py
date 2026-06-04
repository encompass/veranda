"""Live validity checks for command-style action editors.

Each ``*_status`` returns ``(ok, tooltip)`` where ``ok`` is True (valid),
False (invalid), or None (empty / nothing to check). ``attach_validity`` shows
that as a green check / orange warning suffix icon on an Adw.EntryRow.
"""

from __future__ import annotations

import os
import shlex
import shutil
from typing import Callable


def command_status(text: str) -> tuple[bool | None, str]:
    text = text.strip()
    if not text:
        return (None, "")
    try:
        argv = shlex.split(text)
    except ValueError as exc:
        return (False, f"Can't parse: {exc}")
    if not argv:
        return (None, "")
    exe = argv[0]
    path = shutil.which(exe)
    if path:
        return (True, f"Found: {path}")
    if os.path.isabs(exe) and os.access(exe, os.X_OK):
        return (True, f"Executable: {exe}")
    return (False, f"Not found on PATH: {exe}")


def path_status(text: str) -> tuple[bool | None, str]:
    text = text.strip()
    if not text:
        return (None, "")
    if "://" in text:
        return (True, "Looks like a URL")
    expanded = os.path.expanduser(text)
    if os.path.exists(expanded):
        return (True, "File exists")
    return (False, "File not found")


def folder_status(text: str) -> tuple[bool | None, str]:
    text = text.strip()
    if not text:
        return (None, "")
    expanded = os.path.expanduser(text)
    if os.path.isdir(expanded):
        return (True, "Folder exists")
    if os.path.exists(expanded):
        return (False, "Not a folder")
    return (False, "Folder not found")


def hotkey_status(text: str) -> tuple[bool | None, str]:
    from veranda.input_backend import combo_is_valid

    return combo_is_valid(text)


def attach_validity(row, validate: Callable[[str], tuple[bool | None, str]]):
    """Add a live validity indicator (suffix icon) to an Adw.EntryRow."""
    from gi.repository import Gtk

    icon = Gtk.Image(valign=Gtk.Align.CENTER)
    row.add_suffix(icon)

    def update(*_a) -> None:
        ok, tip = validate(row.get_text())
        icon.remove_css_class("success")
        icon.remove_css_class("warning")
        if ok is None:
            icon.set_visible(False)
            return
        icon.set_visible(True)
        icon.set_from_icon_name("emblem-ok-symbolic" if ok else "dialog-warning-symbolic")
        icon.add_css_class("success" if ok else "warning")
        icon.set_tooltip_text(tip)

    row.connect("changed", update)
    update()
    return icon
