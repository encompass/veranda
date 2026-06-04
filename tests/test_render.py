"""Rendering: backgrounds, contrast, badges, dynamic widgets."""

from veranda import render
from veranda.models import ButtonConfig
from veranda.actions.special.widget import LiveWidget


def test_parse_hex():
    assert render._parse_hex("#ff0000") == (255, 0, 0)
    assert render._parse_hex("") is None
    assert render._parse_hex("nope") is None


def test_contrast():
    assert render._contrast((255, 255, 255)) == (24, 24, 24)
    assert render._contrast((10, 10, 10)) == (240, 240, 240)


def test_theme_and_accent_background():
    assert len(render.theme_background()) == 3
    assert len(render.accent_background()) == 3
    assert render.resolve_background("#3584e4") == (53, 132, 228)
    assert render.resolve_background("accent") == render.accent_background()
    assert render.resolve_background("") == render.theme_background()


def test_compose_uses_custom_background():
    img = render._compose((80, 80), ButtonConfig(label="x", background="#3584e4"))
    assert img.getpixel((2, 2)) == (53, 132, 228)


def test_compose_dynamic_badge():
    class Badge(LiveWidget):
        TYPE_ID = "t"
        def display_icon(self): return "mail-unread-symbolic"
        def display_text(self): return ""
        def badge_text(self): return "9"

    img = render._compose((96, 96), ButtonConfig(action=Badge()))
    # top-right pixel should be the red badge fill
    px = img.getpixel((90, 8))
    assert px[0] > 150 and px[1] < 120


def test_rasterize_unknown_icon_is_none():
    assert render.rasterize_icon("definitely-not-an-icon-xyz", 48) is None


def test_preview_texture_size():
    tex = render.render_preview_texture(ButtonConfig(label="Hi"), size=64)
    assert tex.get_width() == 64 and tex.get_height() == 64
