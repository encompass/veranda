"""Page reordering."""

from veranda.models import Page, Profile


def _profile():
    return Profile(name="P", pages=[Page(name="A"), Page(name="B"), Page(name="C")])


def test_move_page_forward():
    p = _profile()
    assert p.move_page(0, 2) is True
    assert [pg.name for pg in p.pages] == ["B", "C", "A"]
    assert p.active_page == 2  # moved page is active


def test_move_page_backward():
    p = _profile()
    p.active_page = 0
    assert p.move_page(2, 0) is True
    assert [pg.name for pg in p.pages] == ["C", "A", "B"]
    assert p.active_page == 0


def test_move_page_invalid():
    p = _profile()
    assert p.move_page(0, 0) is False
    assert p.move_page(5, 1) is False
    assert [pg.name for pg in p.pages] == ["A", "B", "C"]
