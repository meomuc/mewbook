# SPDX-License-Identifier: AGPL-3.0-or-later
"""Reading PDFs in worker processes: same result as in-process, and a pool that cannot run never fails a book."""
from __future__ import annotations

from concurrent.futures import BrokenExecutor

from smartdoc.application.import_queue import ImportQueueManager
from smartdoc.infrastructure.pdf_extractor import PdfExtractor
from smartdoc.infrastructure.pdf_worker import read_pdf
from tests.test_import_queue import _make_pdf, _wait_until


def test_read_pdf_returns_plain_values_a_process_can_send_back(tmp_path):
    path = tmp_path / "b.pdf"
    _make_pdf(path, "Tiêu đề", "Tác giả", "noi dung trang mot")
    metadata, png, text = read_pdf(str(path), 10)
    assert metadata["title"] == "Tiêu đề" and metadata["page_count"] == 1
    assert png and png.startswith(b"\x89PNG") and "noi dung trang mot" in text


def test_the_same_pdf_gives_the_same_book_with_and_without_the_pool(tmp_path, app_context):
    path = tmp_path / "b.pdf"
    _make_pdf(path, "Cùng một sách", "Tác giả", "noi dung")
    plain = PdfExtractor(app_context).extract_all(str(path), "id-plain")
    manager = ImportQueueManager(app_context, num_workers=2, use_process_pool=True)
    manager.start()
    try:
        pooled = manager._pdf_extractor.extract_all(str(path), "id-pool")
    finally:
        manager.stop()
    assert plain[0] == pooled[0] and plain[2] == pooled[2]
    assert plain[1] and pooled[1] and pooled[1].endswith(".webp")  # the parent saved the cover picture the worker rendered


def test_importing_through_the_pool_indexes_the_book(tmp_path, app_context):
    path = tmp_path / "b.pdf"
    _make_pdf(path, "Qua tiến trình con", "Tác giả", "tukhoahiem")
    manager = ImportQueueManager(app_context, num_workers=2, use_process_pool=True)
    manager.start()
    try:
        manager.add_files([str(path)])
        assert _wait_until(lambda: app_context.db.find_id_by_path(str(path)) is not None, timeout=30)
    finally:
        manager.stop()
    assert app_context.db.query_documents(fts_query="tukhoahiem")[0]["title"] == "Qua tiến trình con"


def test_a_pool_that_cannot_run_falls_back_to_reading_in_process(tmp_path, app_context):
    class Broken:
        def submit(self, *_a, **_k):
            raise BrokenExecutor("no workers here")

    path = tmp_path / "b.pdf"
    _make_pdf(path, "Vẫn nhập được", "Tác giả", "noi dung")
    extractor = PdfExtractor(app_context)
    extractor.pool = Broken()
    metadata, cover, text = extractor.extract_all(str(path), "id1")
    assert metadata["title"] == "Vẫn nhập được" and cover and "noi dung" in text
    assert extractor.pool is None  # switched off for the rest of the session, not retried for every book


def test_a_corrupt_pdf_is_reported_as_a_bare_record_not_an_exception(tmp_path, app_context):
    path = tmp_path / "bad.pdf"
    path.write_bytes(b"not a pdf at all")
    manager = ImportQueueManager(app_context, num_workers=1, use_process_pool=True)
    manager.start()
    try:
        metadata, cover, text = manager._pdf_extractor.extract_all(str(path), "id1")
    finally:
        manager.stop()
    assert metadata["extension"] == "pdf" and cover is None and text == ""


def test_shutting_down_mid_import_does_not_file_the_book_as_an_empty_record(tmp_path, app_context):
    from concurrent.futures import CancelledError

    import pytest

    class Cancelled:
        def submit(self, *_a, **_k):
            raise CancelledError()

    path = tmp_path / "b.pdf"
    _make_pdf(path, "Đang nhập thì tắt", "Tác giả", "noi dung")
    extractor = PdfExtractor(app_context)
    extractor.pool = Cancelled()
    with pytest.raises(CancelledError):
        extractor.extract_all(str(path), "id1")  # the worker loop logs it as a failed import and writes nothing


def test_a_pdf_that_never_finishes_is_reported_as_unreadable(tmp_path, app_context, monkeypatch):
    from concurrent.futures import Future

    from smartdoc.infrastructure import pdf_extractor

    monkeypatch.setattr(pdf_extractor, "POOL_TIMEOUT_SECONDS", 0.05)

    class Hangs:
        def submit(self, *_a, **_k):
            return Future()  # never completed

    extractor = PdfExtractor(app_context)
    extractor.pool = Hangs()
    metadata, cover, text = extractor.extract_all(str(tmp_path / "x.pdf"), "id1")
    assert metadata["extension"] == "pdf" and cover is None and text == ""
