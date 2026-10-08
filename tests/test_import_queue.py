import time
from pathlib import Path

import fitz
import pytest

from smartdoc.application.import_queue import ImportQueueManager
from smartdoc.core.event_bus import (
    DocumentIndexedEvent,
    FileDetectedEvent,
    ImportBatchCompletedEvent,
    ImportProgressEvent,
    LibraryUpdatedEvent,
)
from tests._metadata_helpers import make_epub


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


def test_add_file_indexes_an_epubs_publisher_year_language_and_isbn(tmp_path, app_context, manager):
    """The detail sidebar reads publisher/pub_year/language/isbn straight off the document row it gets from the
    database -- these must already be there after a plain import, not only after running "Tìm thêm thông tin"."""
    epub_path = tmp_path / "book.epub"
    make_epub(
        epub_path,
        metadata=(
            '    <dc:title>Sách Có Đủ Thông Tin</dc:title>\n'
            '    <dc:creator opf:role="aut">Tác Giả</dc:creator>\n'
            '    <dc:publisher>NXB Trẻ</dc:publisher>\n'
            '    <dc:language>vi</dc:language>\n'
            '    <dc:date>2019-01-01</dc:date>\n'
            '    <dc:identifier id="uid">urn:isbn:9786041234567</dc:identifier>\n'
        ),
    )

    manager.add_file(str(epub_path))
    assert _wait_until(lambda: app_context.db.search("Sách") != [])

    doc = app_context.db.get_document(app_context.db.search("Sách")[0]["id"])
    assert doc["publisher"] == "NXB Trẻ" and doc["language"] == "vi"
    assert doc["pub_year"] == 2019 and doc["isbn"] == "9786041234567"


def test_file_detected_event_auto_enqueues(tmp_path, app_context, manager):
    pdf_path = tmp_path / "auto.pdf"
    _make_pdf(pdf_path, "Auto Indexed", "Someone", "auto content")

    updated_events = []
    app_context.event_bus.subscribe(LibraryUpdatedEvent, lambda e: updated_events.append(e))

    app_context.event_bus.publish(FileDetectedEvent(file_path=str(pdf_path)))
    assert _wait_until(lambda: len(updated_events) == 1)

    results = app_context.db.search("Auto")
    assert any(r["title"] == "Auto Indexed" for r in results)


def test_a_file_nobody_shares_a_size_with_is_not_read_through_to_hash_it(tmp_path, app_context, manager):
    """Only files of equal size can be identical, so import does not hash a file whose size is unique (that read the whole
    file of every import); the hash comes when a same-size file shows up, or when duplicates are looked for."""
    pdf_path = tmp_path / "book.pdf"
    _make_pdf(pdf_path, "Hashed", "Author", "content")

    manager.add_file(str(pdf_path))
    assert _wait_until(lambda: len(app_context.db.list_all_documents()) == 1)
    assert app_context.db.list_all_documents()[0]["content_hash"] is None

    same_size = tmp_path / "other.pdf"
    same_size.write_bytes(pdf_path.read_bytes())
    manager.add_file(str(same_size))
    assert _wait_until(lambda: len(app_context.db.list_all_documents()) == 2)
    hashes = [d["content_hash"] for d in app_context.db.list_all_documents()]
    assert all(h and len(h) == 64 for h in hashes) and len(set(hashes)) == 1  # both got theirs (sha256 hex), and they match


def test_two_files_with_identical_bytes_get_the_same_content_hash(tmp_path, app_context, manager):
    pdf_path = tmp_path / "original.pdf"
    _make_pdf(pdf_path, "Same Book", "Author", "identical content")
    copy_path = tmp_path / "copy.pdf"
    copy_path.write_bytes(pdf_path.read_bytes())

    manager.add_file(str(pdf_path))
    manager.add_file(str(copy_path))
    assert _wait_until(lambda: len(app_context.db.list_all_documents()) == 2)

    from smartdoc.application.duplicate_finder import DuplicateEngine

    engine = DuplicateEngine(app_context)
    engine.hash_pending()  # what the duplicate finder does first (two workers may both have seen "no other book of that size")
    hashes = {d["content_hash"] for d in app_context.db.list_all_documents()}
    assert len(hashes) == 1 and None not in hashes  # both files hash the same
    assert len(engine.find_exact_duplicates()) == 1

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


def test_same_physical_file_via_differently_styled_path_is_not_duplicated(tmp_path, app_context, manager):
    """S1-xx dup-books: a folder scan (os.walk, native separators) and a later
    re-detection of the same file spelled with forward slashes (as a watcher
    or a differently-built path string might) must resolve to the same
    document id, not create a second row. See domain.models.normalize_path_key
    and DatabaseManager.find_id_by_path."""
    pdf_path = tmp_path / "book.pdf"
    _make_pdf(pdf_path, "Once", "Author", "content")

    manager.add_file(str(pdf_path))
    assert _wait_until(lambda: len(app_context.db.list_all_documents()) == 1)

    forward_slash_path = str(pdf_path).replace("\\", "/")
    assert forward_slash_path != str(pdf_path)  # the test only proves something if the strings actually differ

    batches: list[ImportBatchCompletedEvent] = []
    app_context.event_bus.subscribe(ImportBatchCompletedEvent, lambda e: batches.append(e))
    manager.add_files([forward_slash_path])

    assert _wait_until(lambda: len(batches) == 1)
    assert (batches[0].success, batches[0].duplicate, batches[0].failed) == (0, 1, 0)
    assert len(app_context.db.list_all_documents()) == 1


