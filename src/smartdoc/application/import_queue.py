"""TDD-007: Background Job Queue (Importer).

Consumes file paths (either pushed directly via add_file, or automatically
via FileDetectedEvent from the file watcher), runs the right extractor,
normalizes the result, and writes it into the database — all off the UI
thread.

Known limitation: MOBI/AZW3 are not zip/OPF containers like EPUB, so
routing them through EpubExtractor will currently fail gracefully (empty
metadata, filename used as title) rather than actually parsing them. A
dedicated binary extractor for those formats is future work, not something
to fake here.
"""
from __future__ import annotations

import logging
import os
import queue
import threading
import time
from pathlib import Path

from smartdoc.core.event_bus import DocumentIndexedEvent, FileDetectedEvent, ImportProgressEvent, LibraryUpdatedEvent
from smartdoc.domain.models import MetadataNormalizer
from smartdoc.infrastructure.epub_extractor import EpubExtractor
from smartdoc.infrastructure.file_hash import sha256_file
from smartdoc.infrastructure.pdf_extractor import PdfExtractor

logger = logging.getLogger(__name__)

_EPUB_LIKE_EXTENSIONS = {"epub", "azw3", "mobi"}
_SENTINEL = None


class ImportQueueManager:
    def __init__(self, context, num_workers: int = 4) -> None:
        self.context = context
        self.num_workers = num_workers
        self._queue: queue.Queue[str | None] = queue.Queue()
        self._threads: list[threading.Thread] = []
        self._stop_event = threading.Event()

        self._pdf_extractor = PdfExtractor(context)
        self._epub_extractor = EpubExtractor(context)

        self._progress_lock = threading.Lock()
        self._done = 0
        self._total = 0

        context.event_bus.subscribe(FileDetectedEvent, self._on_file_detected)

    def _on_file_detected(self, event: FileDetectedEvent) -> None:
        self.add_file(event.file_path)

    def add_file(self, path: str) -> None:
        with self._progress_lock:
            self._total += 1
        self._queue.put(path)

    def scan_folder(self, folder_path: str) -> int:
        """Walk a folder recursively and enqueue every allowed file. Used
        for the initial bulk import when a watch folder is added, as opposed
        to the live file watcher which only reacts to changes going forward.
        Respects the user's allowed_extensions setting (TDD-015), same as
        the live watcher does.
        """
        allowed = set(self.context.config.config.allowed_extensions)
        enqueued = 0
        for root, _dirs, files in os.walk(folder_path):
            for name in files:
                if name.rsplit(".", 1)[-1].lower() in allowed:
                    self.add_file(str(Path(root) / name))
                    enqueued += 1
        return enqueued

    def start(self) -> None:
        self._stop_event.clear()
        for _ in range(self.num_workers):
            thread = threading.Thread(target=self._worker_loop, daemon=True)
            thread.start()
            self._threads.append(thread)

    def stop(self) -> None:
        self._stop_event.set()
        for _ in self._threads:
            self._queue.put(_SENTINEL)
        for thread in self._threads:
            thread.join(timeout=5)
        self._threads.clear()

    def _worker_loop(self) -> None:
        while not self._stop_event.is_set():
            try:
                path = self._queue.get(timeout=0.5)
            except queue.Empty:
                continue
            if path is _SENTINEL:
                break
            try:
                self._process_file(path)
            except Exception:
                logger.exception("Failed to import file: %s", path)
            finally:
                self._queue.task_done()
                self._report_progress()

    def _report_progress(self) -> None:
        with self._progress_lock:
            self._done += 1
            done, total = self._done, self._total
        self.context.event_bus.publish(ImportProgressEvent(done=done, total=total))

    def _process_file(self, path: str) -> None:
        extension = Path(path).suffix.lower().lstrip(".")
        doc_id = MetadataNormalizer.generate_document_id(path)

        if extension == "pdf":
            # extract_all opens the PDF once and reuses that handle for
            # metadata + cover + text, instead of parsing the file three
            # separate times (see PdfExtractor.extract_all docstring).
            raw_metadata, cover_path, extracted_text = self._pdf_extractor.extract_all(path, doc_id)
        elif extension in _EPUB_LIKE_EXTENSIONS:
            raw_metadata = self._epub_extractor.extract_metadata(path)
            cover_path = self._epub_extractor.extract_cover(path, doc_id)
            extracted_text = ""
        else:
            logger.info("Unsupported extension, skipping: %s", path)
            return

        raw_metadata["file_path"] = path
        raw_metadata["extension"] = extension
        try:
            raw_metadata["file_size"] = Path(path).stat().st_size
        except OSError:
            raw_metadata["file_size"] = 0
        raw_metadata["created_at"] = time.time()
        raw_metadata["content_hash"] = sha256_file(path)

        clean_metadata = MetadataNormalizer.clean_metadata(raw_metadata)
        clean_metadata["cover_path"] = cover_path

        self.context.db.add_or_update_document(doc_id, clean_metadata, extracted_text)
        self.context.event_bus.publish(DocumentIndexedEvent(doc_id=doc_id))
        self.context.event_bus.publish(LibraryUpdatedEvent())


if __name__ == "__main__":
    import tempfile

    from smartdoc.core.app_context import AppContext

    with tempfile.TemporaryDirectory() as app_data, tempfile.TemporaryDirectory() as library_dir:
        context = AppContext.create_in_memory(Path(app_data))

        # Minimal end-to-end smoke test: not a valid PDF, but proves the
        # pipeline never crashes on a bad file and falls back to the
        # filename as title.
        fake_pdf = Path(library_dir) / "Some Weird Book.pdf"
        fake_pdf.write_bytes(b"not a real pdf")

        progress_events: list[tuple[int, int]] = []
        context.event_bus.subscribe(ImportProgressEvent, lambda e: progress_events.append((e.done, e.total)))

        manager = ImportQueueManager(context, num_workers=2)
        manager.start()
        manager.add_file(str(fake_pdf))

        deadline = time.time() + 5
        while not progress_events and time.time() < deadline:
            time.sleep(0.1)
        manager.stop()

        print("progress events:", progress_events)
        results = context.db.search("weird*")
        print("indexed as:", [r["title"] for r in results])
        assert progress_events == [(1, 1)]
        assert results and results[0]["title"] == "Some Weird Book"

        context.shutdown()
