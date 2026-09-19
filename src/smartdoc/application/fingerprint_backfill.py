"""Fills in the fingerprint (infrastructure/fingerprint.py) of books imported
before it existed.

Runs on one low-priority background thread that works through the library in
small batches and stops on request, so it never delays startup or shutdown.
A book whose file can't be read gets an empty-string fingerprint, which is
"looked at, nothing to find" -- otherwise it would be retried on every launch.

Files that live only in the cloud (OneDrive "Files On-Demand" placeholders) are
skipped and left for a later launch: reading one would make Windows download the
whole file, and a backfill over a big library must not do that behind the user's back.
"""
from __future__ import annotations

import logging
import threading

from smartdoc.infrastructure.cloud_files import is_cloud_only as _is_cloud_only
from smartdoc.infrastructure.fingerprint import fingerprint_file

logger = logging.getLogger(__name__)

BATCH_SIZE = 25


class FingerprintBackfill:
    def __init__(self, context, batch_size: int = BATCH_SIZE) -> None:
        self.context = context
        self._batch_size = batch_size
        self._stop = threading.Event()
        self._thread: threading.Thread | None = None

    def start(self) -> None:
        if self._thread is not None and self._thread.is_alive():
            return
        self._stop.clear()
        self._thread = threading.Thread(target=self.run, name="fingerprint-backfill", daemon=True)
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
        """Processes every book that lacks a fingerprint; returns how many it handled."""
        handled = 0
        cursor = 0
        while not self._stop.is_set():
            batch = self.context.db.documents_missing_fingerprint(self._batch_size, after_rowid=cursor)
            if not batch:
                break
            for row in batch:
                if self._stop.is_set():
                    return handled
                cursor = row["doc_rowid"]
                if _is_cloud_only(row["file_path"]):
                    continue  # not downloaded: leave it for a later launch
                try:
                    fingerprint = fingerprint_file(row["file_path"], row["extension"]) or ""
                    self.context.db.set_fingerprint(row["id"], fingerprint)
                except Exception:  # noqa: BLE001 -- one bad file/db hiccup must not stop the rest
                    logger.exception("Fingerprint backfill failed for %s", row.get("file_path"))
                    self.context.db.set_fingerprint(row["id"], "")
                handled += 1
        if handled:
            logger.info("Fingerprint backfill done: %d book(s)", handled)
        return handled
