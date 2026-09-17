from PySide6.QtCore import Qt
from PySide6.QtWidgets import QMessageBox

from smartdoc.presentation.duplicate_finder_dialog import DuplicateFinderDialog


def _seed_exact_duplicates(app_context):
    app_context.db.add_or_update_document(
        "d1", {"title": "Sach A", "author": "X", "file_path": "a.pdf", "content_hash": "h1", "created_at": 1.0}
    )
    app_context.db.add_or_update_document(
        "d2", {"title": "Sach A (copy)", "author": "X", "file_path": "a2.pdf", "content_hash": "h1", "created_at": 2.0}
    )
    app_context.db.add_or_update_document(
        "d3", {"title": "Unique", "author": "Y", "file_path": "b.pdf", "content_hash": "h2", "created_at": 3.0}
    )


def test_exact_tab_lists_only_duplicate_documents(qapp, app_context):
    _seed_exact_duplicates(app_context)
    dialog = DuplicateFinderDialog(app_context)

    assert dialog.exact_table.rowCount() == 2
    titles = {dialog.exact_table.item(row, 0).text() for row in range(2)}
    assert titles == {"Sach A", "Sach A (copy)"}


def test_no_duplicates_means_empty_tables(qapp, app_context):
    app_context.db.add_or_update_document(
        "d1", {"title": "Only One", "author": "X", "file_path": "a.pdf", "content_hash": "h1", "created_at": 1.0}
    )
    dialog = DuplicateFinderDialog(app_context)

    assert dialog.exact_table.rowCount() == 0
    assert dialog.fuzzy_table.rowCount() == 0


def test_checking_a_row_and_deleting_removes_from_library(qapp, app_context, monkeypatch):
    _seed_exact_duplicates(app_context)
    monkeypatch.setattr(QMessageBox, "question", staticmethod(lambda *a, **k: QMessageBox.Yes))

    dialog = DuplicateFinderDialog(app_context)
    dialog.exact_table.item(0, 0).setCheckState(Qt.Checked)

    dialog._on_delete_selected()

    remaining_ids = {d["id"] for d in app_context.db.list_all_documents()}
    assert "d1" not in remaining_ids or "d2" not in remaining_ids
    assert len(remaining_ids) == 2  # one of the pair removed, "d3" untouched
    assert "d3" in remaining_ids


def test_deleting_with_nothing_checked_does_nothing(qapp, app_context):
    _seed_exact_duplicates(app_context)
    dialog = DuplicateFinderDialog(app_context)

    dialog._on_delete_selected()

    assert len(app_context.db.list_all_documents()) == 3


def test_delete_cancelled_keeps_all_documents(qapp, app_context, monkeypatch):
    _seed_exact_duplicates(app_context)
    monkeypatch.setattr(QMessageBox, "question", staticmethod(lambda *a, **k: QMessageBox.No))

    dialog = DuplicateFinderDialog(app_context)
    dialog.exact_table.item(0, 0).setCheckState(Qt.Checked)
    dialog._on_delete_selected()

    assert len(app_context.db.list_all_documents()) == 3


def test_refresh_updates_after_external_change(qapp, app_context):
    dialog = DuplicateFinderDialog(app_context)
    assert dialog.exact_table.rowCount() == 0

    _seed_exact_duplicates(app_context)
    dialog.refresh()

    assert dialog.exact_table.rowCount() == 2
