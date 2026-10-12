# SPDX-License-Identifier: AGPL-3.0-or-later
"""The one place that decides what happens to a book's file and library row when the user removes it.

Every removal the user asks for (delete in the library, the duplicate finder's two buttons, the tiny-file cleanup) goes
through `RemovalService.remove`, so changing what "remove" means is a change in one function, not in four dialogs. Not
covered on purpose: forgetting books whose file is already gone (`LibraryCleanupService.forget_missing`) and the trash's
own expiry and "Xóa hẳn", which delete rows for good by design.

Two modes exist (docs/adr/0002): both keep the row, hide it from every library list, and can be undone from Thùng rác.

- `REMOVE_FROM_LIBRARY`: Xóa khỏi thư viện. The row is listed in Thùng rác as the kind "library", the file is never
  touched, and its path is remembered so the folder watcher does not import it again.
- `TRASH_FILE`: Xóa file và thư viện. The file moves into MewBook's trash folder and the row is kept as the kind "file"
  (`TrashService.send`).
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
    REMOVE_FROM_LIBRARY = "remove_from_library"
    TRASH_FILE = "trash_file"


class RemovalService:
    def __init__(self, context: AppContext) -> None:
        self.context = context

    def remove(self, items: list[RemovalItem], mode: RemovalMode,
               progress: ProgressCallback | None = None) -> SendResult:
        """Removes the books from the library according to `mode`; `moved` lists the ids that left the library."""
        if mode is RemovalMode.TRASH_FILE:
            return self.context.trash.send(items, progress)
        return self._remove_from_library(items)

    def _remove_from_library(self, items: list[RemovalItem]) -> SendResult:
        result = SendResult([], [], [])
        for doc_id, file_path in items:
            doc = self.context.db.get_document(doc_id)
            if doc is None:
                continue
            self.context.db.mark_document_removed(doc_id)
            path = file_path or doc.get("file_path") or ""
            if path and Path(path).is_file():
                # The file stays where it is, so the folder watcher would find it again: remember it was dropped on purpose.
                self.context.db.exclude_paths([path])
            result.moved.append(doc_id)
        if result.moved:
            self.context.event_bus.publish(LibraryUpdatedEvent())
        return result
