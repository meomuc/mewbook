# SPDX-License-Identifier: AGPL-3.0-or-later
"""The bookshelf (stage G4): grouping labels, layout, hit-testing, keyboard, selection and the cover states."""
from datetime import datetime, timedelta

import pytest
from PySide6.QtCore import QEvent, Qt
from PySide6.QtGui import QKeyEvent
from PySide6.QtWidgets import QApplication

from smartdoc.presentation import shelf_groups as groups
from smartdoc.presentation.library_view import LibraryListWidget, ShelfModel

NOW = datetime(2026, 9, 25, 12, 0, 0)


def _ts(days_ago: int) -> float:
    return (NOW - timedelta(days=days_ago)).timestamp()


def test_newest_sort_groups_by_age():
    assert groups.shelf_for({"created_at": _ts(0)}, None, NOW).title == "HÔM NAY"
    assert groups.shelf_for({"created_at": _ts(3)}, groups.SORT_NEWEST, NOW).title == "TUẦN NÀY"
    assert groups.shelf_for({"created_at": _ts(12)}, None, NOW).title == "THÁNG 9"
    assert groups.shelf_for({"created_at": _ts(40)}, None, NOW).title == "THÁNG 8"
    assert groups.shelf_for({"created_at": _ts(400)}, None, NOW).title.startswith("THÁNG")
    assert groups.shelf_for({"created_at": _ts(0)}, None, NOW).subtitle(5) == "5 sách mới thêm"


def test_title_and_author_sorts_group_by_base_letter_ignoring_accents():
    assert groups.shelf_for({"title": "Ánh sáng"}, groups.SORT_TITLE).title == "A"
    assert groups.shelf_for({"title": "Đức Phật"}, groups.SORT_TITLE).title == "D"
    assert groups.shelf_for({"title": "12 luật"}, groups.SORT_TITLE).title == "0–9"
    assert groups.shelf_for({"author": ""}, groups.SORT_AUTHOR).title == "CHƯA RÕ TÁC GIẢ"
    assert groups.shelf_for({"author": "Nguyễn Văn Hải"}, groups.SORT_AUTHOR).key == "aN"


def test_size_and_rating_sorts_group_into_bands():
    assert groups.shelf_for({"file_size": 60 * 1024 * 1024}, groups.SORT_SIZE).title == "TRÊN 50 MB"
    assert groups.shelf_for({"file_size": 100}, groups.SORT_SIZE).title == "DƯỚI 1 MB"
    assert groups.shelf_for({"avg_rating": 4.6}, groups.SORT_RATING).title == "5★"
    assert groups.shelf_for({"avg_rating": None}, groups.SORT_RATING).title == "CHƯA CÓ ĐÁNH GIÁ"


@pytest.fixture
def shelf(qapp, app_context):
    for i in range(10):
        app_context.db.add_or_update_document(
            f"d{i}", {"title": f"Book {i}", "author": "A", "file_path": f"{i}.pdf", "extension": "pdf",
                      "created_at": float(1_700_000_000 + i)})
    widget = LibraryListWidget(app_context)
    widget.resize(900, 640)
    widget.show()
    qapp.processEvents()
    yield widget
    widget.hide()
    widget.deleteLater()


def test_covers_wrap_onto_shelves_and_the_first_shelf_of_a_group_carries_the_label(shelf):
    view = shelf.list_view
    per_row = view._per_row()
    assert 1 <= per_row < 10
    assert sum(len(s.rows) for s in view._shelves) == 10
    assert view._shelves[0].label is not None
    labels = [s.label for s in view._shelves if s.label]
    assert len(labels) >= 1 and labels[0][1].endswith("sách")


def test_bottoms_of_covers_on_one_shelf_line_up_and_gridsize_follows_cover_size(shelf):
    view = shelf.list_view
    row = view._shelves[0]
    bottoms = {view._rects[r].bottom() for r in row.rows}
    assert len(bottoms) == 1
    before = view.gridSize()
    from PySide6.QtCore import QSize

    view.setIconSize(QSize(200, 284))
    assert view.gridSize().width() > before.width() and view.gridSize().height() > before.height()


def test_indexat_and_selection_by_click_and_the_lift(shelf, qapp):
    from PySide6.QtTest import QTest

    view = shelf.list_view
    rect = view.visualRect(shelf.model.index(2, 0))
    assert view.indexAt(rect.center()).row() == 2
    QTest.mouseClick(view.viewport(), Qt.LeftButton, Qt.NoModifier, rect.center())
    assert [i.row() for i in view.selectedIndexes()] == [2]
    assert view.visualRect(shelf.model.index(2, 0)).top() == rect.top() - 6  # the picked cover is lifted


def test_arrow_keys_move_between_covers_and_shelves(shelf, qapp):
    view = shelf.list_view
    view.setCurrentIndex(shelf.model.index(0, 0))
    view.setFocus()

    def press(key):
        QApplication.sendEvent(view, QKeyEvent(QEvent.KeyPress, key, Qt.NoModifier))

    press(Qt.Key_Right)
    assert view.currentIndex().row() == 1
    press(Qt.Key_Down)
    assert view.currentIndex().row() >= view._per_row()  # the next shelf
    press(Qt.Key_Home)
    assert view.currentIndex().row() == 0


def test_cover_state_says_none_for_a_book_without_a_cover(qapp, app_context):
    app_context.db.add_or_update_document("d1", {"title": "A", "author": "X", "file_path": "a.pdf", "created_at": 1.0})
    model = ShelfModel(context=app_context)
    model.set_documents([app_context.db.get_document("d1")])
    assert model.cover_state(0) == ("none", None)
