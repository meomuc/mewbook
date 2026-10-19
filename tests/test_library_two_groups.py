# SPDX-License-Identifier: AGPL-3.0-or-later
"""A multi-word search in relevance order shows its two groups in the list (table) view, each heading spanning the row
(ticket 3, step 2b, slice 2). The shelf keeps books only until its own slice."""
from smartdoc.presentation.library_view import LibraryListWidget


def _seed(app_context):
    db = app_context.db
    db.add_or_update_document("exact", {"title": "Python Co Ban", "author": "A", "file_path": "a.pdf", "extension": "pdf", "created_at": 1.0})
    db.add_or_update_document("partial", {"title": "Co Ban Python", "author": "B", "file_path": "b.pdf", "extension": "pdf", "created_at": 2.0})


def test_two_groups_show_in_the_list_with_spanned_headings(qapp, app_context):
    _seed(app_context)
    widget = LibraryListWidget(app_context)
    widget.show()
    app_context.filters.set_query("python co")
    qapp.processEvents()

    model = widget.table_model
    assert model.rowCount() == 4  # heading, exact book, heading, partial book
    assert model.data(model.index(0, 0), 0) == "Khớp đúng cụm"
    assert model.document_at(1)["id"] == "exact"
    assert model.data(model.index(2, 0), 0) == "Khớp một phần"
    assert model.document_at(3)["id"] == "partial"
    assert widget.table_view.columnSpan(0, 0) == model.columnCount()
    assert widget.table_view.columnSpan(2, 0) == model.columnCount()
    widget.deleteLater()


def test_the_shelf_shows_the_same_headings_as_the_list(qapp, app_context):
    _seed(app_context)
    widget = LibraryListWidget(app_context)
    widget.show()
    app_context.filters.set_query("python co")
    qapp.processEvents()

    shelf = widget.list_view
    assert widget.model.rowCount() == 4
    assert widget.model.document_at(0) is None and widget.model.document_at(2) is None
    headings = [s.heading for s in shelf._shelves if s.heading is not None]
    assert headings == ["Khớp đúng cụm", "Khớp một phần"]
    widget.deleteLater()


def test_a_heading_cannot_be_clicked_and_the_cursor_steps_over_it(qapp, app_context):
    from PySide6.QtCore import Qt
    from PySide6.QtWidgets import QAbstractItemView

    _seed(app_context)
    widget = LibraryListWidget(app_context)
    widget.show()
    app_context.filters.set_query("python co")
    qapp.processEvents()

    shelf = widget.list_view
    heading_rect = shelf._rects[0]
    assert not shelf.indexAt(heading_rect.center()).isValid()  # a click on the heading selects nothing
    shelf.setCurrentIndex(widget.model.index(0, 0))  # the cursor stands on the heading
    down = shelf.moveCursor(QAbstractItemView.MoveDown, Qt.NoModifier)
    assert down.row() == 1  # the first book of the exact group, not another heading
    widget.deleteLater()


def test_a_single_word_search_has_no_headings(qapp, app_context):
    _seed(app_context)
    widget = LibraryListWidget(app_context)
    widget.show()
    app_context.filters.set_query("python")
    qapp.processEvents()

    assert widget.table_model.rowCount() == 2
    assert all(widget.table_model.document_at(row) is not None for row in range(2))
    widget.deleteLater()
