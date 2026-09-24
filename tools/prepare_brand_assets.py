# SPDX-License-Identifier: AGPL-3.0-or-later
"""Builds the packaged mascot artwork from the owner's source pictures (docs/handoff/08_BRAND_MASCOT_SPEC.md §7).

The sources ("Sample theme/cat/", kept out of the repository) have a grey/white checkerboard *painted into* the
picture instead of real alpha, so every cut-out is made in two passes: (1) near-neutral light pixels connected to the
image border are the background; (2) large blobs of *exactly* the two checker colours that survive inside the
picture (between the tail and body, in a neural-net graph...) are removed too. Scenes (a picture with its own
background) are only trimmed at the edge, where the checker leaks in. The output is a small `@1x`/`@2x` PNG pair
per role, a new `app_icon.ico` + `brand_logo.png`, and a report with the leftover-checker count (must be 0).

Deliberately outside `src/smartdoc`: it needs numpy/scipy, which the GUI process must not import. Run by hand,
not part of the build:
    uv run --with numpy --with scipy --with pillow python tools/prepare_brand_assets.py "Sample theme/cat"
"""
from __future__ import annotations

import sys
from pathlib import Path

import numpy as np
from PIL import Image, ImageDraw
from scipy import ndimage

ROOT = Path(__file__).resolve().parent.parent
ASSETS = ROOT / "src" / "smartdoc" / "presentation" / "assets"
BRAND_DIR = ASSETS / "brand"
REPORT = ROOT / "docs" / "brand" / "asset_report.md"

# role -> (source file, kind, @1x longest side). @2x is twice that (capped by the source resolution).
ROLES: dict[str, tuple[str, str, int]] = {
    "logo": ("logo.png", "cutout", 240),
    "thinking": ("cat AI.png", "cutout", 240),
    "searching": ("cat research.png", "cutout", 240),
    "waiting": ("cat_coffee.png", "scene", 240),
    "done": ("cat_retire.png", "scene", 240),
    "sad": ("cat_sad.png", "scene", 200),
    "dev": ("cat_dev.png", "cutout", 240),
}
BG_MAX_CHROMA = 22  # near-neutral ...
BG_MIN_LEVEL = 185  # ... and light = checkerboard, never the orange cat or its dark outline
CHECKER_TOLERANCE = 6
MIN_ENCLOSED_BLOB = 150  # px; smaller specks are anti-aliasing, not a checker square
SCENE_TRIM = 8  # px shaved from a scene's edges, where the checker leaks in
EDGE_CHECKER_SHARE = 0.3  # an edge line with more near-neutral light pixels than this is checker
ICO_SIZES = (16, 24, 32, 48, 64, 128, 256)
ICON_BG = (217, 192, 167)  # "kem giấy" from the brand palette (08 §2)
ICON_RADIUS_RATIO = 0.22


def _chroma_level(rgb: np.ndarray) -> tuple[np.ndarray, np.ndarray]:
    mx = rgb.max(axis=2).astype(int)
    return mx - rgb.min(axis=2).astype(int), mx


def _checker_colours(rgb: np.ndarray, background: np.ndarray) -> list[np.ndarray]:
    """The two checker colours: the most common colours among pixels already known to be background."""
    vals, counts = np.unique(rgb[background].reshape(-1, 3), axis=0, return_counts=True)
    return [vals[i] for i in np.argsort(counts)[::-1][:2]]


def cut_out(img: Image.Image) -> Image.Image:
    rgba = np.array(img.convert("RGBA"))
    rgb = rgba[..., :3]
    chroma, level = _chroma_level(rgb)
    light = (chroma <= BG_MAX_CHROMA) & (level >= BG_MIN_LEVEL)
    labels, _ = ndimage.label(light)
    border = np.unique(np.concatenate([labels[0], labels[-1], labels[:, 0], labels[:, -1]]))
    background = np.isin(labels, border[border != 0])
    if background.any():
        exact = np.zeros(light.shape, bool)
        for colour in _checker_colours(rgb, background):
            exact |= (np.abs(rgb.astype(int) - colour.astype(int)) <= CHECKER_TOLERANCE).all(axis=2)
        blobs, n = ndimage.label(ndimage.binary_closing(exact, iterations=1))
        if n:
            sizes = ndimage.sum(exact, blobs, index=range(1, n + 1))
            big = [i + 1 for i, s in enumerate(sizes) if s >= MIN_ENCLOSED_BLOB]
            background |= np.isin(blobs, big) & exact
    background = ndimage.binary_dilation(background, iterations=1) & light | background  # eat the halo
    alpha = np.where(background, 0, 255).astype(np.uint8)
    alpha = np.array(Image.fromarray(alpha).filter(_soft_edge()))
    rgba[..., 3] = alpha
    out = Image.fromarray(rgba)
    box = out.getchannel("A").point(lambda a: 255 if a > 8 else 0).getbbox()
    return out.crop(box) if box else out


