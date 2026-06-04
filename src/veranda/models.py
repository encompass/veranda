"""Data models for decks, pages, buttons, and the drag-and-drop payload."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

import gi

gi.require_version("Gtk", "4.0")
from gi.repository import GObject  # noqa: E402

from veranda.actions import Action, action_from_dict  # noqa: E402

DEFAULT_BRIGHTNESS = 60


@dataclass
class AppSettings:
    """Application-wide (not per-device) preferences."""

    run_in_background: bool = False
    start_hidden: bool = False
    tray_warning_dismissed: bool = False

    def to_dict(self) -> dict[str, Any]:
        return {
            "run_in_background": self.run_in_background,
            "start_hidden": self.start_hidden,
            "tray_warning_dismissed": self.tray_warning_dismissed,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any] | None) -> "AppSettings":
        data = data or {}
        return cls(
            run_in_background=bool(data.get("run_in_background", False)),
            start_hidden=bool(data.get("start_hidden", False)),
            tray_warning_dismissed=bool(data.get("tray_warning_dismissed", False)),
        )


class ActionItem(GObject.Object):
    """Drag-and-drop payload describing an action *type* from the library.

    Carries only the type identity (not a configured instance); when dropped
    on a tile, a fresh :class:`Action` is instantiated with its defaults.
    """

    __gtype_name__ = "VerandaActionItem"

    type_id = GObject.Property(type=str)
    name = GObject.Property(type=str)
    icon = GObject.Property(type=str)
    category = GObject.Property(type=str)

    def __init__(self, action_class: type[Action]) -> None:
        super().__init__()
        self.type_id = action_class.TYPE_ID
        self.name = action_class.NAME
        self.icon = action_class.ICON
        self.category = action_class.CATEGORY
        self._action_class = action_class

    def new_action(self) -> Action:
        return self._action_class()


@dataclass
class ButtonConfig:
    """Presentation + bound action for a single key on a page."""

    label: str = ""
    icon: str = ""  # absolute file path, or a symbolic icon name
    font_size: int = 14
    action: Action | None = None

    @property
    def is_empty(self) -> bool:
        return self.action is None and not self.label and not self.icon

    def to_dict(self) -> dict[str, Any]:
        data: dict[str, Any] = {
            "label": self.label,
            "icon": self.icon,
            "font_size": self.font_size,
        }
        if self.action is not None:
            data["action"] = self.action.to_dict()
        return data

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "ButtonConfig":
        return cls(
            label=data.get("label", ""),
            icon=data.get("icon", ""),
            font_size=int(data.get("font_size", 14)),
            action=action_from_dict(data.get("action")),
        )


@dataclass
class Page:
    name: str = "Main"
    buttons: dict[int, ButtonConfig] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return {
            "name": self.name,
            "buttons": {str(k): b.to_dict() for k, b in self.buttons.items()},
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "Page":
        buttons = {
            int(k): ButtonConfig.from_dict(v)
            for k, v in (data.get("buttons") or {}).items()
        }
        return cls(name=data.get("name", "Main"), buttons=buttons)


@dataclass
class Profile:
    """A named set of pages — the unit users switch between and share."""

    name: str = "Default"
    active_page: int = 0
    pages: list[Page] = field(default_factory=lambda: [Page()])

    def current_page(self) -> Page:
        if not self.pages:
            self.pages.append(Page())
        self.active_page = max(0, min(self.active_page, len(self.pages) - 1))
        return self.pages[self.active_page]

    def to_dict(self) -> dict[str, Any]:
        return {
            "name": self.name,
            "active_page": self.active_page,
            "pages": [p.to_dict() for p in self.pages],
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "Profile":
        pages = [Page.from_dict(p) for p in (data.get("pages") or [])] or [Page()]
        return cls(
            name=data.get("name", "Default"),
            active_page=int(data.get("active_page", 0)),
            pages=pages,
        )

    def clone(self, new_name: str | None = None) -> "Profile":
        """A deep copy (via serialization), optionally renamed."""
        copy = Profile.from_dict(self.to_dict())
        if new_name is not None:
            copy.name = new_name
        return copy


@dataclass
class DeckState:
    """Persisted state for one physical deck, keyed by serial number."""

    serial: str
    deck_type: str = ""
    name: str = ""
    brightness: int = DEFAULT_BRIGHTNESS
    dim_on_lock: bool = False
    active_profile: int = 0
    profiles: list[Profile] = field(default_factory=lambda: [Profile()])

    @property
    def display_name(self) -> str:
        return self.name or self.deck_type or self.serial

    def current_profile(self) -> Profile:
        if not self.profiles:
            self.profiles.append(Profile())
        self.active_profile = max(0, min(self.active_profile, len(self.profiles) - 1))
        return self.profiles[self.active_profile]

    def current_page(self) -> Page:
        return self.current_profile().current_page()

    def to_dict(self) -> dict[str, Any]:
        return {
            "deck_type": self.deck_type,
            "name": self.name,
            "brightness": self.brightness,
            "dim_on_lock": self.dim_on_lock,
            "active_profile": self.active_profile,
            "profiles": [p.to_dict() for p in self.profiles],
        }

    @classmethod
    def from_dict(cls, serial: str, data: dict[str, Any]) -> "DeckState":
        if "profiles" in data:
            profiles = [Profile.from_dict(p) for p in (data.get("profiles") or [])]
        else:
            # Legacy schema (v1): pages lived directly under the deck.
            pages = [Page.from_dict(p) for p in (data.get("pages") or [])] or [Page()]
            profiles = [Profile(name="Default", active_page=int(data.get("active_page", 0)), pages=pages)]
        if not profiles:
            profiles = [Profile()]
        return cls(
            serial=serial,
            deck_type=data.get("deck_type", ""),
            name=data.get("name", ""),
            brightness=int(data.get("brightness", DEFAULT_BRIGHTNESS)),
            dim_on_lock=bool(data.get("dim_on_lock", False)),
            active_profile=int(data.get("active_profile", 0)),
            profiles=profiles,
        )
