# SPDX-License-Identifier: AGPL-3.0-or-later
"""Finding books whose file has gone, and pointing them at where the file went (S1-04, FR-OPS-04).

Two steps, both safe by construction:

1. `check_files` looks at every book's path and records `file_status` ('present' / 'missing'); it announces the
   count with `LibraryFilesMissingEvent`.
2. `propose` searches a folder the user chose for the missing books and returns *proposals* (nothing is written);
   the user reviews them, and `apply` then changes the stored path of the ones they kept.

A proposal is matched, from most to least certain, by
  - **content hash** (the same bytes, whatever the file is now called);
  - **name + size**, when exactly one file in the new folder has the old name and size;
  - **fingerprint** (application/metadata_writer keeps it stable when MewBook itself rewrote the file's metadata)
    among files that carry the old name.

The library only ever changes `documents.file_path` (and its status/size). The book files are read to hash them
and are never moved, renamed or written. The document id (an md5 of the *old* path) is kept: collections, tags
and reviews point at it. The import queue recognises a path that is already filed, so a relinked book is not
imported a second time.
"""
from __future__ import annotations

import logging
import os
import threading
from collections.abc import Callable
from dataclasses import dataclass, field
from pathlib import Path

from smartdoc.core.config import KNOWN_EXTENSIONS
from smartdoc.application.background_task import TASK_FILE_CHECK, TaskReporter
from smartdoc.core.event_bus import EventBus, LibraryFilesMissingEvent, LibraryUpdatedEvent
from smartdoc.infrastructure.database import DatabaseManager
from smartdoc.infrastructure.file_hash import sha256_file
from smartdoc.infrastructure.fingerprint import fingerprint_file

logger = logging.getLogger(__name__)

METHOD_HASH = "hash"
METHOD_NAME_SIZE = "name+size"
METHOD_FINGERPRINT = "fingerprint"

Progress = Callable[[str, int, int], None]
"""progress(stage, done, total): stage is "scan" (files found so far, total 0), or "match" (books processed)."""


@dataclass
class RelinkProposal:
    doc_id: str
    title: str
    old_path: str
    new_path: str
    method: str
    selected: bool = True
    note: str = ""
    """Why it is not selected by default, if it isn't."""


@dataclass
class RelinkResult:
    updated: int = 0
    skipped: list[tuple[str, str]] = field(default_factory=list)
    """(doc_id, reason) for the ones that could not be applied."""


def _same_name(old_path: str, candidate: str) -> bool:
    return os.path.basename(old_path).casefold() == os.path.basename(candidate).casefold()


