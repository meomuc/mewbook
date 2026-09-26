# SPDX-License-Identifier: AGPL-3.0-or-later
"""Developer tool: builds the main window over a throw-away demo library (drawn covers, Vietnamese titles) and saves
screenshots per theme and window size, to compare with the design mock-ups in `Sample theme/Bookshelf`.
Not part of the app bundle. Run on the real platform (offscreen has no fonts):

    uv run python tools/ui_screenshots.py OUT_DIR [theme ...] [--size=1280x800] [--layout=toi-gian] [--page=home|library]
"""
from __future__ import annotations

import random
import sys
import tempfile
import time
from pathlib import Path

from PIL import Image, ImageDraw
from PySide6.QtWidgets import QApplication

from smartdoc.app import _apply_appearance
from smartdoc.core.app_context import AppContext
from smartdoc.presentation.theme_manager import theme_manager
from smartdoc.presentation.window_shapes import window_class_for

_TITLES = [
    ("Thiết kế hệ thống điện nhẹ", "Nguyễn Văn Hải", "pdf"), ("Camera giám sát cho nhà máy", "Nguyễn Văn Hải", "pdf"),
    ("Cáp quang ngoại hiện trường", "Nguyễn Văn Hải", "pdf"), ("Âm thanh công cộng", "Phạm Thu Hà", "pdf"),
    ("PCCC trong tòa nhà cao tầng", "Phạm Thu Hà", "pdf"), ("Hệ thống báo cháy tự động", "Lê Quang Minh", "epub"),
    ("Kiểm soát ra vào", "Lê Quang Minh", "pdf"), ("Bản vẽ kỹ thuật thực hành", "Bùi Tấn", "pdf"),
    ("Tổng đài nội bộ IP", "", "pdf"), ("Lập trình Python cho người mới", "Bùi Tấn", "epub"),
    ("Mạng không dây doanh nghiệp", "Lê Quang Minh", "mobi"), ("Nghiêm thu hệ thống camera", "Nguyễn Văn Hải", "pdf"),
    ("Chấm công và kiểm soát cửa", "Nguyễn Văn Hải", "pdf"), ("Tủ rack và đi dây gọn gàng", "Trần Công Lý", "azw3"),
]
_PALETTE = ["#1f3a5f", "#111111", "#c8d6e5", "#0f6b5c", "#b03026", "#2a2a3e", "#e8dcc8", "#3a3f6b"]


def build_demo(context: AppContext, folder: Path) -> None:
    rng = random.Random(7)
    for i, (title, author, ext) in enumerate(_TITLES):
        cover = None
        if i % 5 != 2:  # every fifth book has no cover, to show the placeholder
            image = Image.new("RGB", (240, 340), _PALETTE[i % len(_PALETTE)])
            draw = ImageDraw.Draw(image)
            draw.rectangle((16, 200, 224, 206 + rng.randint(0, 20)), fill="#d9a441")
            draw.text((20, 40), title[:20], fill="white")
            cover = str(folder / f"c{i}.png")
            image.save(cover)
        context.db.add_or_update_document(f"d{i}", {
            "title": title, "author": author or "Unknown", "file_path": str(folder / f"b{i}.{ext}"), "extension": ext,
            "file_size": 12_000_000 + i * 100_000, "created_at": 1_790_000_000.0 - i * 40_000, "cover_path": cover,
            "tags": ["điện-nhẹ", "camera"] if i % 2 == 0 else ["mạng"],
        })


def main() -> None:
    args = [a for a in sys.argv[1:] if not a.startswith("--")]
    out = Path(args[0])
    themes = args[1:] or ["broadsheet", "inkynight"]
    size = next((a[7:] for a in sys.argv if a.startswith("--size=")), "1280x800")
    layout = next((a[9:] for a in sys.argv if a.startswith("--layout=")), "ke-sach")
    page = next((a[7:] for a in sys.argv if a.startswith("--page=")), "library")
    width, height = (int(v) for v in size.split("x"))
    out.mkdir(parents=True, exist_ok=True)
    app = QApplication([])
    with tempfile.TemporaryDirectory() as tmp:
        context = AppContext.create_in_memory(Path(tmp))
        build_demo(context, Path(tmp))
        if "--history" in sys.argv:  # something read, so the home screen has a book being read and a recent-reading card
            now = time.time()
            for n, (doc_id, position, total) in enumerate((("d0", 57, 248), ("d5", 71, 196), ("d9", 12, 340))):
                context.db.record_reading_open(doc_id, unit="page", total=total, now=now - n * 3600)
                context.db.record_reading_position(doc_id, position, total=total, now=now - n * 3600)
        for theme in themes:
            context.config.config.theme = theme
            context.config.config.layout = layout
            _apply_appearance(app, context)
            window = window_class_for(theme_manager().layout.id)(context)
            window.resize(width, height)
            window.show()
            for _ in range(5):
                app.processEvents()
            if hasattr(window, "go_to"):  # a layout with a home screen: pick the page to shoot
                window.go_to("home" if page == "home" else "library")
                for _ in range(3):
                    app.processEvents()
            if "--list" in sys.argv:
                window.library_view.set_view_mode("list")
                window.toolbar.list_view_button.setChecked(True)
                for _ in range(3):
                    app.processEvents()
            if "--select" in sys.argv:
                view = window.library_view._active_view()
                view.setCurrentIndex(window.library_view._active_model().index(1, 0))
                for _ in range(3):
                    app.processEvents()
            suffix = "_list" if "--list" in sys.argv else ""
            tag = f"{layout}_{page}_" if layout != "ke-sach" else ""
            window.grab().save(str(out / f"main_{tag}{theme}_{size}{suffix}.png"))
            window.close()
        context.shutdown()


if __name__ == "__main__":
    main()
