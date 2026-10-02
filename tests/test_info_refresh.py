# SPDX-License-Identifier: AGPL-3.0-or-later
"""InfoRefresh (application/info_refresh.py): the file-facts scan service brings file facts up to date, counts
what changed, and never touches what a person typed. Its own standalone dialog was retired when "Cập nhật thông
tin sách" merged this with the bibliographic lookup (see test_metadata_batch_update.py and
test_metadata_batch_dialog.py for the merged tool's own tests -- `InfoRefresh.refresh_one()`, exercised here per
document, is what that merged run calls directly per book instead of going through `run()`'s own query)."""
from __future__ import annotations

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


def test_refresh_one_is_the_per_document_entry_point_the_merged_tool_reuses(app_context, library):
    """The merged "Cập nhật thông tin sách" (metadata_batch_update.py) calls `refresh_one()` directly, per its own
    bulk-fetched row, instead of `run()`'s whole-library query -- this is the public method that keeps working for
    that caller (renamed from `_refresh_one` on purpose: two collaborating services now use it deliberately)."""
    row = app_context.db.documents_for_batch_update(["d1"], only_missing_info=False)[0]
    assert app_context.info_refresh.refresh_one(row) is True
    assert app_context.db.get_document("d1")["content_hash"]
