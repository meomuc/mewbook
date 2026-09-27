# SPDX-License-Identifier: AGPL-3.0-or-later
"""Gives the e-books that were imported before their text was read a searchable text, once, in the background.

Before this, only a PDF's first pages were indexed: a word from inside an EPUB / MOBI / AZW3 found nothing. New imports
now read the text; this pass catches up with the books already in the library. Like the fingerprint backfill it runs on
one low-priority thread in small batches and stops on request; a book whose file cannot be read (missing, DRM,
scrambled legacy encoding) is left alone. It runs *once* (`AppConfig.content_backfill_done`); "Cập nhật thông tin sách
ngay" reads any book that still has no text, on demand. Files that live only in the cloud are skipped (reading one would
download it).
"""
from __future__ import annotations

import logging
import threading

from smartdoc.application.background_task import TASK_READ_TEXT, TaskReporter
from smartdoc.infrastructure.cloud_files import is_cloud_only
from smartdoc.infrastructure.pdf_extractor import DEFAULT_MAX_PAGES

logger = logging.getLogger(__name__)

# Kept in step with text_sampler.SEARCH_TEXT_EXTENSIONS (a test checks): text_sampler is imported only where it is used, never at
# start-up -- the GUI process stays light (see test_importing_the_app_does_not_load_the_machine_learning_stack).
SEARCH_TEXT_EXTENSIONS = frozenset({"epub", "mobi", "azw3", "azw", "prc"})

BATCH_SIZE = 25


class ContentBackfill:
    def __init__(self, context, batch_size: int = BATCH_SIZE) -> None:
        self.context = context
        self._batch_size = batch_size
        self._stop = threading.Event()
        self._thread: threading.Thread | None = None

    def start(self) -> None:
        if self.context.config.config.content_backfill_done or (self._thread is not None and self._thread.is_alive()):
            return
        self._stop.clear()
        self._thread = threading.Thread(target=self.run, name="content-backfill", daemon=True)
        self._thread.start()

    def stop(self, timeout: float = 5.0) -> None:
        self._stop.set()
        if self._thread is not None and self._thread.is_alive():
            self._thread.join(timeout)

    def wait(self, timeout: float | None = None) -> bool:
        if self._thread is not None:
            self._thread.join(timeout)
            return not self._thread.is_alive()
        return True

    def run(self) -> int:
        """One pass over the e-books without text; returns how many got some. Marks the pass done only if it finished."""
        from smartdoc.infrastructure.text_sampler import extract_search_text

        config = self.context.config
        pages = config.config.content_search_pages or DEFAULT_MAX_PAGES
        formats = tuple(sorted(SEARCH_TEXT_EXTENSIONS))
        reporter = TaskReporter(getattr(self.context, "event_bus", None), TASK_READ_TEXT,
                                self.context.db.count_documents_without_text(formats))
        try:
            return self._pass(config, pages, formats, extract_search_text, reporter)
        finally:
            reporter.finish()

    def _pass(self, config, pages, formats, extract_search_text, reporter) -> int:
        filled = 0
        cursor = 0
        while not self._stop.is_set():
            batch = self.context.db.documents_without_text(formats, after_rowid=cursor, limit=self._batch_size)
            if not batch:
                config.config.content_backfill_done = True
                config.save()
                break
            for row in batch:
                if self._stop.is_set():
                    return filled
                cursor = row["doc_rowid"]
                reporter.step()
                if is_cloud_only(row["file_path"]):
                    continue
                text = extract_search_text(row["file_path"], row["extension"], pages)
                if text:
                    self.context.db.set_document_content(row["id"], text)
                    filled += 1
        if filled:
            logger.info("Content backfill done: %d e-book(s) now searchable by their text", filled)
        return filled
