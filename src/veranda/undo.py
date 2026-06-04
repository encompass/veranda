"""A small undo/redo stack of opaque state snapshots."""

from __future__ import annotations

from typing import Any


class UndoStack:
    """Records snapshots before each mutation; undo/redo swap with the current.

    Snapshots are opaque (the caller produces and applies them), so this works
    for any serializable state. ``undo``/``redo`` take the *current* snapshot so
    the inverse operation can be reconstructed.
    """

    def __init__(self, limit: int = 50) -> None:
        self._undo: list[Any] = []
        self._redo: list[Any] = []
        self._limit = limit

    def record(self, snapshot: Any) -> None:
        self._undo.append(snapshot)
        if len(self._undo) > self._limit:
            self._undo.pop(0)
        self._redo.clear()

    def can_undo(self) -> bool:
        return bool(self._undo)

    def can_redo(self) -> bool:
        return bool(self._redo)

    def undo(self, current: Any) -> Any | None:
        if not self._undo:
            return None
        self._redo.append(current)
        return self._undo.pop()

    def redo(self, current: Any) -> Any | None:
        if not self._redo:
            return None
        self._undo.append(current)
        return self._redo.pop()

    def clear(self) -> None:
        self._undo.clear()
        self._redo.clear()
