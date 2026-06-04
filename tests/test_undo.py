"""UndoStack behavior."""

from veranda.undo import UndoStack


def test_record_undo_redo():
    s = UndoStack()
    assert not s.can_undo() and not s.can_redo()
    s.record("A")          # before mutation that produced B
    # current is now "B"
    assert s.can_undo()
    prev = s.undo("B")     # back to A
    assert prev == "A" and s.can_redo()
    nxt = s.redo("A")      # forward to B
    assert nxt == "B" and s.can_undo()


def test_record_clears_redo():
    s = UndoStack()
    s.record("A")
    s.undo("B")            # redo now has B
    assert s.can_redo()
    s.record("C")          # a new edit clears redo
    assert not s.can_redo()


def test_limit():
    s = UndoStack(limit=3)
    for x in "ABCDE":
        s.record(x)
    assert len(s._undo) == 3 and s._undo == ["C", "D", "E"]


def test_empty_undo_redo_return_none():
    s = UndoStack()
    assert s.undo("x") is None
    assert s.redo("x") is None
