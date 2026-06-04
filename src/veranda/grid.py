"""The grid of tiles laid out to match a deck's physical key geometry."""

from __future__ import annotations

from typing import Callable

import gi

gi.require_version("Gtk", "4.0")
from gi.repository import Gtk  # noqa: E402

from veranda.deck import DeckInfo  # noqa: E402
from veranda.models import ActionItem, ButtonConfig, Page  # noqa: E402
from veranda.tile import DeckTile  # noqa: E402


class DeckGrid(Gtk.Box):
    """Renders a deck's keys as an addressable NxM grid of tiles."""

    def __init__(
        self,
        on_drop: Callable[[int, ActionItem], None],
        on_select: Callable[[int], None],
        on_move: Callable[[int, int], None],
    ) -> None:
        super().__init__(
            orientation=Gtk.Orientation.VERTICAL,
            halign=Gtk.Align.CENTER,
            valign=Gtk.Align.CENTER,
            hexpand=True,
            vexpand=True,
        )
        self._on_drop = on_drop
        self._on_select = on_select
        self._on_move = on_move
        self._tiles: dict[int, DeckTile] = {}
        self._selected: int | None = None

        self._grid = Gtk.Grid(
            row_spacing=14,
            column_spacing=14,
            row_homogeneous=True,
            column_homogeneous=True,
        )
        self.append(self._grid)

    def build(self, info: DeckInfo, page: Page) -> None:
        """(Re)create tiles for ``info`` and fill them from ``page``."""
        child = self._grid.get_first_child()
        while child is not None:
            nxt = child.get_next_sibling()
            self._grid.remove(child)
            child = nxt
        self._tiles.clear()
        self._selected = None

        key = 0
        for row in range(info.rows):
            for col in range(info.cols):
                tile = DeckTile(key, self._on_drop, self._on_select, self._on_move)
                self._grid.attach(tile, col, row, 1, 1)
                self._tiles[key] = tile
                tile.set_button(page.buttons.get(key))
                key += 1

    def update_key(self, key: int, button: ButtonConfig | None) -> None:
        tile = self._tiles.get(key)
        if tile is not None:
            tile.set_button(button)

    def select(self, key: int | None) -> None:
        if self._selected is not None and self._selected in self._tiles:
            self._tiles[self._selected].set_selected(False)
        self._selected = key
        if key is not None and key in self._tiles:
            self._tiles[key].set_selected(True)
