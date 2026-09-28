# SPDX-License-Identifier: AGPL-3.0-or-later
"""Đặt lại thư viện: put the local library database back to a blank slate.

Always two steps, in this order, exactly like a schema upgrade (no backup, no reset):

1. The current library is backed up (`backup_service.REASON_PRE_RESET`) -- a failing backup stops the reset, so
   there is never a reset without a way back.
2. `DatabaseManager.reset_library_data()` empties every table that holds library data: books, hashtags (a column
   of `documents`, so nothing separate to clear), collections, sidebar groups, classification and metadata-write
   history, reading progress, the duplicate-exclusion list.

`keep_config=True` (the default) is the only other thing this touches: when False, `ConfigManager.reset_to_defaults()`
also puts every setting back to first-run, except where the library's own files live.

What this never does: delete or rename a book file, write to a book's metadata, or contact the community server --
only `documents`-derived state inside library.db moves. The book files a watched folder still holds are found again
(as if freshly imported: no hashtags, no reading history) the next time MewBook scans that folder, which happens
on its own the next time the app starts.
"""
from __future__ import annotations

import logging

from smartdoc.application.backup_service import BackupError, REASON_PRE_RESET
from smartdoc.core.event_bus import LibraryUpdatedEvent

logger = logging.getLogger(__name__)


class LibraryResetError(Exception):
    """The reset could not even start (the safety backup failed); nothing was touched."""


class LibraryResetService:
    def __init__(self, context) -> None:
        self.context = context

    def reset(self, *, keep_config: bool = True) -> None:
        if self.context.db.db_path != ":memory:":  # an in-memory library (tests, demos) has no file to back up
            try:
                self.context.backups.create_backup(REASON_PRE_RESET, prune=False)
            except BackupError as exc:
                raise LibraryResetError(f"Chưa đặt lại: không sao lưu được thư viện hiện tại trước khi đặt lại. {exc}") from exc
        self.context.db.reset_library_data()
        if not keep_config:
            self.context.config.reset_to_defaults()
        self.context.filters.clear()  # nothing left for a stale collection/tag/author selection to point at
        self.context.event_bus.publish(LibraryUpdatedEvent())
        logger.info("Library data reset (keep_config=%s)", keep_config)


if __name__ == "__main__":
    import tempfile
    from pathlib import Path

    from smartdoc.core.app_context import AppContext

    with tempfile.TemporaryDirectory() as tmp:
        context = AppContext.create_in_memory(Path(tmp))
        context.db.add_or_update_document("d1", {"title": "A", "author": "X", "file_path": "a.pdf", "created_at": 0.0})
        print("before:", context.db.count_documents())
        context.library_reset.reset()
        print("after:", context.db.count_documents())