def test_add_files_tracked_returns_batch_id_and_tags_its_own_events(tmp_path, app_context, manager):
    pdf_path = tmp_path / "tracked.pdf"
    _make_pdf(pdf_path, "Tracked Book", "Author", "content")

    indexed: list[DocumentIndexedEvent] = []
    completed: list[ImportBatchCompletedEvent] = []
    app_context.event_bus.subscribe(DocumentIndexedEvent, lambda e: indexed.append(e))
    app_context.event_bus.subscribe(ImportBatchCompletedEvent, lambda e: completed.append(e))

    batch_id = manager.add_files_tracked([str(pdf_path)])
    assert batch_id

    assert _wait_until(lambda: len(completed) == 1)
    assert completed[0].batch_id == batch_id
    assert len(indexed) == 1
    assert indexed[0].batch_id == batch_id


def test_add_files_tracked_returns_none_for_empty_list(manager):
    assert manager.add_files_tracked([]) is None


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


def test_batch_completion_lists_the_new_documents_only(tmp_path, app_context, manager):
    already_indexed = tmp_path / "already.pdf"
    _make_pdf(already_indexed, "Already Indexed", "Author", "content")
    manager.add_file(str(already_indexed))
    assert _wait_until(lambda: len(app_context.db.list_all_documents()) == 1)

    new_pdf = tmp_path / "new.pdf"
    _make_pdf(new_pdf, "Brand New", "Author", "content")
    batches: list[ImportBatchCompletedEvent] = []
    app_context.event_bus.subscribe(ImportBatchCompletedEvent, lambda e: batches.append(e))

    manager.add_files([str(already_indexed), str(new_pdf)])
    assert _wait_until(lambda: len(batches) == 1)

    new_ids = [d["id"] for d in app_context.db.list_all_documents() if d["title"] == "Brand New"]
    assert len(new_ids) == 1
    assert list(batches[0].doc_ids) == new_ids  # the duplicate is not offered for classification


def test_pending_count_reports_files_queued_or_in_progress(manager, tmp_path):
    assert manager.pending_count() == 0

    pdfs = []
    for index in range(3):
        pdf = tmp_path / f"book{index}.pdf"
        _make_pdf(pdf, f"Title {index}", "Author", "some body text")
        pdfs.append(str(pdf))
    manager.add_files(pdfs)

    assert 0 <= manager.pending_count() <= 3  # workers may already have finished some
    assert _wait_until(lambda: manager.pending_count() == 0)  # and it settles back to idle


def test_watcher_files_are_reported_as_one_batch_after_a_quiet_moment(tmp_path, app_context, manager, monkeypatch):
    from smartdoc.application import import_queue

    monkeypatch.setattr(import_queue, "WATCH_BATCH_QUIET_SECONDS", 0.4)
    batches: list[ImportBatchCompletedEvent] = []
    app_context.event_bus.subscribe(ImportBatchCompletedEvent, lambda e: batches.append(e))
    for index in range(3):
        pdf = tmp_path / f"w{index}.pdf"
        _make_pdf(pdf, f"Watched {index}", "Author", "content")
        app_context.event_bus.publish(FileDetectedEvent(file_path=str(pdf)))

    assert _wait_until(lambda: len(batches) == 1, timeout=6.0)
    time.sleep(0.6)  # no second summary for the same burst
    assert len(batches) == 1
    assert (batches[0].success, batches[0].duplicate, batches[0].failed) == (3, 0, 0)


def test_a_batch_lists_the_files_that_failed(tmp_path, app_context, manager):
    bad = tmp_path / "notes.txt"
    bad.write_text("not a book")
    batches: list[ImportBatchCompletedEvent] = []
    app_context.event_bus.subscribe(ImportBatchCompletedEvent, lambda e: batches.append(e))

    manager.add_files([str(bad)])
    assert _wait_until(lambda: len(batches) == 1)
    assert batches[0].failed_paths == (str(bad),)


def test_stop_button_drops_the_waiting_files_and_reports_what_was_done(tmp_path, app_context):
    manager = ImportQueueManager(app_context, num_workers=1)  # not started: every file is still waiting
    batches: list[ImportBatchCompletedEvent] = []
    progress: list[tuple[int, int]] = []
    app_context.event_bus.subscribe(ImportBatchCompletedEvent, lambda e: batches.append(e))
    app_context.event_bus.subscribe(ImportProgressEvent, lambda e: progress.append((e.done, e.total)))
    paths = []
    for index in range(3):
        pdf = tmp_path / f"s{index}.pdf"
        _make_pdf(pdf, f"S {index}", "Author", "content")
        paths.append(str(pdf))
    manager.add_files(paths)
    assert manager.pending_count() == 3

    assert manager.cancel_pending() == 3

    assert manager.pending_count() == 0
    assert len(batches) == 1 and (batches[0].success, batches[0].failed) == (0, 0)
    assert progress[-1] == (0, 0)
