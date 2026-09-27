# SPDX-License-Identifier: AGPL-3.0-or-later
"""The excluded-books window and the CSV export of the library."""
from __future__ import annotations

import csv

from smartdoc.application.library_export import COLUMNS, export_library_csv


def _doc(db, doc_id, title, path, **extra):
    db.add_or_update_document(doc_id, {"title": title, "author": "A", "file_path": path, "created_at": 1.0, **extra})


def test_list_excluded_details(app_context):
    app_context.db.exclude_paths(["a/x.pdf", "b/y.epub"])
    rows = app_context.db.list_excluded_details()
    assert {r["path"] for r in rows} == {"a/x.pdf", "b/y.epub"}
    assert all("excluded_at" in r and "file_size" in r for r in rows)


def test_export_writes_bom_header_rows_and_guards_formulas(app_context, tmp_path):
    _doc(app_context.db, "d1", "=HYPERLINK(\"x\")", "1.pdf")
    _doc(app_context.db, "d2", "Sách hay", "2.pdf")
    target = tmp_path / "out.csv"
    assert export_library_csv(app_context.db, target) == 2
    raw = target.read_bytes()
    assert raw.startswith(b"\xef\xbb\xbf")
    rows = list(csv.reader(raw.decode("utf-8-sig").splitlines()))
    assert rows[0] == [h for h, _k in COLUMNS] and len(rows) == 3
    titles = {r[0] for r in rows[1:]}
    assert "'=HYPERLINK(\"x\")" in titles and "Sách hay" in titles
    assert not (tmp_path / "out.csv.part").exists()


def test_export_pages_and_reports_progress(app_context, tmp_path, monkeypatch):
    monkeypatch.setattr("smartdoc.application.library_export.PAGE", 2)
    for n in range(5):
        _doc(app_context.db, f"d{n}", f"t{n}", f"{n}.pdf")
    told = []
    assert export_library_csv(app_context.db, tmp_path / "o.csv", lambda done, total: told.append((done, total))) == 5
    assert told[-1] == (5, 5) and len(told) == 3


def test_export_failure_leaves_no_part_file(app_context, tmp_path):
    import pytest

    with pytest.raises(OSError):
        export_library_csv(app_context.db, tmp_path / "missing-folder" / "o.csv")


def test_excluded_dialog_lists_filters_and_restores(qapp, app_context, tmp_path):
    from smartdoc.presentation.excluded_books_dialog import ExcludedBooksDialog

    real = tmp_path / "Truyện Kiều.pdf"
    real.write_bytes(b"x")
    gone = str(tmp_path / "mat.pdf")
    app_context.db.exclude_paths([str(real), gone])

    added = []

    class _Importer:
        def add_files(self, paths):
            added.extend(paths)

    dialog = ExcludedBooksDialog(app_context, _Importer())
    assert dialog.table.rowCount() == 2
    dialog.search_edit.setText("truyen kieu")
    assert [dialog.table.isRowHidden(r) for r in range(2)].count(False) == 1
    dialog.search_edit.setText("")
    dialog.table.selectAll()
    dialog._on_restore()
    assert added == [str(real)]
    assert dialog.table.rowCount() == 0 and app_context.db.list_excluded_details() == []
    dialog.deleteLater()
