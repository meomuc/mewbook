"""The shared "book shelf" look: placeholder jackets, sidebar count rows,
theme names."""
from PySide6.QtCore import QSize
from PySide6.QtGui import QColor

from smartdoc.presentation.cover_placeholder import _pair_index, gradient_pixmap
from smartdoc.presentation.sidebar_style import split_count
from smartdoc.presentation.theme import BROADSHEET, THEMES


def test_placeholder_color_is_stable_across_launches():
    # crc32 of the id, not Python's per-process-salted hash(): the same
    # book must keep the same jacket colour from one launch to the next.
    assert _pair_index("doc-123", 8) == 1
    assert _pair_index("", 8) == 0


def test_placeholder_spine_is_a_tint_not_a_solid_black_block(qapp):
    image = gradient_pixmap("doc-1", QSize(120, 160), BROADSHEET).toImage()
    spine = QColor(image.pixel(2, 80))
    assert (spine.red(), spine.green(), spine.blue()) != (0, 0, 0)


def test_placeholder_prints_the_title_on_grid_sized_jackets_only(qapp):
    plain = gradient_pixmap("doc-1", QSize(120, 160), BROADSHEET).toImage()
    titled = gradient_pixmap("doc-1", QSize(120, 160), BROADSHEET, title="Lịch Sử", author="Ai Đó").toImage()
    assert plain != titled

    # List-view thumbnails are too small for text: identical either way.
    tiny_plain = gradient_pixmap("doc-1", QSize(32, 46), BROADSHEET).toImage()
    tiny_titled = gradient_pixmap("doc-1", QSize(32, 46), BROADSHEET, title="Lịch Sử").toImage()
    assert tiny_plain == tiny_titled


def test_split_count_separates_name_and_count():
    assert split_count("Tất cả tài liệu (14781)") == ("Tất cả tài liệu", "14781")
    assert split_count("📂 Nga (3)") == ("📂 Nga", "3")
    assert split_count("Tác giả") == ("Tác giả", "")
    assert split_count("") == ("", "")


def test_theme_display_names():
    assert [THEMES[key].display_name for key in ("broadsheet", "woodshelf", "inkynight")] == [
        "Editorial Light",
        "Walnut Library",
        "Midnight Ink",
    ]
