# SPDX-License-Identifier: AGPL-3.0-or-later
"""The one place that decides what happens to a book's file and library row when the user removes it.

Every removal the user asks for (delete in the library, the duplicate finder's two buttons, the tiny-file cleanup) goes
through `RemovalService.remove`, so changing what "remove" means is a change in one function, not in four dialogs. Not
covered on purpose: forgetting books whose file is already gone (`LibraryCleanupService.forget_missing`) and the trash's
own expiry and "Xóa hẳn", which delete rows for good by design.

Two modes exist, both mirroring behaviour the app had before this seam was cut:

- `TRASH_FILE`: the file moves into MewBook's trash and the row is kept, marked as trashed (`TrashService.send`).
- `FORGET_RECORD`: a legacy mode from the duplicate finder's old "gỡ khỏi thư viện": the row is deleted for good, the
  file stays where it is, and its path is remembered so the folder watcher does not bring it back. docs/adr/0002
  replaces it with a recoverable removal; it stays here only until that lands.
"""
from __future__ import annotations

from collections.abc import Callable
from enum import Enum
from pathlib import Path
from typing import TYPE_CHECKING

from smartdoc.application.trash_service import SendResult
from smartdoc.core.event_bus import LibraryUpdatedEvent

if TYPE_CHECKING:
    from smartdoc.core.app_context import AppContext

RemovalItem = tuple[str, str | None]  # (document id, file path as the caller knows it)
ProgressCallback = Callable[[int, int], None]


class RemovalMode(Enum):
    TRASH_FILE = "trash_file"
    FORGET_RECORD = "forget_record"


class RemovalService:
    def __init__(self, context: AppContext) -> None:
        self.context = context

    def remove(self, items: list[RemovalItem], mode: RemovalMode,
               progress: ProgressCallback | None = None) -> SendResult:
        """Removes the books from the library according to `mode`. In both modes `moved` lists the ids that left
        the library (for TRASH_FILE they are in the trash, for FORGET_RECORD they are gone)."""
        if mode is RemovalMode.TRASH_FILE:
            return self.context.trash.send(items, progress)
        return self._forget_records(items)

    def _forget_records(self, items: list[RemovalItem]) -> SendResult:
        result = SendResult([], [], [])
        for doc_id, file_path in items:
            self.context.db.delete_document(doc_id)
            if file_path and Path(file_path).is_file():
                # The file stays where it is, so the folder watcher would find it again: remember it was dropped on purpose.
                self.context.db.exclude_paths([file_path])
            result.moved.append(doc_id)
        if items:
            self.context.event_bus.publish(LibraryUpdatedEvent())
        return result
