"""Render a ButtonConfig to both a hardware key image and a GUI preview.

The same PIL compositing is used for both targets so the on-screen tile is a
faithful preview of what appears on the physical key. Icons may be a themed
icon name (symbolic icons are recolored to the foreground), an SVG file, or a
raster image file — all are rasterized into the key image.
"""

from __future__ import annotations

import io
import logging
import time
import warnings
from functools import lru_cache

import gi
from PIL import Image, ImageDraw, ImageFont
from StreamDeck.ImageHelpers import PILHelper

gi.require_version("Gtk", "4.0")
gi.require_version("Gdk", "4.0")
gi.require_version("Gsk", "4.0")
gi.require_version("Graphene", "1.0")
gi.require_version("Adw", "1")
from gi.repository import Adw, Gdk, GLib, Gio, Graphene, Gsk, Gtk  # noqa: E402

from veranda.models import ButtonConfig  # noqa: E402

log = logging.getLogger(__name__)

FALLBACK_BG = (28, 28, 30)
BADGE_BG = (224, 64, 64)
BADGE_FG = "white"
PREVIEW_SIZE = 96
RASTER_EXTS = (".png", ".jpg", ".jpeg", ".webp", ".gif", ".bmp")

_THEME_BG: tuple[int, int, int] | None = None


def _extract_theme_bg() -> tuple[int, int, int]:
    """Read the GNOME theme's view background color (light/dark aware)."""
    try:
        with warnings.catch_warnings():
            warnings.simplefilter("ignore", DeprecationWarning)
            ok, rgba = Gtk.Box().get_style_context().lookup_color("view_bg_color")
        if ok:
            return (round(rgba.red * 255), round(rgba.green * 255), round(rgba.blue * 255))
    except Exception:  # noqa: BLE001
        pass
    try:
        if Adw.StyleManager.get_default().get_dark():
            return (29, 29, 32)
        return (250, 250, 250)
    except Exception:  # noqa: BLE001
        return FALLBACK_BG


def theme_background() -> tuple[int, int, int]:
    global _THEME_BG
    if _THEME_BG is None:
        _THEME_BG = _extract_theme_bg()
    return _THEME_BG


def invalidate_theme_cache() -> None:
    """Drop the cached theme color + recolored icons (call on theme change)."""
    global _THEME_BG
    _THEME_BG = None
    _rasterize_named.cache_clear()


def accent_background() -> tuple[int, int, int]:
    """The live GNOME accent color as an (r, g, b) tuple."""
    try:
        rgba = Adw.StyleManager.get_default().get_property("accent-color-rgba")
        return (round(rgba.red * 255), round(rgba.green * 255), round(rgba.blue * 255))
    except Exception:  # noqa: BLE001
        return (53, 132, 228)


def resolve_background(value: str) -> tuple[int, int, int]:
    if value == "accent":
        return accent_background()
    return _parse_hex(value) or theme_background()


def _parse_hex(value: str) -> tuple[int, int, int] | None:
    if not value:
        return None
    s = value.lstrip("#")
    if len(s) == 6:
        try:
            return (int(s[0:2], 16), int(s[2:4], 16), int(s[4:6], 16))
        except ValueError:
            return None
    return None


def _contrast(bg: tuple[int, int, int]) -> tuple[int, int, int]:
    """A readable foreground (near-black on light, near-white on dark)."""
    luminance = 0.2126 * bg[0] + 0.7152 * bg[1] + 0.0722 * bg[2]
    return (24, 24, 24) if luminance > 140 else (240, 240, 240)


@lru_cache(maxsize=16)
def _font(size: int) -> ImageFont.FreeTypeFont | ImageFont.ImageFont:
    """A scalable font at ``size`` px, falling back to PIL's default."""
    for name in ("DejaVuSans.ttf", "Roboto-Regular.ttf", "FreeSans.ttf"):
        try:
            return ImageFont.truetype(name, size)
        except OSError:
            continue
    try:
        return ImageFont.load_default(size=size)
    except TypeError:  # very old Pillow without size kwarg
        return ImageFont.load_default()


