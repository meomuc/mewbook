import time
from pathlib import Path

import fitz
import pytest

from smartdoc.application.import_queue import ImportQueueManager
from smartdoc.core.event_bus import (
    FileDetectedEvent,
    ImportBatchCompletedEvent,
    ImportProgressEvent,
    LibraryUpdatedEvent,
)


def _make_pdf(path: Path, title: str, author: str, body_text: str) -> None:
    doc = fitz.open()
    page = doc.new_page()
    page.insert_text((72, 72), body_text)
    doc.set_metadata({"title": title, "author": author})
    doc.save(str(path))
    doc.close()


def _wait_until(predicate, timeout: float = 5.0) -> bool:
    deadline = time.time() + timeout
    while time.time() < deadline:
        if predicate():
            return True
        time.sleep(0.05)
    return predicate()


@pytest.fixture
def manager(app_context):
    mgr = ImportQueueManager(app_context, num_workers=2)
    mgr.start()
    yield mgr
    mgr.stop()


def test_add_file_indexes_pdf_into_database(tmp_path, app_context, manager):
    pdf_path = tmp_path / "book.pdf"
    _make_pdf(pdf_path, "Hello PDF", "Test Author", "Hello Python World")

    progress: list[tuple[int, int]] = []
    app_context.event_bus.subscribe(ImportProgressEvent, lambda e: progress.append((e.done, e.total)))

    manager.add_file(str(pdf_path))
    assert _wait_until(lambda: progress == [(1, 1)])

    results = app_context.db.search("Hello")
    assert any(r["title"] == "Hello PDF" for r in results)


def test_file_detected_event_auto_enqueues(tmp_path, app_context, manager):
    pdf_path = tmp_path / "auto.pdf"
    _make_pdf(pdf_path, "Auto Indexed", "Someone", "auto content")

    updated_events = []
    app_context.event_bus.subscribe(LibraryUpdatedEvent, lambda e: updated_events.append(e))

    app_context.event_bus.publish(FileDetectedEvent(file_path=str(pdf_path)))
    assert _wait_until(lambda: len(updated_events) == 1)

    results = app_context.db.search("Auto")
    assert any(r["title"] == "Auto Indexed" for r in results)


def test_imported_pdf_gets_a_content_hash(tmp_path, app_context, manager):
    pdf_path = tmp_path / "book.pdf"
    _make_pdf(pdf_path, "Hashed", "Author", "content")

    manager.add_file(str(pdf_path))
    assert _wait_until(lambda: len(app_context.db.list_all_documents()) == 1)

    doc = app_context.db.list_all_documents()[0]
    assert doc["content_hash"] is not None
    assert len(doc["content_hash"]) == 64  # sha256 hex digest


def test_two_files_with_identical_bytes_get_the_same_content_hash(tmp_path, app_context, manager):
    pdf_path = tmp_path / "original.pdf"
    _make_pdf(pdf_path, "Same Book", "Author", "identical content")
    copy_path = tmp_path / "copy.pdf"
    copy_path.write_bytes(pdf_path.read_bytes())

    manager.add_file(str(pdf_path))
    manager.add_file(str(copy_path))
    assert _wait_until(lambda: len(app_context.db.list_all_documents()) == 2)

    hashes = {d["content_hash"] for d in app_context.db.list_all_documents()}
    assert len(hashes) == 1  # both files hash the same

    duplicate_groups = app_context.db.find_duplicate_groups_by_content_hash()
    assert len(duplicate_groups) == 1
    assert len(duplicate_groups[0]) == 2


def test_scan_folder_enqueues_supported_files_recursively(tmp_path, app_context, manager):
    (tmp_path / "sub").mkdir()
    _make_pdf(tmp_path / "top.pdf", "Top Book", "A", "top content")
    _make_pdf(tmp_path / "sub" / "nested.pdf", "Nested Book", "B", "nested content")
    (tmp_path / "notes.txt").write_text("ignored")

    progress: list[tuple[int, int]] = []
    app_context.event_bus.subscribe(ImportProgressEvent, lambda e: progress.append((e.done, e.total)))

    enqueued = manager.scan_folder(str(tmp_path))
    assert enqueued == 2
    assert _wait_until(lambda: len(progress) == 2 and progress[-1] == (2, 2))

    titles = {r["title"] for r in app_context.db.list_all_documents()}
    assert titles == {"Top Book", "Nested Book"}


def test_unsupported_extension_is_skipped_without_crashing(tmp_path, app_context, manager):
    txt_path = tmp_path / "notes.txt"
    txt_path.write_text("just notes")

    progress: list[tuple[int, int]] = []
    app_context.event_bus.subscribe(ImportProgressEvent, lambda e: progress.append((e.done, e.total)))

    manager.add_file(str(txt_path))
    assert _wait_until(lambda: progress == [(1, 1)])
    assert app_context.db.search("notes") == []


def test_reimporting_the_same_path_is_skipped_as_a_duplicate(tmp_path, app_context, manager):
    pdf_path = tmp_path / "book.pdf"
    _make_pdf(pdf_path, "Once", "Author", "content")

    manager.add_file(str(pdf_path))
    assert _wait_until(lambda: len(app_context.db.list_all_documents()) == 1)
    updated_at_first_pass = app_context.db.list_all_documents()[0]["updated_at"]

    batches: list[ImportBatchCompletedEvent] = []
    app_context.event_bus.subscribe(ImportBatchCompletedEvent, lambda e: batches.append(e))
    manager.add_files([str(pdf_path)])  # same path, re-scanned

    assert _wait_until(lambda: len(batches) == 1)
    assert (batches[0].success, batches[0].duplicate, batches[0].failed) == (0, 1, 0)
    # Not silently re-extracted/re-written either.
    assert app_context.db.list_all_documents()[0]["updated_at"] == updated_at_first_pass


def test_add_files_batch_reports_success_duplicate_and_failed_counts(tmp_path, app_context, manager):
    already_indexed = tmp_path / "already.pdf"
    _make_pdf(already_indexed, "Already Indexed", "Author", "content")
    manager.add_file(str(already_indexed))
    assert _wait_until(lambda: len(app_context.db.list_all_documents()) == 1)

    new_pdf = tmp_path / "new.pdf"
    _make_pdf(new_pdf, "Brand New", "Author", "content")
    unsupported = tmp_path / "notes.txt"
    unsupported.write_text("not a book")

    batches: list[ImportBatchCompletedEvent] = []
    app_context.event_bus.subscribe(ImportBatchCompletedEvent, lambda e: batches.append(e))

    enqueued = manager.add_files([str(already_indexed), str(new_pdf), str(unsupported)])
    assert enqueued == 3
    assert _wait_until(lambda: len(batches) == 1)
    assert (batches[0].success, batches[0].duplicate, batches[0].failed) == (1, 1, 1)
