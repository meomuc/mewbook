"""Generates the SmartDoc Library app icon: a document with a folded corner
(the "smart doc" part) plus a magnifying glass (the fast full-text search
that's the app's whole reason for existing), in the same flat, minimal
palette as the running app (see presentation/theme.py's LIGHT colors).

Drawn programmatically with Pillow rather than as an SVG asset -- no new
dependency needed (no SVG rasterizer), and a hand-drawn geometric mark like
this doesn't lose anything by being built straight from primitives at high
resolution and downsampled for the smaller ICO sizes.
"""
from __future__ import annotations

import math
from pathlib import Path

from PIL import Image, ImageDraw

SIZE = 1024

BG_COLOR = (74, 144, 217, 255)     # #4a90d9 -- theme.LIGHT.accent
PAGE_COLOR = (255, 255, 255, 255)  # #ffffff -- theme.LIGHT.surface
FOLD_COLOR = (200, 224, 248, 255)  # a shade between accent and surface, for the folded corner
LINE_COLOR = (74, 144, 217, 255)   # text lines on the page, echoing the accent
GLASS_COLOR = (26, 26, 26, 255)    # #1a1a1a -- theme.LIGHT.text, for the magnifying glass


def build_icon() -> Image.Image:
    img = Image.new("RGBA", (SIZE, SIZE), (0, 0, 0, 0))
    draw = ImageDraw.Draw(img)

    # Rounded-square background, Windows-11-style.
    margin = int(SIZE * 0.045)
    draw.rounded_rectangle(
        [margin, margin, SIZE - margin, SIZE - margin],
        radius=int(SIZE * 0.22),
        fill=BG_COLOR,
    )

    # Document with a folded top-right corner.
    page_left = int(SIZE * 0.26)
    page_top = int(SIZE * 0.20)
    page_right = int(SIZE * 0.64)
    page_bottom = int(SIZE * 0.68)
    fold = int(SIZE * 0.13)

    page_points = [
        (page_left, page_top),
        (page_right - fold, page_top),
        (page_right, page_top + fold),
        (page_right, page_bottom),
        (page_left, page_bottom),
    ]
    draw.polygon(page_points, fill=PAGE_COLOR)
    draw.polygon(
        [(page_right - fold, page_top), (page_right, page_top + fold), (page_right - fold, page_top + fold)],
        fill=FOLD_COLOR,
    )

    # A couple of text lines to read as "document", not just a blank card.
    line_inset = int(SIZE * 0.055)
    line_height = int(SIZE * 0.028)
    line_gap = int(SIZE * 0.075)
    line_start_y = page_top + int(SIZE * 0.16)
    for i, width_ratio in enumerate((0.80, 0.60)):
        y = line_start_y + i * line_gap
        line_right = page_left + line_inset + int((page_right - page_left - 2 * line_inset) * width_ratio)
        draw.rounded_rectangle(
            [page_left + line_inset, y, line_right, y + line_height],
            radius=line_height // 2,
            fill=LINE_COLOR,
        )

    # Magnifying glass overlapping the page's bottom-right corner.
    glass_cx = int(SIZE * 0.66)
    glass_cy = int(SIZE * 0.64)
    glass_r = int(SIZE * 0.175)
    stroke = int(SIZE * 0.055)

    draw.ellipse(
        [glass_cx - glass_r, glass_cy - glass_r, glass_cx + glass_r, glass_cy + glass_r],
        fill=PAGE_COLOR,
        outline=GLASS_COLOR,
        width=stroke,
    )

    angle = math.radians(45)
    handle_start_r = glass_r + int(stroke * 0.15)
    handle_len = int(SIZE * 0.19)
    hx1 = glass_cx + math.cos(angle) * handle_start_r
    hy1 = glass_cy + math.sin(angle) * handle_start_r
    hx2 = hx1 + math.cos(angle) * handle_len
    hy2 = hy1 + math.sin(angle) * handle_len
    draw.line([(hx1, hy1), (hx2, hy2)], fill=GLASS_COLOR, width=stroke)
    cap_r = stroke // 2
    draw.ellipse([hx1 - cap_r, hy1 - cap_r, hx1 + cap_r, hy1 + cap_r], fill=GLASS_COLOR)
    draw.ellipse([hx2 - cap_r, hy2 - cap_r, hx2 + cap_r, hy2 + cap_r], fill=GLASS_COLOR)

    return img


if __name__ == "__main__":
    icon = build_icon()
    out_dir = Path(__file__).parent
    preview_path = out_dir / "icon_preview.png"
    ico_path = out_dir.parent / "src" / "smartdoc" / "presentation" / "assets" / "app_icon.ico"
    ico_path.parent.mkdir(parents=True, exist_ok=True)

    icon.save(preview_path)
    icon.save(ico_path, sizes=[(s, s) for s in (16, 24, 32, 48, 64, 128, 256)])
    print("wrote", preview_path)
    print("wrote", ico_path)