def _node_to_pil(node, size: int) -> Image.Image | None:
    """Rasterize a GSK render node to an RGBA PIL image via the Cairo renderer."""
    if node is None:
        return None
    display = Gdk.Display.get_default()
    renderer = Gsk.CairoRenderer.new()
    try:
        renderer.realize_for_display(display)
        texture = renderer.render_texture(node, Graphene.Rect().init(0, 0, size, size))
    finally:
        renderer.unrealize()
    png = texture.save_to_png_bytes()
    return Image.open(io.BytesIO(png.get_data())).convert("RGBA")


def _is_symbolic(icon: str) -> bool:
    return icon.endswith("-symbolic") or icon.endswith("-symbolic.svg")


def _paintable_to_pil(paintable, icon: str, size: int, color) -> Image.Image | None:
    snapshot = Gtk.Snapshot.new()
    if _is_symbolic(icon) and hasattr(paintable, "snapshot_symbolic"):
        rgba = Gdk.RGBA()
        rgba.red, rgba.green, rgba.blue, rgba.alpha = (
            color[0] / 255, color[1] / 255, color[2] / 255, 1.0,
        )
        paintable.snapshot_symbolic(snapshot, size, size, [rgba])
    else:
        paintable.snapshot(snapshot, size, size)
    return _node_to_pil(snapshot.to_node(), size)


@lru_cache(maxsize=256)
def _rasterize_named(icon: str, size: int, color) -> Image.Image | None:
    theme = Gtk.IconTheme.get_for_display(Gdk.Display.get_default())
    if not theme.has_icon(icon):
        return None  # avoid rendering the "missing image" fallback glyph
    paintable = theme.lookup_icon(
        icon, None, size, 1, Gtk.TextDirection.NONE, Gtk.IconLookupFlags.PRELOAD
    )
    if paintable is None:
        return None
    try:
        return _paintable_to_pil(paintable, icon, size, color)
    except Exception as exc:  # noqa: BLE001
        log.debug("named icon render failed for %s: %s", icon, exc)
        return None


def _rasterize_file(path: str, size: int) -> Image.Image | None:
    lower = path.lower()
    if lower.endswith(".svg"):
        try:
            paintable = Gtk.IconPaintable.new_for_file(Gio.File.new_for_path(path), size, 1)
            return _paintable_to_pil(paintable, path, size, (240, 240, 240))
        except Exception as exc:  # noqa: BLE001
            log.debug("svg render failed for %s: %s", path, exc)
            return None
    try:
        with Image.open(path) as raw:
            icon = raw.convert("RGBA")
        icon.thumbnail((size, size), Image.LANCZOS)
        return icon
    except (OSError, ValueError) as exc:
        log.debug("raster icon load failed for %s: %s", path, exc)
        return None


def rasterize_icon(icon: str, size: int, color=(240, 240, 240)) -> Image.Image | None:
    """Render any icon spec to an RGBA image; ``color`` recolors symbolic icons."""
    if not icon:
        return None
    if "/" in icon or icon.lower().endswith(RASTER_EXTS) or icon.lower().endswith(".svg"):
        return _rasterize_file(icon, size)
    return _rasterize_named(icon, size, tuple(color))


@lru_cache(maxsize=32)
def _gif_frames(path: str):
    """Return ((rgba_frame, duration_ms), ...) for an animated GIF, else None."""
    try:
        frames = []
        with Image.open(path) as im:
            if not getattr(im, "is_animated", False) or im.n_frames <= 1:
                return None
            for i in range(im.n_frames):
                im.seek(i)
                duration = im.info.get("duration") or 100
                frames.append((im.convert("RGBA").copy(), int(duration)))
        return tuple(frames)
    except Exception:  # noqa: BLE001
        return None


def is_animated_icon(icon: str) -> bool:
    return bool(icon) and "/" in icon and icon.lower().endswith(".gif") and _gif_frames(icon) is not None


def _cover(img: Image.Image, size: tuple[int, int]) -> Image.Image:
    iw, ih = img.size
    w, h = size
    scale = max(w / iw, h / ih)
    nw, nh = max(1, int(iw * scale)), max(1, int(ih * scale))
    resized = img.resize((nw, nh), Image.LANCZOS)
    x, y = (nw - w) // 2, (nh - h) // 2
    return resized.crop((x, y, x + w, y + h))


