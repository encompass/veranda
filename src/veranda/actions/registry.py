"""Catalog of available action types, grouped by category."""

from __future__ import annotations

from typing import Any, Iterator

from veranda.actions.base import Action
from veranda.actions.deck_control import BrightnessAction, SwitchPageAction
from veranda.actions.gnome_shortcut import GnomeShortcutAction
from veranda.actions.hotkey import HotkeyAction
from veranda.actions.multi import DelayAction, MultiAction
from veranda.actions.open_app import OpenAppAction
from veranda.actions.open_url import OpenUrlAction
from veranda.actions.extras import CopyTextAction, OpenFolderAction
from veranda.actions.run_command import RunCommandAction
from veranda.actions.special.connectivity import (
    NetworkWidget,
    UpdatesWidget,
    WeatherWidget,
)
from veranda.actions.special.media import AppBadgeWidget, NowPlayingWidget
from veranda.actions.special.system import (
    BatteryWidget,
    DoNotDisturbWidget,
    SystemMonitorWidget,
    VolumeWidget,
)
from veranda.actions.special.time import ClockWidget, DateWidget
from veranda.actions.type_text import TypeTextAction

# Order here is the order shown in the library, grouped by CATEGORY.
ACTION_CATALOG: list[type[Action]] = [
    OpenAppAction,
    RunCommandAction,
    OpenUrlAction,
    OpenFolderAction,
    HotkeyAction,
    TypeTextAction,
    CopyTextAction,
    GnomeShortcutAction,
    MultiAction,
    SwitchPageAction,
    BrightnessAction,
    # Special Buttons (live widgets)
    ClockWidget,
    DateWidget,
    NowPlayingWidget,
    AppBadgeWidget,
    BatteryWidget,
    SystemMonitorWidget,
    VolumeWidget,
    DoNotDisturbWidget,
    NetworkWidget,
    WeatherWidget,
    UpdatesWidget,
]

# Reconstructable but not shown in the palette (only used inside macros).
_EXTRA_TYPES: list[type[Action]] = [DelayAction]

_BY_TYPE: dict[str, type[Action]] = {
    cls.TYPE_ID: cls for cls in (*ACTION_CATALOG, *_EXTRA_TYPES)
}


def get_action_class(type_id: str) -> type[Action] | None:
    return _BY_TYPE.get(type_id)


def action_from_dict(data: dict[str, Any] | None) -> Action | None:
    """Reconstruct an Action from its serialized form, or None."""
    if not data:
        return None
    cls = _BY_TYPE.get(data.get("type", ""))
    if cls is None:
        return None
    return cls.from_dict(data)


def iter_categories() -> Iterator[tuple[str, list[type[Action]]]]:
    """Yield ``(category, [action_classes])`` preserving catalog order."""
    seen: list[str] = []
    grouped: dict[str, list[type[Action]]] = {}
    for cls in ACTION_CATALOG:
        if cls.CATEGORY not in grouped:
            grouped[cls.CATEGORY] = []
            seen.append(cls.CATEGORY)
        grouped[cls.CATEGORY].append(cls)
    for category in seen:
        yield category, grouped[category]
