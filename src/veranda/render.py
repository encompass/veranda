"""Render a ButtonConfig to both a hardware key image and a GUI preview.

The same PIL compositing is used for both targets so the on-screen tile is a
faithful preview of what appears on the physical key. Icons may be a themed
icon name (symbolic icons are recolored to the foreground), an SVG file, or a
raster image file — all are rasterized into the key image.
"""

from __future__ import annotations

import io
import logging
from functools import lru_cache

import gi
from PIL import Image, ImageDraw, ImageFont
from StreamDeck.ImageHelpers import PILHelper

gi.require_version("Gtk", "4.0")
gi.require_version("Gdk", "4.0")
gi.require_version("Gsk", "4.0")
gi.require_version("Graphene", "1.0")
from gi.repository import Gdk, GLib, Gio, Graphene, Gsk, Gtk  # noqa: E402

from veranda.models import ButtonConfig  # noqa: E402

log = logging.getLogger(__name__)

BACKGROUND = (28, 28, 30)
FOREGROUND = "white"
ICON_COLOR = (240, 240, 240)
PREVIEW_SIZE = 96
RASTER_EXTS = (".png", ".jpg", ".jpeg", ".webp", ".gif", ".bmp")


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


def _paintable_to_pil(paintable, icon: str, size: int) -> Image.Image | None:
    snapshot = Gtk.Snapshot.new()
    if _is_symbolic(icon) and hasattr(paintable, "snapshot_symbolic"):
        color = Gdk.RGBA()
        color.red, color.green, color.blue, color.alpha = (
            ICON_COLOR[0] / 255,
            ICON_COLOR[1] / 255,
            ICON_COLOR[2] / 255,
            1.0,
        )
        paintable.snapshot_symbolic(snapshot, size, size, [color])
    else:
        paintable.snapshot(snapshot, size, size)
    return _node_to_pil(snapshot.to_node(), size)


@lru_cache(maxsize=128)
def _rasterize_named(icon: str, size: int) -> Image.Image | None:
    theme = Gtk.IconTheme.get_for_display(Gdk.Display.get_default())
    if not theme.has_icon(icon):
        return None  # avoid rendering the "missing image" fallback glyph
    paintable = theme.lookup_icon(
        icon, None, size, 1, Gtk.TextDirection.NONE, Gtk.IconLookupFlags.PRELOAD
    )
    if paintable is None:
        return None
    try:
        return _paintable_to_pil(paintable, icon, size)
    except Exception as exc:  # noqa: BLE001
        log.debug("named icon render failed for %s: %s", icon, exc)
        return None


def _rasterize_file(path: str, size: int) -> Image.Image | None:
    lower = path.lower()
    if lower.endswith(".svg"):
        try:
            paintable = Gtk.IconPaintable.new_for_file(Gio.File.new_for_path(path), size, 1)
            return _paintable_to_pil(paintable, path, size)
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


def rasterize_icon(icon: str, size: int) -> Image.Image | None:
    """Render any icon spec (name, SVG path, or raster path) to an RGBA image."""
    if not icon:
        return None
    if "/" in icon or icon.lower().endswith(RASTER_EXTS) or icon.lower().endswith(".svg"):
        return _rasterize_file(icon, size)
    return _rasterize_named(icon, size)


def _compose(size: tuple[int, int], button: ButtonConfig) -> Image.Image:
    """Build an RGB key image: optional icon + a text label."""
    width, height = size
    image = Image.new("RGB", size, BACKGROUND)

    has_label = bool(button.label)
    label_band = int(height * 0.30) if has_label else 0

    if button.icon:
        avail_h = height - label_band
        target = max(8, int(min(width, avail_h) * 0.80))
        icon = rasterize_icon(button.icon, target)
        if icon is not None:
            x = (width - icon.width) // 2
            y = (avail_h - icon.height) // 2
            image.paste(icon, (x, y), icon)

    if has_label:
        draw = ImageDraw.Draw(image)
        scale = height / PREVIEW_SIZE
        font = _font(max(8, int(button.font_size * scale)))
        if button.icon:
            baseline = height - int(height * 0.06)
            anchor = "ms"
        else:
            baseline = height // 2
            anchor = "mm"
        draw.text((width / 2, baseline), button.label, font=font, anchor=anchor, fill=FOREGROUND)

    return image


def render_native(deck, button: ButtonConfig) -> bytes:
    """Render to the device's native key format (bytes ready for set_key_image)."""
    size = deck.key_image_format()["size"]
    image = _compose(size, button)
    return PILHelper.to_native_key_format(deck, image)


def blank_native(deck) -> bytes:
    size = deck.key_image_format()["size"]
    return PILHelper.to_native_key_format(deck, Image.new("RGB", size, BACKGROUND))


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
