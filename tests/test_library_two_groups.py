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


def test_the_shelf_keeps_books_only(qapp, app_context):
    _seed(app_context)
    widget = LibraryListWidget(app_context)
    widget.show()
    app_context.filters.set_query("python co")
    qapp.processEvents()

    assert widget.model.rowCount() == 2
    assert all(widget.model.document_at(row) is not None for row in range(widget.model.rowCount()))
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