class RelinkService:
    def __init__(self, db: DatabaseManager, event_bus: EventBus | None = None) -> None:
        self._db = db
        self._bus = event_bus

    # -- 1. detect --------------------------------------------------------------------------------------------

    def check_files(self, progress: Progress | None = None) -> int:
        """Record which books' files exist; returns how many are missing."""
        rows = self._db.files_to_check()
        present: list[str] = []
        missing: list[str] = []
        reporter = TaskReporter(self._bus, TASK_FILE_CHECK, len(rows))
        for done, (doc_id, path) in enumerate(rows, start=1):
            (present if path and os.path.isfile(path) else missing).append(doc_id)
            reporter.step()
            if progress and done % 200 == 0:
                progress("check", done, len(rows))
        reporter.finish()
        self._db.record_file_status(present, missing)
        if self._bus is not None:
            self._bus.publish(LibraryFilesMissingEvent(count=len(missing)))
        return len(missing)

    # -- 2. propose -------------------------------------------------------------------------------------------

    @staticmethod
    def _scan(root: Path, cancel: threading.Event | None, progress: Progress | None) -> list[tuple[str, int]]:
        wanted = {f".{ext}" for ext in KNOWN_EXTENSIONS}
        found: list[tuple[str, int]] = []
        for folder, _dirs, files in os.walk(root):
            if cancel is not None and cancel.is_set():
                break
            for name in files:
                if os.path.splitext(name)[1].lower() in wanted:
                    path = os.path.join(folder, name)
                    try:
                        found.append((path, os.stat(path).st_size))
                    except OSError:
                        continue
            if progress:
                progress("scan", len(found), 0)
        return found

    def propose(self, root: Path | str, progress: Progress | None = None, cancel: threading.Event | None = None) -> list[RelinkProposal]:
        """Search `root` for the missing books. Reads and hashes files; writes nothing."""
        missing = self._db.missing_documents()
        if not missing:
            return []
        files = self._scan(Path(root), cancel, progress)
        all_paths = [path for path, _size in files]
        by_size: dict[int, list[str]] = {}
        for path, size in files:
            by_size.setdefault(size, []).append(path)
        by_name: dict[str, list[str]] = {}
        for path, _size in files:
            by_name.setdefault(os.path.basename(path).casefold(), []).append(path)
        hashes: dict[str, str | None] = {}

        def hash_of(path: str) -> str | None:
            if path not in hashes:
                hashes[path] = sha256_file(path)
            return hashes[path]

        proposals: list[RelinkProposal] = []
        claimed: dict[str, str] = {}  # new_path -> doc_id that already took it
        for done, doc in enumerate(missing, start=1):
            if cancel is not None and cancel.is_set():
                break
            match = self._match(doc, by_size, by_name, all_paths, hash_of)
            if progress:
                progress("match", done, len(missing))
            if match is None:
                continue
            new_path, method = match
            proposal = RelinkProposal(doc["id"], doc["title"], doc["file_path"], new_path, method)
            owner = self._db.find_id_by_path(new_path)
            if owner is not None and owner != doc["id"]:
                proposal.selected, proposal.note = False, "Đường dẫn này đã thuộc một sách khác trong thư viện"
            elif new_path.casefold() in claimed:
                proposal.selected, proposal.note = False, "File này đã được đề xuất cho một sách khác (bản trùng)"
            else:
                claimed[new_path.casefold()] = doc["id"]
            proposals.append(proposal)
        return proposals

    @staticmethod
    def _match(doc: dict, by_size: dict[int, list[str]], by_name: dict[str, list[str]], all_paths: list[str],
              hash_of: Callable[[str], str | None]) -> tuple[str, str] | None:
        size, old_path = int(doc.get("file_size") or 0), doc["file_path"]
        same_size = by_size.get(size, []) if size else []
        if doc.get("content_hash"):
            # Normally narrowed to files of the same size (cheap, and almost always enough). A book whose size was
            # never recorded (file_size 0 -- a stat that failed at import time, or a pre-file_size row) has nothing
            # to narrow by, so every scanned file is hashed instead of none -- otherwise it could never be found by
            # hash at all, even for an exact copy sitting right there under a new name.
            for candidate in (same_size if size else all_paths):
                if hash_of(candidate) == doc["content_hash"]:
                    return candidate, METHOD_HASH
        named = [c for c in same_size if _same_name(old_path, c)]
        if len(named) == 1:
            return named[0], METHOD_NAME_SIZE  # same name and size, and no other file qualifies: the user confirms it
        if doc.get("fingerprint"):
            for candidate in by_name.get(os.path.basename(old_path).casefold(), []):
                if fingerprint_file(candidate) == doc["fingerprint"]:
                    return candidate, METHOD_FINGERPRINT
        return None

    # -- 3. apply ---------------------------------------------------------------------------------------------

    def apply(self, proposals: list[RelinkProposal]) -> RelinkResult:
        """Change the stored path of every selected proposal. Only the database is written."""
        result = RelinkResult()
        for proposal in proposals:
            if not proposal.selected:
                continue
            try:
                size = os.stat(proposal.new_path).st_size
            except OSError:
                result.skipped.append((proposal.doc_id, "File đã biến mất khỏi vị trí mới"))
                continue
            owner = self._db.find_id_by_path(proposal.new_path)
            if owner is not None and owner != proposal.doc_id:
                result.skipped.append((proposal.doc_id, "Đường dẫn này đã thuộc một sách khác"))
                continue
            if self._db.relocate_document(proposal.doc_id, proposal.new_path, size):
                result.updated += 1
            else:
                result.skipped.append((proposal.doc_id, "Sách không còn trong thư viện"))
        if self._bus is not None:
            self._bus.publish(LibraryFilesMissingEvent(count=self._db.count_missing()))
            if result.updated:
                self._bus.publish(LibraryUpdatedEvent())
        logger.info("Relinked %d book(s), skipped %d", result.updated, len(result.skipped))
        return result
