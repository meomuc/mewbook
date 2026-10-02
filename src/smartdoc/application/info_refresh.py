# SPDX-License-Identifier: AGPL-3.0-or-later
"""Cập nhật ngay: one pass over the library that brings what MewBook knows about each *file* up to date -- the "scan now"
counterpart of the background work (missing-file check, fingerprint backfill) that runs by itself.

For every book it reads the file (never writes it) and refreshes only *facts about the file*, never what the person
typed (title, author, hashtags and so on are untouched):
- whether the file is there (`file_status`);
- its size, and -- when the size changed or it was never computed -- the content hash (what "Giống hệt" duplicates are
  matched by), the fingerprint (what metadata lookup matches by) and the page count.
A book counts as *updated* when at least one of those values is new or different. Cloud-only placeholders
(OneDrive "Files On-Demand") are skipped rather than downloaded.

It is meant to run on a background thread: it reports `progress(done, total)`, checks `should_cancel` between books, and
holds no lock while it reads a file.
"""
from __future__ import annotations

import logging
import os
from collections.abc import Callable
from dataclasses import dataclass, field

from smartdoc.application.content_backfill import SEARCH_TEXT_EXTENSIONS
from smartdoc.core.event_bus import LibraryFilesMissingEvent, LibraryUpdatedEvent
from smartdoc.infrastructure.cloud_files import is_cloud_only
from smartdoc.infrastructure.file_hash import sha256_file
from smartdoc.infrastructure.fingerprint import fingerprint_file
from smartdoc.infrastructure.page_count import SUPPORTED_EXTENSIONS, count_pages
from smartdoc.infrastructure.pdf_extractor import DEFAULT_MAX_PAGES

logger = logging.getLogger(__name__)

Progress = Callable[[int, int], None]  # (done, total)


@dataclass
class RefreshResult:
    checked: int = 0
    updated: int = 0
    missing: int = 0
    skipped_cloud: int = 0
    cancelled: bool = False
    changed_ids: list[str] = field(default_factory=list)


class InfoRefresh:
    def __init__(self, context) -> None:
        self.context = context

    def run(self, progress: Progress | None = None, should_cancel: Callable[[], bool] | None = None) -> RefreshResult:
        db = self.context.db
        rows = db.documents_for_refresh()
        result = RefreshResult()
        present: list[str] = []
        missing: list[str] = []
        total = len(rows)
        for done, row in enumerate(rows):
            if should_cancel is not None and should_cancel():
                result.cancelled = True
                break
            if progress is not None and done % 10 == 0:
                progress(done, total)
            path = row["file_path"] or ""
            if not os.path.isfile(path):
                missing.append(row["id"])
                result.checked += 1
                continue
            present.append(row["id"])
            result.checked += 1
            if is_cloud_only(path):
                result.skipped_cloud += 1
                continue
            try:
                if self.refresh_one(row):
                    result.updated += 1
                    result.changed_ids.append(row["id"])
            except Exception:  # noqa: BLE001 -- one unreadable file must not stop the pass over the rest
                logger.exception("Refreshing %s failed", path)
        result.missing = len(missing)
        if not result.cancelled:
            if progress is not None:
                progress(total, total)
        db.record_file_status(present, missing)
        bus = self.context.event_bus
        bus.publish(LibraryFilesMissingEvent(count=db.count_missing()))
        if result.updated:
            bus.publish(LibraryUpdatedEvent())
        logger.info("Info refresh: %d checked, %d updated, %d missing", result.checked, result.updated, result.missing)
        return result

    def refresh_one(self, row: dict) -> bool:
        """Bring one book's file facts up to date; True when something new or different was stored. Public (not
        `_refresh_one`): the merged "Cập nhật thông tin sách" (application/metadata_batch_update.py) calls this
        directly per document, on its own bulk-fetched row shape, instead of going through `run()`'s own
        whole-library query -- see that module's docstring for why."""
        path, extension = row["file_path"], (row["extension"] or "")
        db = self.context.db
        size = os.stat(path).st_size
        old_size = int(row["file_size"] or 0)
        size_changed = old_size not in (0, size)  # 0 = never recorded: not a change, just news
        content_hash = row["content_hash"]
        if size_changed or not content_hash:
            content_hash = sha256_file(path) or content_hash
        if content_hash != row["content_hash"] or old_size != size:
            db.set_file_stats(row["id"], content_hash, size)
        changed = content_hash != row["content_hash"] or old_size != size
        if size_changed or not row["fingerprint"]:
            fingerprint = fingerprint_file(path, extension) or ""
            if fingerprint != (row["fingerprint"] or "") or row["fingerprint"] is None:
                db.set_fingerprint(row["id"], fingerprint)  # "" = looked at, nothing to find
            changed = changed or (bool(fingerprint) and fingerprint != (row["fingerprint"] or ""))
        ext = extension.lower().lstrip(".")
        if ext in SEARCH_TEXT_EXTENSIONS and (size_changed or not row["has_text"]):
            # An e-book imported before its text was read for search (or whose file changed): read it now.
            from smartdoc.infrastructure.text_sampler import extract_search_text  # lazily: see content_backfill

            pages = self.context.config.config.content_search_pages or DEFAULT_MAX_PAGES
            text = extract_search_text(path, extension, pages)
            if text:
                db.set_document_content(row["id"], text)
                changed = True
        if ext in SUPPORTED_EXTENSIONS and (size_changed or not row["page_count"]):
            pages = count_pages(path, extension)
            if pages and pages != row["page_count"]:
                db.set_page_count(row["id"], pages)
                changed = True
        return changed
