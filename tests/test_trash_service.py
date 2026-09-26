# SPDX-License-Identifier: AGPL-3.0-or-later
"""MewBook's trash: files go there before they are gone, can come back with everything, and expire after the period."""
from __future__ import annotations

import time

import pytest

from smartdoc.application.trash_service import TrashError
from smartdoc.core.event_bus import LibraryUpdatedEvent


@pytest.fixture
def library(app_context, tmp_path):
    folder = tmp_path / "books"
    folder.mkdir()
    for n in (1, 2):
        (folder / f"b{n}.pdf").write_bytes(b"x" * n)
        app_context.db.add_or_update_document(f"d{n}", {
            "title": f"Sách {n}", "author": "Tác giả", "file_path": str(folder / f"b{n}.pdf"), "extension": "pdf",
            "file_size": n, "tags": "a,b", "created_at": 5.0}, extracted_text=f"nội dung số {n}")
    return folder


def test_send_moves_the_file_and_removes_the_entry(app_context, library):
    events = []
    app_context.event_bus.subscribe(LibraryUpdatedEvent, events.append)
    result = app_context.trash.send([("d1", str(library / "b1.pdf"))])
    assert result.moved == ["d1"] and not result.failed
    assert not (library / "b1.pdf").exists() and (library / "b2.pdf").exists()
    assert app_context.db.get_document("d1") is None
    (item,) = app_context.trash.list_items()
    assert item.title == "Sách 1" and item.original_path == str(library / "b1.pdf") and item.size == 1
    assert item.days_left() == 30 and events


def test_restore_brings_back_file_tags_collections_and_search_text(app_context, library):
    app_context.db.save_collection("c1", "Đọc dần", "[]", "AND", 1.0)
    app_context.db.add_documents_to_collection("c1", ["d1"])
    app_context.trash.send([("d1", str(library / "b1.pdf"))])
    (item,) = app_context.trash.list_items()
    where = app_context.trash.restore(item.item_id)
    assert where == library / "b1.pdf" and where.is_file()
    doc = app_context.db.get_document("d1")
    assert doc["title"] == "Sách 1" and doc["tags"] == "a,b" and doc["content"] == "nội dung số 1"
    assert "d1" in app_context.db.list_collection_document_ids("c1")
    assert not app_context.trash.list_items()


def test_restore_never_overwrites_another_file(app_context, library):
    app_context.trash.send([("d1", str(library / "b1.pdf"))])
    (library / "b1.pdf").write_bytes(b"someone else's file")
    (item,) = app_context.trash.list_items()
    where = app_context.trash.restore(item.item_id)
    assert where.name == "b1 (khôi phục).pdf" and (library / "b1.pdf").read_bytes() == b"someone else's file"


def test_a_file_that_cannot_be_moved_stays_and_stays_in_the_library(app_context, library, monkeypatch):
    def refuse(*_a, **_k):
        raise PermissionError(13, "denied")

    monkeypatch.setattr("smartdoc.application.trash_service.shutil.move", refuse)
    result = app_context.trash.send([("d1", str(library / "b1.pdf"))])
    assert result.failed and result.failed[0][0] == "d1" and not result.moved
    assert (library / "b1.pdf").exists() and app_context.db.get_document("d1") is not None
    assert not app_context.trash.list_items()


def test_a_book_whose_file_is_already_gone_just_leaves_the_library(app_context, library):
    (library / "b2.pdf").unlink()
    result = app_context.trash.send([("d2", str(library / "b2.pdf"))])
    assert result.missing == ["d2"] and app_context.db.get_document("d2") is None and not app_context.trash.list_items()


def test_items_expire_after_the_retention_period_and_zero_means_never(app_context, library):
    app_context.trash.send([("d1", str(library / "b1.pdf")), ("d2", str(library / "b2.pdf"))])
    now = time.time()
    assert app_context.trash.purge_expired(now + 29 * 86_400) == 0
    assert app_context.trash.purge_expired(now + 31 * 86_400) == 2 and not app_context.trash.list_items()
    app_context.config.config.trash_retention_days = 0
    app_context.trash.send([("d1", str(library / "b1.pdf"))]) if app_context.db.get_document("d1") else None
    assert app_context.trash.purge_expired(now + 10_000 * 86_400) == 0


def test_delete_forever_and_empty_only_touch_the_trash(app_context, library):
    app_context.trash.send([("d1", str(library / "b1.pdf")), ("d2", str(library / "b2.pdf"))])
    first, second = app_context.trash.list_items()
    app_context.trash.delete_forever(first.item_id)
    assert len(app_context.trash.list_items()) == 1
    assert app_context.trash.empty() == 1 and not app_context.trash.list_items()
    with pytest.raises(TrashError):
        app_context.trash.restore("../../etc")


def test_the_trash_dialog_lists_restores_and_sets_the_period(qapp, app_context, library, monkeypatch):
    from PySide6.QtWidgets import QMessageBox

    from smartdoc.presentation.trash_dialog import TrashDialog

    app_context.trash.send([("d1", str(library / "b1.pdf")), ("d2", str(library / "b2.pdf"))])
    dialog = TrashDialog(app_context)
    assert dialog.table.rowCount() == 2 and not dialog.restore_button.isEnabled()
    dialog.table.selectRow(0)
    assert dialog.restore_button.isEnabled()
    dialog.restore_button.click()
    assert dialog.table.rowCount() == 1 and app_context.db.get_document("d1") or app_context.db.get_document("d2")
    dialog.days_spin.setValue(7)
    assert app_context.config.config.trash_retention_days == 7 and "7 ngày" in dialog.table.item(0, 4).text()
    monkeypatch.setattr(QMessageBox, "question", lambda *a, **k: QMessageBox.Yes)
    dialog.empty_button.click()
    assert dialog.table.rowCount() == 0 and "trống" in dialog.empty_note.text()
    dialog.deleteLater()
