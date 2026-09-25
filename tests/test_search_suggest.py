# SPDX-License-Identifier: AGPL-3.0-or-later
"""The search box's grouped suggestion popup (stage G3): rows, keyboard, chip vs. text search."""
from PySide6.QtCore import QEvent, Qt
from PySide6.QtGui import QKeyEvent
from PySide6.QtWidgets import QApplication

from smartdoc.domain.library_filter import AUTHORS
from smartdoc.presentation.omnibar import OmnibarSearchBar


def _seed(app_context):
    for i, author in enumerate(["Nguyễn Văn Hải", "Nguyễn Phương", "Lê Minh"]):
        app_context.db.add_or_update_document(
            f"d{i}", {"title": f"Sách {i}", "author": author, "file_path": f"b{i}.pdf", "extension": "pdf",
                      "created_at": float(i)})


def _press(widget, key):
    QApplication.sendEvent(widget, QKeyEvent(QEvent.KeyPress, key, Qt.NoModifier))


def _typed(qapp, app_context, text):
    bar = OmnibarSearchBar(app_context)
    bar.resize(400, 30)
    bar.show()
    bar.setText(text)
    bar.textEdited.emit(text)
    qapp.processEvents()
    return bar


def test_popup_offers_grouped_filters_and_a_text_search_row(qapp, app_context):
    _seed(app_context)
    bar = _typed(qapp, app_context, "nguy")
    popup = bar._popup
    assert popup.isVisible()
    assert popup.row_count == 3  # two authors + the "search the words" row
    assert "nguy" in popup._hint.text()


def test_arrow_and_enter_turn_a_suggestion_into_a_chip_and_clear_the_words(qapp, app_context):
    _seed(app_context)
    bar = _typed(qapp, app_context, "nguy")
    _press(bar, Qt.Key_Down)
    assert bar._popup.has_choice
    _press(bar, Qt.Key_Return)
    qapp.processEvents()
    qapp.processEvents()
    assert app_context.filters.current.values(AUTHORS)
    assert app_context.filters.current.query == "" and bar.text() == ""
    assert not bar._popup.isVisible()


def test_enter_without_a_choice_searches_the_words(qapp, app_context):
    _seed(app_context)
    bar = _typed(qapp, app_context, "nguy")
    _press(bar, Qt.Key_Return)
    assert app_context.filters.current.query == "nguy"
    assert not bar._popup.isVisible()


def test_escape_closes_and_short_text_offers_nothing(qapp, app_context):
    _seed(app_context)
    bar = _typed(qapp, app_context, "nguy")
    _press(bar, Qt.Key_Escape)
    assert not bar._popup.isVisible()
    bar = _typed(qapp, app_context, "n")
    assert not bar._popup.isVisible()
