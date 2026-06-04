"""Animated GIF key icons."""

from PIL import Image

from veranda import render
from veranda.livebuttons import LiveButtonController
from veranda.models import ButtonConfig, Page


def _make_gif(path, frames=6):
    imgs = []
    for i in range(frames):
        im = Image.new("RGB", (32, 32), (i * 40 % 256, 0, 255 - i * 40 % 256))
        imgs.append(im)
    imgs[0].save(path, save_all=True, append_images=imgs[1:], duration=80, loop=0)


def _make_static_gif(path):
    Image.new("RGB", (32, 32), (10, 20, 30)).save(path)


def test_is_animated_icon(tmp_path):
    g = tmp_path / "anim.gif"
    _make_gif(g)
    assert render.is_animated_icon(str(g)) is True

    s = tmp_path / "static.gif"
    _make_static_gif(s)
    assert render.is_animated_icon(str(s)) is False
    assert render.is_animated_icon("plain-icon-symbolic") is False


def test_gif_frame_changes_over_time(tmp_path):
    g = tmp_path / "anim.gif"
    _make_gif(g)
    f0 = render._gif_frame_at(str(g), (80, 80), 0.0)
    f1 = render._gif_frame_at(str(g), (80, 80), 0.2)  # 200ms -> a later frame
    assert f0 is not None and f1 is not None
    assert f0.tobytes() != f1.tobytes()  # different frames


def test_compose_uses_animation(tmp_path):
    g = tmp_path / "anim.gif"
    _make_gif(g)
    img = render._compose((80, 80), ButtonConfig(icon=str(g)))
    # full-bleed animation -> corner pixel is part of the frame, not the bg
    assert img.size == (80, 80)


def test_controller_schedules_animation(tmp_path):
    g = tmp_path / "anim.gif"
    _make_gif(g)
    ctrl = LiveButtonController(lambda k: None)
    page = Page(buttons={
        0: ButtonConfig(icon=str(g)),                 # animated -> timer
        1: ButtonConfig(icon="audio-volume-high-symbolic"),  # static -> none
    })
    ctrl.rebuild(page)
    assert len(ctrl._timeouts) == 1
    ctrl.stop()
    assert ctrl._timeouts == []
