# SPDX-License-Identifier: AGPL-3.0-or-later
"""Heading rows in the library models (ticket 3, step 2b, slice 1): a heading shows its text, holds no book and cannot be
selected; every book row is unchanged."""
from PySide6.QtCore import Qt

from smartdoc.presentation.library_view import LibraryModel, LibraryTableModel

HEADING = "Khớp đúng cụm"


def _docs():
    return [
        None,
        {"id": "a", "title": "Python Co Ban", "author": "Nam", "extension": "pdf"},
        {"id": "b", "title": "Lap Trinh", "author": "An", "extension": "epub"},
    ]


def test_list_model_shows_the_heading_and_refuses_to_select_it(qapp):
    model = LibraryModel()
    model.set_documents(_docs(), headings={0: HEADING})

    assert model.rowCount() == 3
    heading = model.index(0, 0)
    assert model.data(heading, Qt.DisplayRole) == HEADING
    assert model.document_at(0) is None
    assert not (model.flags(heading) & Qt.ItemIsSelectable)


def test_list_model_books_are_unchanged_beside_a_heading(qapp):
    model = LibraryModel()
    model.set_documents(_docs(), headings={0: HEADING})

    book = model.index(1, 0)
    assert model.document_at(1)["id"] == "a"
    assert model.data(book, Qt.DisplayRole).startswith("Python Co Ban")
    assert model.flags(book) & Qt.ItemIsSelectable


def test_table_model_spans_the_heading_in_its_first_column_only(qapp):
    model = LibraryTableModel()
    model.set_documents(_docs(), headings={0: HEADING})

    assert model.data(model.index(0, 0), Qt.DisplayRole) == HEADING
    assert model.data(model.index(0, 1), Qt.DisplayRole) is None
    assert model.document_at(0) is None
    assert not (model.flags(model.index(0, 0)) & Qt.ItemIsSelectable)
    assert model.flags(model.index(1, 0)) & Qt.ItemIsSelectable


def test_a_model_without_headings_behaves_as_before(qapp):
    model = LibraryModel()
    model.set_documents([{"id": "a", "title": "Python", "author": "Nam", "extension": "pdf"}])
    assert model.rowCount() == 1
    assert model.document_at(0)["id"] == "a"