def _gif_frame_at(path: str, size: tuple[int, int], t: float) -> Image.Image | None:
    frames = _gif_frames(path)
    if not frames:
        return None
    total = sum(d for _, d in frames) or 1
    ms = (t * 1000) % total
    acc = 0
    for frame, duration in frames:
        acc += duration
        if ms < acc:
            return _cover(frame, size)
    return _cover(frames[-1][0], size)


def _draw_badge(image: Image.Image, text: str) -> None:
    """Draw a small count/badge pill in the top-right corner (notification style)."""
    width, height = image.size
    draw = ImageDraw.Draw(image)
    font = _font(max(9, int(height * 0.26)))
    pad = max(2, int(height * 0.04))
    tb = draw.textbbox((0, 0), text, font=font)
    tw, th = tb[2] - tb[0], tb[3] - tb[1]
    diameter = max(tw, th) + 2 * pad
    w_pill = max(diameter, tw + 2 * pad)
    x1, y1 = width - w_pill - pad, pad
    x2, y2 = width - pad, pad + diameter
    draw.rounded_rectangle((x1, y1, x2, y2), radius=diameter // 2, fill=BADGE_BG)
    draw.text(((x1 + x2) / 2, (y1 + y2) / 2), text, font=font, anchor="mm", fill=BADGE_FG)


def _compose(size: tuple[int, int], button: ButtonConfig) -> Image.Image:
    """Build an RGB key image: optional icon + a text label (+ live badge)."""
    width, height = size
    bg = resolve_background(button.background)
    fg = _contrast(bg)
    image = Image.new("RGB", size, bg)

    # A "Special Button" (DYNAMIC action) can override icon/label and add a badge.
    icon_spec = button.icon
    label = button.label
    badge = None
    action = button.action
    if action is not None and getattr(action, "DYNAMIC", False):
        icon_spec = action.display_icon() or button.icon
        text = action.display_text()
        if text is not None:
            label = text
        badge = action.badge_text()

    has_label = bool(label)
    label_band = int(height * 0.30) if has_label else 0

    animated = _gif_frame_at(icon_spec, size, time.monotonic()) if icon_spec else None
    if animated is not None:
        image.paste(animated, (0, 0), animated)  # full-bleed animation
    elif icon_spec:
        avail_h = height - label_band
        target = max(8, int(min(width, avail_h) * 0.80))
        icon = rasterize_icon(icon_spec, target, fg)
        if icon is not None:
            x = (width - icon.width) // 2
            y = (avail_h - icon.height) // 2
            image.paste(icon, (x, y), icon)

    if has_label:
        draw = ImageDraw.Draw(image)
        scale = height / PREVIEW_SIZE
        font = _font(max(8, int(button.font_size * scale)))
        if icon_spec:
            baseline = height - int(height * 0.06)
            anchor = "ms"
        else:
            baseline = height // 2
            anchor = "mm"
        draw.text((width / 2, baseline), label, font=font, anchor=anchor, fill=fg)

    if badge:
        _draw_badge(image, badge)

    return image


def render_native(deck, button: ButtonConfig) -> bytes:
    """Render to the device's native key format (bytes ready for set_key_image)."""
    size = deck.key_image_format()["size"]
    image = _compose(size, button)
    return PILHelper.to_native_key_format(deck, image)


def blank_native(deck) -> bytes:
    size = deck.key_image_format()["size"]
    return PILHelper.to_native_key_format(deck, Image.new("RGB", size, theme_background()))


def _round_corners(image: Image.Image, radius: int) -> Image.Image:
    """Apply a rounded-rectangle alpha mask (GUI only; hardware keys are square)."""
    mask = Image.new("L", image.size, 0)
    ImageDraw.Draw(mask).rounded_rectangle(
        (0, 0, image.size[0] - 1, image.size[1] - 1), radius=radius, fill=255
    )
    image.putalpha(mask)
    return image


def render_preview_texture(button: ButtonConfig, size: int = PREVIEW_SIZE) -> Gdk.Texture:
    """Render a GUI preview as a Gdk.Texture mirroring the hardware key."""
    image = _compose((size, size), button).convert("RGBA")
    image = _round_corners(image, int(size * 0.16))
    data = GLib.Bytes.new(image.tobytes())
    return Gdk.MemoryTexture.new(
        image.width,
        image.height,
        Gdk.MemoryFormat.R8G8B8A8,
        data,
        image.width * 4,
    )