def _soft_edge():
    from PIL import ImageFilter
    return ImageFilter.GaussianBlur(0.8)


def trim_scene(img: Image.Image) -> Image.Image:
    """Shave the fixed margin, then keep shaving any edge line that is still mostly checker."""
    w, h = img.size
    rgba = img.convert("RGBA").crop((SCENE_TRIM, SCENE_TRIM, w - SCENE_TRIM, h - SCENE_TRIM))
    a = np.array(rgba)
    chroma, level = _chroma_level(a[..., :3])
    light = (chroma <= BG_MAX_CHROMA) & (level >= BG_MIN_LEVEL)
    top, bottom, left, right = 0, light.shape[0], 0, light.shape[1]
    while right - left > 1 and light[top:bottom, right - 1].mean() > EDGE_CHECKER_SHARE:
        right -= 1
    while right - left > 1 and light[top:bottom, left].mean() > EDGE_CHECKER_SHARE:
        left += 1
    while bottom - top > 1 and light[bottom - 1, left:right].mean() > EDGE_CHECKER_SHARE:
        bottom -= 1
    while bottom - top > 1 and light[top, left:right].mean() > EDGE_CHECKER_SHARE:
        top += 1
    return rgba.crop((left, top, right, bottom))


def leftover_checker(img: Image.Image) -> int:
    """Visible near-neutral light pixels that touch transparency: what a bad cut leaves behind."""
    a = np.array(img.convert("RGBA"))
    chroma, level = _chroma_level(a[..., :3])
    light = (chroma <= BG_MAX_CHROMA) & (level >= BG_MIN_LEVEL) & (a[..., 3] > 200)
    near_hole = ndimage.binary_dilation(a[..., 3] < 20, iterations=2)
    return int((light & near_hole).sum())


def _fit(img: Image.Image, longest: int) -> Image.Image:
    scale = min(1.0, longest / max(img.size))
    return img.resize((max(1, round(img.width * scale)), max(1, round(img.height * scale))), Image.LANCZOS)


def _icon(logo: Image.Image) -> Image.Image:
    """Rounded cream tile with the cut-out logo centred, so it stays readable at 16 px."""
    size = 512
    tile = Image.new("RGBA", (size, size), (0, 0, 0, 0))
    mask = Image.new("L", (size, size), 0)
    ImageDraw.Draw(mask).rounded_rectangle([0, 0, size - 1, size - 1], radius=int(size * ICON_RADIUS_RATIO), fill=255)
    tile.paste(Image.new("RGBA", (size, size), ICON_BG + (255,)), (0, 0), mask)
    cat = _fit(logo, int(size * 0.8))
    tile.alpha_composite(cat, ((size - cat.width) // 2, (size - cat.height) // 2))
    return tile


def main(source_dir: Path) -> None:
    BRAND_DIR.mkdir(parents=True, exist_ok=True)
    REPORT.parent.mkdir(parents=True, exist_ok=True)
    rows = ["| Vai trò | Loại | @1x | @2x | Điểm ảnh caro còn sót | Dung lượng (KB) |", "|---|---|---|---|---|---|"]
    total = 0
    logo_full: Image.Image | None = None
    for role, (name, kind, size1) in ROLES.items():
        src = Image.open(source_dir / name)
        full = cut_out(src) if kind == "cutout" else trim_scene(src)
        if role == "logo":
            logo_full = full
        left = leftover_checker(full) if kind == "cutout" else 0
        sizes = []
        kb = 0.0
        for suffix, longest in (("", size1), ("@2x", size1 * 2)):
            out = _fit(full, longest)
            path = BRAND_DIR / f"{role}{suffix}.png"
            out.quantize(colors=128, method=Image.Quantize.FASTOCTREE).save(path, optimize=True)  # size budget
            kb += path.stat().st_size / 1024
            sizes.append(f"{out.width}x{out.height}")
        total += kb
        rows.append(f"| {role} | {kind} | {sizes[0]} | {sizes[1]} | {left} | {kb:.0f} |")
    assert logo_full is not None
    icon = _icon(logo_full)
    icon.save(ASSETS / "app_icon.ico", sizes=[(s, s) for s in ICO_SIZES])
    icon.save(ASSETS / "brand_logo.png", optimize=True)
    REPORT.write_text(
        "# Báo cáo ảnh thương hiệu\n\nSinh bởi `tools/prepare_brand_assets.py` (không sửa tay).\n\n"
        + "\n".join(rows) + f"\n\nTổng ảnh mèo: {total:.0f} KB (ngân sách 1536 KB).\n",
        encoding="utf-8",
    )
    print("\n".join(rows), f"\ntotal {total:.0f} KB")


if __name__ == "__main__":
    if len(sys.argv) != 2:
        sys.exit(__doc__)
    main(Path(sys.argv[1]))
