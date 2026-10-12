# SPDX-License-Identifier: AGPL-3.0-or-later
"""The one entry point that decides what happens to a book's file and library row when the user removes it."""
from __future__ import annotations

import time

import pytest

from smartdoc.application.removal import RemovalMode
from smartdoc.application.trash_service import KIND_FILE, KIND_LIBRARY
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


def test_removing_from_the_library_remembers_only_the_removed_paths(app_context, library):
    app_context.removal.remove([("d1", str(library / "b1.pdf"))], RemovalMode.REMOVE_FROM_LIBRARY)
    assert app_context.db.is_path_excluded(str(library / "b1.pdf"))
    assert not app_context.db.is_path_excluded(str(library / "b2.pdf"))


def test_removing_many_books_publishes_one_event(app_context, library):
    events = _events(app_context)
    items = [("d1", str(library / "b1.pdf")), ("d2", str(library / "b2.pdf"))]
    app_context.removal.remove(items, RemovalMode.REMOVE_FROM_LIBRARY)
    assert _library_ids(app_context) == {"d3"}
    assert len(events) == 1


def test_adding_a_removed_file_by_hand_brings_the_book_back_with_its_data(app_context, library):
    app_context.removal.remove([("d1", str(library / "b1.pdf"))], RemovalMode.REMOVE_FROM_LIBRARY)
    assert app_context.trash.restore_removed_at([str(library / "b1.pdf"), str(library / "other.pdf")]) == 1
    assert _library_ids(app_context) == {"d1", "d2", "d3"} and app_context.db.get_document("d1")["tags"] == "a,b"
    assert not app_context.trash.list_items()


def _library_ids(app_context) -> set[str]:
    return {d["id"] for d in app_context.db.query_documents()}


def test_remove_from_library_keeps_the_file_and_hides_the_book_everywhere(app_context, library):
    events = _events(app_context)
    result = app_context.removal.remove([("d1", str(library / "b1.pdf"))], RemovalMode.REMOVE_FROM_LIBRARY)
    assert result.moved == ["d1"] and not result.failed
    assert (library / "b1.pdf").exists()  # the file is never touched
    assert _library_ids(app_context) == {"d2", "d3"}
    assert app_context.db.count_documents_matching() == 2
    assert [row[0] for row in app_context.db.list_facet_rows()].count("d1") == 0
    assert app_context.db.is_path_excluded(str(library / "b1.pdf"))  # the watcher must not bring it back
    assert events


def test_a_removed_book_is_listed_in_the_trash_with_its_kind_and_place(app_context, library):
    app_context.removal.remove([("d1", str(library / "b1.pdf"))], RemovalMode.REMOVE_FROM_LIBRARY)
    (item,) = app_context.trash.list_items()
    assert item.kind == KIND_LIBRARY and item.title == "Sách 1"
    assert item.original_path == str(library / "b1.pdf") and item.days_left() == 30


def test_a_book_trashed_together_with_its_file_is_hidden_from_the_library_too(app_context, library):
    app_context.removal.remove([("d1", str(library / "b1.pdf"))], RemovalMode.TRASH_FILE)
    assert _library_ids(app_context) == {"d2", "d3"}
    (item,) = app_context.trash.list_items()
    assert item.kind == KIND_FILE


def test_restoring_a_removed_book_brings_it_back_with_its_data(app_context, library):
    app_context.removal.remove([("d1", str(library / "b1.pdf"))], RemovalMode.REMOVE_FROM_LIBRARY)
    (item,) = app_context.trash.list_items()
    where = app_context.trash.restore(item.item_id)
    assert where == library / "b1.pdf" and where.exists()
    assert _library_ids(app_context) == {"d1", "d2", "d3"}
    assert app_context.db.get_document("d1")["tags"] == "a,b"
    assert not app_context.db.is_path_excluded(str(library / "b1.pdf"))
    assert not app_context.trash.list_items()


def test_deleting_a_removed_book_for_good_deletes_the_row_and_never_the_file(app_context, library):
    app_context.removal.remove([("d1", str(library / "b1.pdf"))], RemovalMode.REMOVE_FROM_LIBRARY)
    (item,) = app_context.trash.list_items()
    app_context.trash.delete_forever(item.item_id)
    assert app_context.db.get_document("d1") is None
    assert (library / "b1.pdf").exists()


def test_a_removed_book_expires_after_the_retention_period_and_its_file_stays(app_context, library):
    app_context.removal.remove([("d1", str(library / "b1.pdf"))], RemovalMode.REMOVE_FROM_LIBRARY)
    now = time.time()
    assert app_context.trash.purge_expired(now + 29 * 86_400) == 0
    assert app_context.trash.purge_expired(now + 31 * 86_400) == 1
    assert app_context.db.get_document("d1") is None and (library / "b1.pdf").exists()


def test_an_empty_list_changes_nothing_and_publishes_nothing(app_context, library):
    events = _events(app_context)
    for mode in RemovalMode:
        result = app_context.removal.remove([], mode)
        assert not result.moved and not result.missing and not result.failed
    assert events == []
