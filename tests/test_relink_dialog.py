# SPDX-License-Identifier: AGPL-3.0-or-later
from __future__ import annotations

import shutil
import time
from pathlib import Path

from PySide6.QtCore import Qt

from smartdoc.core.event_bus import LibraryFilesMissingEvent
from smartdoc.infrastructure.file_hash import sha256_file
from smartdoc.presentation.relink_dialog import RelinkDialog, method_label
from smartdoc.presentation.status_bar_panel import StatusBarPanel


def _book(app_context, folder: Path, name: str, content: bytes, doc_id: str) -> Path:
    path = folder / name
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(content)
    app_context.db.add_or_update_document(
        doc_id,
        {"title": f"Sách {name}", "author": "A", "file_path": str(path), "file_size": len(content), "extension": "pdf",
         "content_hash": sha256_file(str(path)), "created_at": 1.0},
    )
    return path


def _wait(qapp, dialog, timeout=10.0):
    deadline = time.time() + timeout
    while dialog._busy and time.time() < deadline:
        qapp.processEvents()
        time.sleep(0.01)
    qapp.processEvents()
    assert not dialog._busy, "the background task never reported back"


def _moved_library(tmp_path, app_context, count=2):
    new = tmp_path / "new"
    new.mkdir()
    for n in range(count):
        old = _book(app_context, tmp_path / "old", f"b{n}.pdf", f"content-{n}".encode() * 10, f"d{n}")
        shutil.move(str(old), new / f"renamed-{n}.pdf")
    app_context.relink.check_files()
    return new


def test_with_nothing_missing_the_dialog_says_so_and_offers_only_a_recheck(qapp, app_context):
    dialog = RelinkDialog(app_context)
    assert "Không có sách nào bị mất file" in dialog.summary_label.text()
    assert not dialog.folder_button.isEnabled() and dialog.recheck_button.isEnabled() and not dialog.apply_button.isEnabled()


def test_searching_lists_proposals_selected_by_default_and_changes_nothing(qapp, app_context, tmp_path):
    new = _moved_library(tmp_path, app_context)
    dialog = RelinkDialog(app_context)
    assert "2 sách không tìm thấy file" in dialog.summary_label.text()

    dialog.start_search(str(new))
    _wait(qapp, dialog)

    assert dialog.table.rowCount() == 2
    assert dialog.table.item(0, 0).checkState() == Qt.Checked
    assert "Trùng nội dung" in dialog.table.item(0, 4).text()
    assert app_context.db.count_missing() == 2  # nothing changed until the user confirms
    assert dialog.apply_button.isEnabled()


def test_confirming_updates_the_selected_books_only(qapp, app_context, tmp_path, monkeypatch):
    new = _moved_library(tmp_path, app_context)
    dialog = RelinkDialog(app_context)
    dialog.start_search(str(new))
    _wait(qapp, dialog)
    dialog.table.item(1, 0).setCheckState(Qt.Unchecked)  # the user drops the second row
    monkeypatch.setattr(dialog, "_confirm", lambda count: True)

    dialog.apply_button.click()

    assert app_context.db.count_missing() == 1
    assert "Đã cập nhật đường dẫn của 1 sách" in dialog.status_label.text()
    assert dialog.table.rowCount() == 1  # the applied one left the list, the dropped one stays


def test_declining_the_confirmation_changes_nothing(qapp, app_context, tmp_path, monkeypatch):
    new = _moved_library(tmp_path, app_context, count=1)
    dialog = RelinkDialog(app_context)
    dialog.start_search(str(new))
    _wait(qapp, dialog)
    monkeypatch.setattr(dialog, "_confirm", lambda count: False)

    dialog.apply_button.click()

    assert app_context.db.count_missing() == 1


def test_a_folder_without_the_books_says_so(qapp, app_context, tmp_path):
    _moved_library(tmp_path, app_context, count=1)
    empty = tmp_path / "empty"
    empty.mkdir()
    dialog = RelinkDialog(app_context)

    dialog.start_search(str(empty))
    _wait(qapp, dialog)

    assert "Không tìm thấy sách nào" in dialog.status_label.text() and dialog.table.rowCount() == 0


def test_recheck_finds_files_that_came_back(qapp, app_context, tmp_path):
    path = _book(app_context, tmp_path / "lib", "x.pdf", b"x" * 20, "x")
    content = path.read_bytes()
    path.unlink()
    app_context.relink.check_files()
    path.write_bytes(content)
    dialog = RelinkDialog(app_context)

    dialog.recheck_button.click()
    _wait(qapp, dialog)

    assert "0 sách không tìm thấy file" in dialog.status_label.text() and app_context.db.count_missing() == 0


def test_the_status_bar_shows_and_hides_the_missing_files_notice(qapp, app_context, tmp_path):
    panel = StatusBarPanel(app_context)
    assert panel.missing_label.isHidden()
    path = _book(app_context, tmp_path / "lib", "gone.pdf", b"g" * 20, "g")
    path.unlink()
    asked = []
    panel.relink_requested.connect(lambda: asked.append(True))

    app_context.relink.check_files()  # publishes LibraryFilesMissingEvent(count=1) through the bridge
    qapp.processEvents()

    assert not panel.missing_label.isHidden() and "1 sách không tìm thấy file" in panel.missing_label.text()
    panel.missing_label.clicked.emit()
    assert asked == [True]

    app_context.event_bus.publish(LibraryFilesMissingEvent(count=0))
    qapp.processEvents()
    assert panel.missing_label.isHidden()


def test_method_labels_read_naturally():
    assert method_label("hash") == "Trùng nội dung"
    assert "tên" in method_label("name+size")
