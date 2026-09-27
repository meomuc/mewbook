# SPDX-License-Identifier: AGPL-3.0-or-later
"""E-books are searchable by their text (they had none: only a PDF's first pages were indexed), for new imports and, once, for
the ones already in the library."""
from __future__ import annotations

import struct
import time

import pytest

from smartdoc.application.content_backfill import ContentBackfill
from smartdoc.application.import_queue import ImportQueueManager
from smartdoc.infrastructure.text_sampler import WORDS_PER_PAGE, extract_search_text
from tests._smart_helpers import write_epub


def _write_mobi(path, text: str):
    """The smallest MOBI/PalmDOC this reader understands: uncompressed, one text record."""
    body = text.encode("cp1252")
    record0 = struct.pack(">HHIHHH", 1, 0, len(body), 1, 4096, 0) + b"\0\0"
    first = 78 + 16
    table = struct.pack(">II", first, 0) + struct.pack(">II", first + len(record0), 0)
    header = b"\0" * 76 + struct.pack(">H", 2)
    path.write_bytes(header + table + record0 + body)
    return path


def _wait(predicate, timeout=10.0):
    end = time.time() + timeout
    while time.time() < end:
        if predicate():
            return True
        time.sleep(0.05)
    return predicate()


def test_the_text_of_an_epub_is_read_up_to_the_page_setting(tmp_path):
    epub = write_epub(tmp_path / "b.epub", "thám tử điều tra vụ án mạng bí ẩn hiện trường".split(), repeat=1000)  # 10,000 words
    two_pages = extract_search_text(str(epub), "epub", 2)
    assert len(two_pages.split()) == 2 * WORDS_PER_PAGE
    assert len(extract_search_text(str(epub), "epub", 10).split()) == 10 * WORDS_PER_PAGE


def test_a_mobi_is_read_too(tmp_path):
    mobi = _write_mobi(tmp_path / "b.mobi", "<p>" + "doc mot tu khoa lam sang " * 200 + "</p>")
    assert "khoa" in extract_search_text(str(mobi), "mobi", 5)


@pytest.mark.parametrize("name, data", [("broken.epub", b"not a zip"), ("tiny.mobi", b"x" * 10), ("empty.epub", b"")])
def test_unreadable_files_give_no_text_and_never_raise(tmp_path, name, data):
    path = tmp_path / name
    path.write_bytes(data)
    assert extract_search_text(str(path), None, 10) == ""
    assert extract_search_text(str(tmp_path / "missing.epub"), "epub", 10) == ""
    assert extract_search_text(str(path), "pdf", 10) == ""  # a PDF is PdfExtractor's job


def test_scrambled_legacy_encodings_are_not_indexed_as_text(tmp_path):
    epub = write_epub(tmp_path / "junk.epub", ["Phµng", "¶i", "·n"], repeat=200)  # TCVN3 read as latin-1
    assert extract_search_text(str(epub), "epub", 10) == ""


def test_an_imported_epub_can_be_found_by_a_word_from_inside_it(tmp_path, app_context):
    epub = write_epub(tmp_path / "b.epub", ["nhan", "vat", "tukhoanoibo", "hiem"], repeat=100)
    manager = ImportQueueManager(app_context, num_workers=1)
    manager.start()
    try:
        manager.add_files([str(epub)])
        assert _wait(lambda: app_context.db.find_id_by_path(str(epub)) is not None)
    finally:
        manager.stop()
    assert len(app_context.db.query_documents(fts_query="tukhoanoibo")) == 1


def test_the_backfill_makes_books_imported_earlier_searchable_once(tmp_path, app_context):
    epub = write_epub(tmp_path / "old.epub", ["tukhoacu", "nhan"], repeat=50)
    app_context.db.add_or_update_document("e1", {"title": "Sách cũ", "author": "A", "file_path": str(epub), "extension": "epub", "created_at": 1.0})
    app_context.db.add_or_update_document("p1", {"title": "Một PDF", "author": "A", "file_path": str(tmp_path / "x.pdf"), "extension": "pdf", "created_at": 1.0})
    assert app_context.db.query_documents(fts_query="tukhoacu") == []

    backfill = ContentBackfill(app_context, batch_size=1)
    assert backfill.run() == 1
    assert [d["id"] for d in app_context.db.query_documents(fts_query="tukhoacu")] == ["e1"]
    assert app_context.config.config.content_backfill_done is True
    backfill.start()  # done: nothing starts again
    assert backfill._thread is None


def test_the_backfill_that_is_stopped_is_not_marked_done_and_a_dead_file_is_skipped(tmp_path, app_context):
    app_context.db.add_or_update_document("gone", {"title": "Mất file", "author": "A", "file_path": str(tmp_path / "gone.epub"), "extension": "epub", "created_at": 1.0})
    backfill = ContentBackfill(app_context)
    backfill._stop.set()
    assert backfill.run() == 0 and app_context.config.config.content_backfill_done is False
    backfill._stop.clear()
    assert backfill.run() == 0 and app_context.config.config.content_backfill_done is True  # finished: a missing file is left alone


def test_cap_nhat_ngay_reads_the_text_of_an_ebook_that_has_none(tmp_path, app_context):
    epub = write_epub(tmp_path / "old.epub", ["tukhoamoi", "nhan"], repeat=50)
    app_context.db.add_or_update_document("e1", {"title": "Sách cũ", "author": "A", "file_path": str(epub), "extension": "epub", "created_at": 1.0})
    result = app_context.info_refresh.run()
    assert result.updated == 1 and [d["id"] for d in app_context.db.query_documents(fts_query="tukhoamoi")] == ["e1"]
    assert app_context.info_refresh.run().updated == 0  # nothing new the second time


def test_the_format_lists_of_the_light_module_and_the_sampler_agree():
    from smartdoc.application.content_backfill import SEARCH_TEXT_EXTENSIONS as light
    from smartdoc.infrastructure.text_sampler import SEARCH_TEXT_EXTENSIONS as sampler

    assert light == sampler
