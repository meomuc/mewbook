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
import multiprocessing
import time
import uuid
from concurrent.futures import ProcessPoolExecutor
from dataclasses import dataclass, field
from pathlib import Path

from smartdoc.core.event_bus import (
    DocumentIndexedEvent,
    FileDetectedEvent,
    ImportBatchCompletedEvent,
    ImportProgressEvent,
    LibraryUpdatedEvent,
)
from smartdoc.domain.models import MetadataNormalizer
from smartdoc.infrastructure.epub_extractor import EpubExtractor
from smartdoc.infrastructure.file_hash import sha256_file
from smartdoc.infrastructure.fingerprint import fingerprint_file
from smartdoc.infrastructure.page_count import count_pages
from smartdoc.infrastructure.pdf_extractor import DEFAULT_MAX_PAGES, PdfExtractor

logger = logging.getLogger(__name__)

_EPUB_LIKE_EXTENSIONS = {"epub", "azw3", "mobi"}
# Files the folder watcher finds are grouped into one batch until this long passes without a new one, so a
# copy of 300 books yields one summary ("412 thêm mới") instead of 300 (or none).
WATCH_BATCH_QUIET_SECONDS = 5.0
_SENTINEL = None


@dataclass
class _BatchProgress:
    total: int
    done: int = 0
    success: int = 0
    duplicate: int = 0
    failed: int = 0
    doc_ids: list[str] = field(default_factory=list)  # the ones that were newly added
    failed_paths: list[str] = field(default_factory=list)  # the files that could not be imported, for the list
    # A batch the watcher is still adding files to: it completes only after it is closed (see _close_watch_batch).
    is_open: bool = False


