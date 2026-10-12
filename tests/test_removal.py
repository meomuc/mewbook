# SPDX-License-Identifier: AGPL-3.0-or-later
"""The one entry point that decides what happens to a book's file and library row when the user removes it."""
from __future__ import annotations

import pytest

from smartdoc.application.removal import RemovalMode
from smartdoc.core.event_bus import LibraryUpdatedEvent


@pytest.fixture
def library(app_context, tmp_path):
    folder = tmp_path / "books"
    folder.mkdir()
    for n in (1, 2, 3):
        (folder / f"b{n}.pdf").write_bytes(b"x" * n)
        app_context.db.add_or_update_document(f"d{n}", {
            "title": f"Sách {n}", "author": "Tác giả", "file_path": str(folder / f"b{n}.pdf"), "extension": "pdf",
            "file_size": n, "tags": "a,b", "created_at": 5.0}, extracted_text=f"nội dung số {n}")
    return folder


def _events(app_context) -> list:
    events: list = []
    app_context.event_bus.subscribe(LibraryUpdatedEvent, events.append)
    return events


def test_trash_file_moves_the_file_and_keeps_the_row_as_trashed(app_context, library):
    events = _events(app_context)
    result = app_context.removal.remove([("d1", str(library / "b1.pdf"))], RemovalMode.TRASH_FILE)
    assert result.moved == ["d1"] and not result.failed
    assert not (library / "b1.pdf").exists() and (library / "b2.pdf").exists()
    doc = app_context.db.get_document("d1")
    assert doc is not None and doc["file_status"] == "trashed"
    assert events


def test_trash_file_reports_progress(app_context, library):
    told: list[tuple[int, int]] = []
    items = [("d1", str(library / "b1.pdf")), ("d2", str(library / "b2.pdf"))]
    app_context.removal.remove(items, RemovalMode.TRASH_FILE, lambda done, total: told.append((done, total)))
    assert told and told[-1][1] == 2


def test_trash_file_for_a_file_that_is_already_gone_just_leaves_the_library(app_context, library):
    (library / "b3.pdf").unlink()
    result = app_context.removal.remove([("d3", str(library / "b3.pdf"))], RemovalMode.TRASH_FILE)
    assert result.missing == ["d3"] and app_context.db.get_document("d3") is None


def test_forget_record_deletes_the_row_and_leaves_the_file(app_context, library):
    events = _events(app_context)
    result = app_context.removal.remove([("d1", str(library / "b1.pdf"))], RemovalMode.FORGET_RECORD)
    assert result.moved == ["d1"] and not result.failed
    assert app_context.db.get_document("d1") is None
    assert (library / "b1.pdf").exists()
    assert len(events) == 1


def test_forget_record_remembers_the_path_so_the_watcher_does_not_bring_the_book_back(app_context, library):
    app_context.removal.remove([("d1", str(library / "b1.pdf"))], RemovalMode.FORGET_RECORD)
    assert app_context.db.is_path_excluded(str(library / "b1.pdf"))
    assert not app_context.db.is_path_excluded(str(library / "b2.pdf"))


def test_forget_record_batches_many_books_into_one_event(app_context, library):
    events = _events(app_context)
    app_context.removal.remove([("d1", str(library / "b1.pdf")), ("d2", str(library / "b2.pdf"))], RemovalMode.FORGET_RECORD)
    assert {d["id"] for d in app_context.db.list_all_documents()} == {"d3"}
    assert len(events) == 1


def test_an_empty_list_changes_nothing_and_publishes_nothing(app_context, library):
    events = _events(app_context)
    for mode in RemovalMode:
        result = app_context.removal.remove([], mode)
        assert not result.moved and not result.missing and not result.failed
    assert events == []
