"""One-off processor for the user-supplied brand icon (a cat reading a book,
replacing the programmatically-drawn document+magnifying-glass mark from
generate_icon.py).

The source export has the squircle icon centered on a canvas much wider
than it is tall, with the "transparent" area outside the squircle baked in
as an opaque checkerboard pattern rather than real alpha -- so this can't
just be cropped by alpha bounding box. Instead: find the squircle's own
bounding square via color saturation (the orange/red gradient border and
green cat are strongly saturated; the checkerboard squares and the book's
white pages are not, so a saturation threshold isolates the squircle's true
extent), crop to it, then stamp a clean rounded-rect alpha mask over that
square so the corners become properly transparent regardless of whatever
background pixels are sitting there.

Run once, by hand, against the source PNG (not part of the normal build):
    uv run python packaging/process_brand_icon.py <path-to-source.png>
"""
from __future__ import annotations

import sys
from pathlib import Path

from PIL import Image, ImageDraw

ASSETS_DIR = Path(__file__).parent.parent / "src" / "smartdoc" / "presentation" / "assets"
ICO_SIZES = (16, 24, 32, 48, 64, 128, 256)
LOGO_SIZE = 512
CORNER_RADIUS_RATIO = 0.22  # matches generate_icon.py's own squircle radius
SATURATION_THRESHOLD = 18
CROP_MARGIN = 6


def _saturation_bbox(img: Image.Image) -> tuple[int, int, int, int]:
    rgb = img.convert("RGB")
    w, h = rgb.size
    px = rgb.load()
    min_x, min_y, max_x, max_y = w, h, 0, 0
    step = 3
    for y in range(0, h, step):
        for x in range(0, w, step):
            r, g, b = px[x, y]
            if max(r, g, b) - min(r, g, b) > SATURATION_THRESHOLD:
                min_x, max_x = min(min_x, x), max(max_x, x)
                min_y, max_y = min(min_y, y), max(max_y, y)
    return min_x, min_y, max_x, max_y


def _rounded_mask(size: int, radius_ratio: float) -> Image.Image:
    mask = Image.new("L", (size, size), 0)
    draw = ImageDraw.Draw(mask)
    draw.rounded_rectangle([0, 0, size - 1, size - 1], radius=int(size * radius_ratio), fill=255)
    return mask


def process(source_path: Path) -> Image.Image:
    source = Image.open(source_path).convert("RGBA")
    min_x, min_y, max_x, max_y = _saturation_bbox(source)

    side = max(max_x - min_x, max_y - min_y) + 2 * CROP_MARGIN
    cx, cy = (min_x + max_x) // 2, (min_y + max_y) // 2
    left, top = cx - side // 2, cy - side // 2
    cropped = source.crop((left, top, left + side, top + side))

    mask = _rounded_mask(side, CORNER_RADIUS_RATIO)
    transparent = Image.new("RGBA", (side, side), (0, 0, 0, 0))
    transparent.paste(cropped, (0, 0), mask)
    return transparent


if __name__ == "__main__":
    if len(sys.argv) != 2:
        print("usage: process_brand_icon.py <path-to-source.png>")
        sys.exit(1)

    icon = process(Path(sys.argv[1]))

    ASSETS_DIR.mkdir(parents=True, exist_ok=True)
    ico_path = ASSETS_DIR / "app_icon.ico"
    logo_path = ASSETS_DIR / "brand_logo.png"
    preview_path = Path(__file__).parent / "icon_preview.png"

    icon.save(ico_path, sizes=[(s, s) for s in ICO_SIZES])
    icon.resize((LOGO_SIZE, LOGO_SIZE), Image.LANCZOS).save(logo_path)
    icon.resize((256, 256), Image.LANCZOS).save(preview_path)

    print("wrote", ico_path)
    print("wrote", logo_path)
    print("wrote", preview_path)