class ImportQueueManager:
    def __init__(self, context, num_workers: int = 4, use_process_pool: bool = False) -> None:
        self.context = context
        self.num_workers = num_workers
        # Reading PDFs in separate processes (infrastructure/pdf_worker.py): PyMuPDF is not thread-safe, so the import
        # threads otherwise take turns on the heavy part. The app turns it on; a test or a tool leaves it off.
        self._use_process_pool = use_process_pool
        self._pdf_pool: ProcessPoolExecutor | None = None
        self._queue: queue.Queue[tuple[str, str | None] | None] = queue.Queue()
        self._threads: list[threading.Thread] = []
        self._stop_event = threading.Event()

        self._pdf_extractor = PdfExtractor(context)
        self._epub_extractor = EpubExtractor(context)

        self._progress_lock = threading.Lock()
        self._done = 0
        self._total = 0

        # Tracks user-initiated batches (folder scan, multi-file add, a
        # drag-and-drop drop) so a single ImportBatchCompletedEvent can be
        # published once every file in *that* batch has been processed --
        # files queued individually (add_file with no batch_id, e.g. the
        # live file watcher) are never batch-tracked or summarized.
        self._batches: dict[str, _BatchProgress] = {}
        self._batches_lock = threading.Lock()
        self._watch_batch_id: str | None = None
        self._watch_timer: threading.Timer | None = None

        context.event_bus.subscribe(FileDetectedEvent, self._on_file_detected)

    def _on_file_detected(self, event: FileDetectedEvent) -> None:
        self._add_to_watch_batch(event.file_path)

    def _add_to_watch_batch(self, path: str) -> None:
        """Files found by the folder watcher share one open batch; it closes (and reports once) after
        WATCH_BATCH_QUIET_SECONDS without a new file."""
        with self._batches_lock:
            batch_id = self._watch_batch_id
            if batch_id is None or batch_id not in self._batches:
                batch_id = uuid.uuid4().hex
                self._batches[batch_id] = _BatchProgress(total=0, is_open=True)
                self._watch_batch_id = batch_id
            self._batches[batch_id].total += 1  # counted before it is queued, so it cannot complete early
            if self._watch_timer is not None:
                self._watch_timer.cancel()
            timer = threading.Timer(WATCH_BATCH_QUIET_SECONDS, self._close_watch_batch, args=(batch_id,))
            timer.daemon = True
            self._watch_timer = timer
            timer.start()
        self.add_file(path, batch_id)

    def _close_watch_batch(self, batch_id: str) -> None:
        finished: _BatchProgress | None = None
        with self._batches_lock:
            batch = self._batches.get(batch_id)
            if self._watch_batch_id == batch_id:
                self._watch_batch_id = None
            if batch is None:
                return
            batch.is_open = False
            if batch.done >= batch.total:
                finished = self._batches.pop(batch_id)
        if finished is not None:
            self._publish_batch(batch_id, finished)

    def cancel_pending(self) -> int:
        """"Dừng": drops every file still waiting in the queue (the ones being processed right now finish). Books
        already added stay; batches that become complete report what was done. Returns how many were dropped."""
        dropped: list[tuple[str, str | None]] = []
        while True:
            try:
                item = self._queue.get_nowait()
            except queue.Empty:
                break
            if item is _SENTINEL:
                self._queue.put(item)  # a stop request is not ours to swallow
                break
            dropped.append(item)
            self._queue.task_done()
        with self._progress_lock:
            self._total = max(self._done, self._total - len(dropped))
            done, total = self._done, self._total
        finished: list[tuple[str, _BatchProgress]] = []
        with self._batches_lock:
            for _path, batch_id in dropped:
                batch = self._batches.get(batch_id) if batch_id else None
                if batch is not None:
                    batch.total -= 1
            for batch_id, batch in list(self._batches.items()):
                if not batch.is_open and batch.done >= batch.total:
                    finished.append((batch_id, self._batches.pop(batch_id)))
        for batch_id, batch in finished:
            self._publish_batch(batch_id, batch)
        self.context.event_bus.publish(ImportProgressEvent(done=done, total=total))
        return len(dropped)

    def add_file(self, path: str, batch_id: str | None = None) -> None:
        with self._progress_lock:
            self._total += 1
        self._queue.put((path, batch_id))

    def add_files(self, paths: list[str]) -> int:
        """Enqueue multiple files as one batch (manual file/folder upload,
        drag-and-drop). Once every file in the batch has been processed, an
        ImportBatchCompletedEvent reports how many succeeded, were already
        in the library (duplicate), or failed. Returns the number enqueued.

        Adding files by hand is an explicit wish: a file the person once removed from the library (and which the watcher
        therefore skips) is imported again.
        """
        if not paths:
            return 0
        self.context.db.unexclude_paths(paths)
        self._start_batch(paths)
        return len(paths)

    def add_files_tracked(self, paths: list[str]) -> str | None:
        """Like add_files, but returns the batch_id instead of a plain
        count -- for a caller that needs to correlate its own batch's
        DocumentIndexedEvent/ImportBatchCompletedEvent against a global
        event bus that may also be carrying an unrelated import's events at
        the same time (e.g. AddDocumentDialog, open while a watched folder
        also happens to be importing). Returns None if there was nothing to
        enqueue."""
        if not paths:
            return None
        self.context.db.unexclude_paths(paths)
        return self._start_batch(paths)

    def _start_batch(self, paths: list[str]) -> str:
        batch_id = uuid.uuid4().hex
        with self._batches_lock:
            self._batches[batch_id] = _BatchProgress(total=len(paths))
        for path in paths:
            self.add_file(path, batch_id)
        return batch_id

    def scan_folder(self, folder_path: str) -> int:
        """Walk a folder recursively and enqueue every allowed file. Used
        for the initial bulk import when a watch folder is added, as opposed
        to the live file watcher which only reacts to changes going forward.
        Respects the user's allowed_extensions setting (TDD-015), same as
        the live watcher does.
        """
        allowed = set(self.context.config.config.allowed_extensions)
        paths = []
        for root, _dirs, files in os.walk(folder_path):
            for name in files:
                if name.rsplit(".", 1)[-1].lower() in allowed:
                    paths.append(str(Path(root) / name))
        return self.add_files(paths)

    def catch_up_scan(self, folders: list[str] | None = None) -> int:
        """Files that arrived in the watched folders while MewBook was closed (the live watcher only sees changes made
        while it runs). Every file of an allowed type that the library does not know is queued like a watched file, except

        - files the person removed from the library on purpose (excluded_paths), and
        - a file that is a book whose file went missing under the same name and size (moved while closed): that book is
          pointed at it instead (same id, so hashtags, collections and reading progress stay).

        Meant for a background thread; returns how many files it queued. Reads only directory listings."""
        db = self.context.db
        allowed = {f".{e}" for e in self.context.config.config.allowed_extensions}
        known = {os.path.normcase(os.path.abspath(path)) for _id, path in db.files_to_check()}
        excluded = db.excluded_path_keys()
        missing = db.missing_documents_by_name()
        queued = relinked = 0
        for folder in folders if folders is not None else list(self.context.config.config.watch_folders):
            if not os.path.isdir(folder):
                continue
            for root, _dirs, names in os.walk(folder):
                for name in names:
                    if os.path.splitext(name)[1].lower() not in allowed:
                        continue
                    path = os.path.join(root, name)
                    key = os.path.normcase(os.path.abspath(path))
                    if key in known or key in excluded or self.context.self_writes.is_recent(path):
                        continue
                    try:
                        size = os.stat(path).st_size
                    except OSError:
                        continue
                    owner = missing.pop((name.lower(), size), None)
                    if owner is not None and db.relocate_document(owner, path, size):
                        relinked += 1
                        known.add(key)
                        continue
                    self._add_to_watch_batch(path)
                    known.add(key)
                    queued += 1
        if relinked:
            self.context.event_bus.publish(LibraryUpdatedEvent())
        logger.info("Start-up scan: %d new file(s) queued, %d moved book(s) found again", queued, relinked)
        return queued

    def pending_count(self) -> int:
        """Files queued or being processed right now (0 when idle)."""
        with self._progress_lock:
            return max(0, self._total - self._done)

    def active_worker_count(self) -> int:
        """Number of worker threads currently running -- shown in Settings
        alongside the configured/allowed count."""
        return len(self._threads)

    def restart(self, num_workers: int) -> None:
        """Live-apply a new worker count -- Settings no longer needs an app
        restart for this. Any in-flight/queued files survive: stop() drains
        each worker's current item before joining, and the queue itself
        isn't touched."""
        self.stop()
        self.num_workers = num_workers
        self.start()

    def start(self) -> None:
        self._stop_event.clear()
        if self._use_process_pool and self._pdf_pool is None:
            # spawn, like the classifier's pool (fork does not exist on Windows); processes start on the first PDF.
            self._pdf_pool = ProcessPoolExecutor(max_workers=max(1, min(self.num_workers, 8)), mp_context=multiprocessing.get_context("spawn"))
            self._pdf_extractor.pool = self._pdf_pool
        for _ in range(self.num_workers):
            thread = threading.Thread(target=self._worker_loop, daemon=True)
            thread.start()
            self._threads.append(thread)

    def stop(self) -> None:
        if self._watch_timer is not None:
            self._watch_timer.cancel()
        self._stop_event.set()
        for _ in self._threads:
            self._queue.put(_SENTINEL)
        for thread in self._threads:
            thread.join(timeout=5)
        self._threads.clear()
        if self._pdf_pool is not None:
            self._pdf_extractor.pool = None
            self._pdf_pool.shutdown(wait=False, cancel_futures=True)
            self._pdf_pool = None

    def _worker_loop(self) -> None:
        while not self._stop_event.is_set():
            try:
                item = self._queue.get(timeout=0.5)
            except queue.Empty:
                continue
            if item is _SENTINEL:
                break
            path, batch_id = item
            outcome = "failed"
            try:
                outcome = self._process_file(path, batch_id)
            except Exception:
                logger.exception("Failed to import file: %s", path)
                outcome = "failed"
            finally:
                self._queue.task_done()
                self._report_progress()
                if batch_id is not None:
                    self._report_batch_outcome(batch_id, outcome, MetadataNormalizer.generate_document_id(path), path)

    def _report_progress(self) -> None:
        with self._progress_lock:
            self._done += 1
            done, total = self._done, self._total
        self.context.event_bus.publish(ImportProgressEvent(done=done, total=total))

    def _report_batch_outcome(self, batch_id: str, outcome: str, doc_id: str, path: str = "") -> None:
        finished: _BatchProgress | None = None
        with self._batches_lock:
            batch = self._batches.get(batch_id)
            if batch is None:
                return
            batch.done += 1
            if outcome == "duplicate":
                batch.duplicate += 1
            elif outcome == "failed":
                batch.failed += 1
                batch.failed_paths.append(path)
            else:
                batch.success += 1
                batch.doc_ids.append(doc_id)
            if batch.done >= batch.total and not batch.is_open:
                finished = batch
                del self._batches[batch_id]
        if finished is not None:
            self._publish_batch(batch_id, finished)

    def _publish_batch(self, batch_id: str, batch: _BatchProgress) -> None:
        self.context.event_bus.publish(
            ImportBatchCompletedEvent(
                success=batch.success,
                duplicate=batch.duplicate,
                failed=batch.failed,
                batch_id=batch_id,
                doc_ids=tuple(batch.doc_ids),
                failed_paths=tuple(batch.failed_paths),
            )
        )

    def _content_hash_if_needed(self, path: str, size: int) -> str | None:
        """Only files of equal size can be the same file, so a file whose size nobody else has is not read through to hash
        it (that was the whole file, for every import). If another book has the size, both get their hash now; the others
        are hashed later, when duplicates are looked for (DuplicateEngine) or by "Cập nhật ngay"."""
        others = [d for d in self.context.db.documents_with_size(size) if os.path.normcase(d["file_path"]) != os.path.normcase(path)]
        if not others:
            return None
        for other in others:
            if not other["content_hash"] and os.path.isfile(other["file_path"]):
                digest = sha256_file(other["file_path"])
                if digest:
                    self.context.db.set_file_stats(other["id"], digest, size)
        return sha256_file(path)

    def _process_file(self, path: str, batch_id: str | None = None) -> str:
        """Returns "success", "duplicate", or "failed" for batch reporting."""
        extension = Path(path).suffix.lower().lstrip(".")
        doc_id = MetadataNormalizer.generate_document_id(path)

        if self.context.db.is_path_excluded(path):
            # Removed from the library on purpose (the file stayed): not brought back by a change to the file or a scan.
            logger.info("Removed from the library on purpose, skipping: %s", path)
            return "duplicate"

        if self.context.db.get_document(doc_id) is not None:
            # Same file path already indexed (doc_id is derived from the
            # path) -- re-scanning a watched folder must not silently
            # re-extract and re-write it every time, and the user wants this
            # counted separately from a genuinely new import.
            logger.info("Already in library, skipping: %s", path)
            return "duplicate"

        if self.context.db.find_id_by_path(path) is not None:
            # A book that was relinked to this path keeps its old id (an md5 of its old path), so the id check
            # above cannot see it; importing it again would duplicate it (S1-04).
            logger.info("Path already filed under another id, skipping: %s", path)
            return "duplicate"

        if extension == "pdf":
            # extract_all opens the PDF once and reuses that handle for
            # metadata + cover + text, instead of parsing the file three
            # separate times (see PdfExtractor.extract_all docstring).
            pages = self.context.config.config.content_search_pages or DEFAULT_MAX_PAGES  # Settings > Hiệu năng
            raw_metadata, cover_path, extracted_text = self._pdf_extractor.extract_all(path, doc_id, max_pages=pages)
        elif extension in _EPUB_LIKE_EXTENSIONS:
            raw_metadata = self._epub_extractor.extract_metadata(path)
            cover_path = self._epub_extractor.extract_cover(path, doc_id)
            extracted_text = ""
        else:
            logger.info("Unsupported extension, skipping: %s", path)
            return "failed"

        raw_metadata["file_path"] = path
        raw_metadata["extension"] = extension
        try:
            raw_metadata["file_size"] = Path(path).stat().st_size
        except OSError:
            raw_metadata["file_size"] = 0
        raw_metadata["created_at"] = time.time()
        raw_metadata["content_hash"] = self._content_hash_if_needed(path, raw_metadata["file_size"])
        raw_metadata["fingerprint"] = fingerprint_file(path, extension)
        if raw_metadata.get("page_count") is None:  # a PDF already reported its own while it was open
            raw_metadata["page_count"] = count_pages(path, extension)

        clean_metadata = MetadataNormalizer.clean_metadata(raw_metadata)
        clean_metadata["cover_path"] = cover_path

        self.context.db.add_or_update_document(doc_id, clean_metadata, extracted_text)
        self.context.event_bus.publish(DocumentIndexedEvent(doc_id=doc_id, batch_id=batch_id))
        self.context.event_bus.publish(LibraryUpdatedEvent())
        return "success"


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
