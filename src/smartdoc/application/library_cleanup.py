# SPDX-License-Identifier: AGPL-3.0-or-later
"""Clean-up of books that make no sense in a library: stub files and entries whose file is gone.

Two kinds, two different promises:

- **Tiny files** (a few hundred bytes to a few KB: failed downloads, placeholders, empty shells). Sent to MewBook's own
  trash (`TrashService`), the same place "Tìm file trùng" uses, so nothing is deleted for good and `Khôi phục` puts the
  file back. Nothing happens unless the person selects the books and confirms.
- **Missing files** (the path no longer exists). Only the library *entry* can be removed ("Gỡ khỏi thư viện"); there is no
  file to touch. Finding the file again is the relink dialog's job (`relink_service`), which is offered first.

Both re-check the disk at the moment of the action, not when the list was drawn: a drive that was unplugged and is back,
or a file that grew, must not be removed on the strength of an old list.
"""
from __future__ import annotations

import logging
import os
from dataclasses import dataclass

from smartdoc.core.event_bus import LibraryUpdatedEvent
from smartdoc.domain.library_filter import TINY_FILE_BYTES

logger = logging.getLogger(__name__)


@dataclass
class CleanupResult:
    done: int = 0  # entries trashed / removed
    skipped: int = 0  # left alone because the disk no longer agrees with the list
    failed: int = 0  # could not be moved (locked, no rights)


class LibraryCleanupService:
    def __init__(self, context) -> None:
        self.context = context

    # -- what to show --------------------------------------------------------------------------------------------------
    def tiny(self, limit_bytes: int = TINY_FILE_BYTES) -> list[dict]:
        return self.context.db.tiny_documents(limit_bytes)

    def missing(self) -> list[dict]:
        return self.context.db.missing_documents()

    # -- what to do ----------------------------------------------------------------------------------------------------
    def trash_tiny(self, doc_ids: list[str], limit_bytes: int = TINY_FILE_BYTES) -> CleanupResult:
        """Moves the files to MewBook's trash and drops them from the library; a file that is no longer under
        `limit_bytes` (or no longer there) is skipped, not moved."""
        result = CleanupResult()
        items: list[tuple[str, str | None]] = []
        for doc_id in doc_ids:
            doc = self.context.db.get_document(doc_id)
            path = (doc or {}).get("file_path") or ""
            try:
                size = os.path.getsize(path)
            except OSError:
                result.skipped += 1
                continue
            if size >= limit_bytes:
                result.skipped += 1
                continue
            items.append((doc_id, path))
        if items:
            sent = self.context.trash.send(items)
            result.done = len(sent.moved)
            result.failed = len(sent.failed)
            result.skipped += len(sent.missing)
        return result

    def forget_missing(self, doc_ids: list[str]) -> CleanupResult:
        """Removes library entries whose file is still not there. An entry whose file has reappeared (a drive plugged back
        in) is kept: it is simply present again."""
        result = CleanupResult()
        for doc_id in doc_ids:
            doc = self.context.db.get_document(doc_id)
            if doc is None:
                continue
            if os.path.exists(doc.get("file_path") or ""):
                self.context.db.record_file_status([doc_id], [])
                result.skipped += 1
                continue
            self.context.db.delete_document(doc_id)
            result.done += 1
        if result.done or result.skipped:
            self.context.event_bus.publish(LibraryUpdatedEvent())
        return result
