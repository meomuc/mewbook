# SPDX-License-Identifier: AGPL-3.0-or-later
"""Cập nhật ngay: the on-demand scan brings file facts up to date, counts what changed, and never touches what a person typed."""
from __future__ import annotations

import time

import pytest

from smartdoc.core.event_bus import LibraryUpdatedEvent


@pytest.fixture
def library(app_context, tmp_path):
    for n in (1, 2, 3):
        path = tmp_path / f"b{n}.txt"
        path.write_bytes(b"data" * n)
        app_context.db.add_or_update_document(f"d{n}", {"title": f"Tên tôi sửa {n}", "author": "Tác giả", "file_path": str(path),
                                                        "extension": "txt", "file_size": 0, "created_at": 1.0})
    return tmp_path


def test_it_fills_in_hash_size_and_fingerprint_and_counts_the_books(app_context, library):
    events = []
    app_context.event_bus.subscribe(LibraryUpdatedEvent, events.append)
    progress = []
    result = app_context.info_refresh.run(progress=lambda d, t: progress.append((d, t)))
    assert (result.checked, result.updated, result.missing) == (3, 3, 0) and events
    row = app_context.db.get_document("d2")
    assert row["file_size"] == 8 and row["content_hash"] and row["fingerprint"] is not None
    assert row["title"] == "Tên tôi sửa 2"  # what the person typed is untouched
    assert progress[-1] == (3, 3)


def test_a_second_pass_finds_nothing_new(app_context, library):
    app_context.info_refresh.run()
    assert app_context.info_refresh.run().updated == 0


def test_a_file_that_changed_on_disk_is_picked_up_and_a_missing_one_is_counted(app_context, library):
    app_context.info_refresh.run()
    old_hash = app_context.db.get_document("d1")["content_hash"]
    (library / "b1.txt").write_bytes(b"something else entirely")
    (library / "b3.txt").unlink()
    result = app_context.info_refresh.run()
    assert result.updated == 1 and result.missing == 1
    assert app_context.db.get_document("d1")["content_hash"] != old_hash
    assert app_context.db.get_document("d3")["file_status"] == "missing"


def test_it_can_be_cancelled_between_books(app_context, library):
    result = app_context.info_refresh.run(should_cancel=lambda: True)
    assert result.cancelled and result.checked == 0


def test_the_window_runs_in_the_background_and_reports_the_number(qapp, app_context, library):
    from smartdoc.presentation.info_refresh_dialog import InfoRefreshDialog

    dialog = InfoRefreshDialog(app_context)
    dialog.start()
    deadline = time.time() + 10
    while dialog._running and time.time() < deadline:
        qapp.processEvents()
        time.sleep(0.01)
    assert "3 / 3 sách" in dialog.status_label.text() and dialog.action_button.text() == "Đóng"
    dialog.deleteLater()
