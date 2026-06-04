"""Base class and runtime context for button actions."""

from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING, Any, Callable

if TYPE_CHECKING:
    from gi.repository import Gtk

    from veranda.deck import DeckManager
    from veranda.input_backend import InputBackend
    from veranda.models import ButtonConfig


@dataclass
class ActionContext:
    """Everything an action needs at execution time.

    Constructed by the dispatcher on the GTK main thread and handed to
    :meth:`Action.execute`. Actions should treat the attributes as
    read-only handles into the running application.
    """

    serial: str
    """Serial number of the deck the press came from."""

    key: int
    """Physical key index that was pressed."""

    deck_manager: "DeckManager"
    """Live device layer — for brightness, re-rendering, etc."""

    input_backend: "InputBackend"
    """uinput-backed keyboard injection (Wayland-safe)."""

    switch_page: Callable[[str, int], None]
    """Call ``switch_page(serial, page_index)`` to change the active page."""

    switch_profile: Callable[[str, str], bool]
    """Call ``switch_profile(serial, name_or_index)`` to activate a profile.

    Accepts a profile name (case-insensitive) or a 0-based index as a string;
    returns ``True`` if a matching profile was found."""

    set_brightness: Callable[[str, int], None]
    """Call ``set_brightness(serial, percent)`` to change and persist brightness."""

    notify: Callable[[str], None]
    """Surface a transient, user-visible message (e.g. a toast)."""


class Action:
    """Abstract base for all bindable actions.

    Subclasses declare their identity via the class attributes below and
    implement :meth:`execute`. Parameters are stored in ``self.params`` so
    that serialization is uniform across every action type.
    """

    #: Stable identifier persisted in the config file.
    TYPE_ID: str = ""
    #: Human-readable name shown in the action library.
    NAME: str = ""
    #: One-line description shown as a subtitle in the library.
    DESCRIPTION: str = ""
    #: Symbolic icon name used in the library and as a tile's default icon.
    ICON: str = "application-x-executable-symbolic"
    #: Category heading the action is grouped under in the library.
    CATEGORY: str = "General"
    #: True for "Special Buttons" whose displayed image updates over time.
    DYNAMIC: bool = False

    def __init__(self, params: dict[str, Any] | None = None) -> None:
        self.params: dict[str, Any] = dict(params or {})

    # -- dynamic display (Special Buttons; defaults keep static actions inert) --

    def display_icon(self) -> str | None:
        """Live icon override (None → use the button's static icon)."""
        return None

    def display_text(self) -> str | None:
        """Live main text (None → use the button's static label)."""
        return None

    def badge_text(self) -> str | None:
        """Small corner-badge text, e.g. an unread count (None → no badge)."""
        return None

    # -- presentation -----------------------------------------------------

    def default_label(self) -> str:
        """Initial text label when this action is first dropped on a tile."""
        return self.NAME

    def default_icon(self) -> str:
        """Initial icon (symbolic name) when first dropped on a tile."""
        return self.ICON

    def summary(self) -> str:
        """Short one-line description of the current configuration."""
        return self.NAME

    # -- serialization ----------------------------------------------------

    def to_dict(self) -> dict[str, Any]:
        return {"type": self.TYPE_ID, **self.params}

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "Action":
        params = {k: v for k, v in data.items() if k != "type"}
        return cls(params)

    # -- editing ----------------------------------------------------------

    def build_editor_rows(
        self, button: "ButtonConfig", on_change: Callable[[], None]
    ) -> list["Gtk.Widget"]:
        """Return Adw rows that edit this action's parameters.

        ``button`` is the owning button, so an action may also set its label
        or icon (e.g. when a concrete choice is made). ``on_change`` must be
        invoked whenever anything changes so the editor persists, re-renders,
        and re-syncs the label/icon fields. Default: no parameters.
        """
        return []

    # -- runtime ----------------------------------------------------------

    def execute(self, ctx: ActionContext) -> None:  # pragma: no cover - abstract
        raise NotImplementedError
