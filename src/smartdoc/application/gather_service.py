# SPDX-License-Identifier: AGPL-3.0-or-later
"""Gom sách về một thư mục: put the library's files in one folder, by copying or by moving.

Two steps, like the relink service, so nothing happens by surprise:

1. `plan` looks at the books and the target folder and returns what *would* happen, book by book (nothing is written).
   It also totals the size and compares it with the free space, so the person is told before, not after, that the
   target drive is too small.
2. `run` does it. **Copy** leaves every book exactly where it is (the library keeps pointing at the originals; the folder
   is a set of extra copies). **Move** puts the file in the folder and updates the path in the library, so nothing
   goes missing.

Safety, in this order for every file: the file is copied under a name that does not exist yet (a clash gets " (2)", so
nothing in the target is ever overwritten), the copy is checked to be the same size, and only then -- for a move -- the
library row is repointed and the original removed. If anything fails half way the copy is deleted and the original and
the library entry are left as they were; the failure is reported with its reason and the run continues with the next
book. A move is refused for files already in the target folder. The folder watcher is told (self-writes) so it does not
import a copy as a new book.
"""
from __future__ import annotations

import logging
import os
import shutil
from collections.abc import Callable
from dataclasses import dataclass, field
from pathlib import Path

from smartdoc.core.event_bus import LibraryUpdatedEvent

logger = logging.getLogger(__name__)

MODE_COPY, MODE_MOVE = "copy", "move"

STATUS_READY = "ready"
STATUS_MISSING = "missing"  # the file is not where the library says
STATUS_THERE = "there"  # already in the target folder
Progress = Callable[[int, int], None]  # (done, total)


class GatherError(Exception):
    """The plan cannot even start (no usable target folder); the message is written for the user."""


@dataclass
class GatherItem:
    doc_id: str
    title: str
    source: str
    size: int
    status: str
    destination: str = ""


@dataclass
class GatherPlan:
    target: str
    mode: str
    items: list[GatherItem]
    free_bytes: int

    @property
    def ready(self) -> list[GatherItem]:
        return [i for i in self.items if i.status == STATUS_READY]

    @property
    def total_bytes(self) -> int:
        return sum(i.size for i in self.ready)

    @property
    def enough_space(self) -> bool:
        """A move on the same drive needs no room; anything else needs the total plus a little headroom."""
        if self.mode == MODE_MOVE and all(_same_drive(i.source, self.target) for i in self.ready):
            return True
        return self.free_bytes >= self.total_bytes + 50 * 1024 * 1024 if self.ready else True


@dataclass
class GatherResult:
    done: int = 0
    failed: list[tuple[str, str]] = field(default_factory=list)  # (title, reason)
    skipped: int = 0


def _same_drive(a: str, b: str) -> bool:
    return os.path.splitdrive(os.path.abspath(a))[0].lower() == os.path.splitdrive(os.path.abspath(b))[0].lower()


def _is_inside(path: Path, folder: Path) -> bool:
    try:
        path.resolve().relative_to(folder.resolve())
    except (ValueError, OSError):
        return False
    return True


class GatherService:
    def __init__(self, context) -> None:
        self.context = context

    # -- 1. what would happen -------------------------------------------------------------------------------------
    def plan(self, target: str, mode: str, doc_ids: list[str] | None = None) -> GatherPlan:
        folder = Path(target)
        if not target.strip():
            raise GatherError("Hãy chọn thư mục đích.")
        if folder.exists() and not folder.is_dir():
            raise GatherError(f"\"{folder}\" không phải là thư mục.")
        if mode not in (MODE_COPY, MODE_MOVE):
            raise GatherError("Hãy chọn sao chép hoặc di chuyển.")
        probe = folder if folder.exists() else folder.parent
        while not probe.exists() and probe != probe.parent:
            probe = probe.parent
        try:
            free = shutil.disk_usage(probe).free
        except OSError:
            free = 0
        items: list[GatherItem] = []
        taken: set[str] = set()
        for doc in self.context.db.documents_for_gather(doc_ids):
            source = Path(doc["file_path"] or "")
            if not source.is_file():
                items.append(GatherItem(doc["id"], doc["title"], str(source), 0, STATUS_MISSING))
                continue
            if folder.exists() and source.parent.resolve() == folder.resolve():
                items.append(GatherItem(doc["id"], doc["title"], str(source), source.stat().st_size, STATUS_THERE))
                continue
            destination = self._free_name(folder, source.name, taken)
            taken.add(os.path.normcase(str(destination)))
            items.append(GatherItem(doc["id"], doc["title"], str(source), source.stat().st_size, STATUS_READY, str(destination)))
        return GatherPlan(str(folder), mode, items, free)

    @staticmethod
    def _free_name(folder: Path, name: str, taken: set[str]) -> Path:
        """`name` in `folder`, or `name (2)`, `name (3)`... when that is already there or already planned."""
        stem, suffix = Path(name).stem, Path(name).suffix
        candidate, counter = folder / name, 2
        while candidate.exists() or os.path.normcase(str(candidate)) in taken:
            candidate = folder / f"{stem} ({counter}){suffix}"
            counter += 1
        return candidate

    def watched_folder_warning(self, target: str) -> str:
        """A sentence when the target lies inside a folder MewBook watches (copies would be offered as new books), else ''."""
        for watched in self.context.config.config.watch_folders:
            if _is_inside(Path(target), Path(watched)):
                return (f"Thư mục đích nằm trong thư mục MewBook đang theo dõi ({watched}). Với “Sao chép”, các bản sao "
                        "có thể bị nhận là sách trùng; hãy chọn thư mục khác nếu không muốn vậy.")
        return ""

    # -- 2. do it -------------------------------------------------------------------------------------------------
    def run(self, plan: GatherPlan, progress: Progress | None = None, should_cancel: Callable[[], bool] | None = None) -> GatherResult:
        result = GatherResult(skipped=len(plan.items) - len(plan.ready))
        try:
            Path(plan.target).mkdir(parents=True, exist_ok=True)
        except OSError as exc:
            raise GatherError(f"Không tạo được thư mục đích: {exc.strerror or exc}") from exc
        ready = plan.ready
        for done, item in enumerate(ready):
            if should_cancel is not None and should_cancel():
                break
            if progress is not None:
                progress(done, len(ready))
            try:
                self._one(item, plan.mode)
                result.done += 1
            except OSError as exc:
                logger.warning("Gather failed for %s: %s", item.source, exc)
                result.failed.append((item.title, "File đang được chương trình khác dùng hoặc không có quyền"
                                      if isinstance(exc, PermissionError) else (exc.strerror or str(exc))))
        if progress is not None:
            progress(len(ready), len(ready))
        if plan.mode == MODE_MOVE and result.done:
            self.context.event_bus.publish(LibraryUpdatedEvent())
        return result

    def _one(self, item: GatherItem, mode: str) -> None:
        source, destination = Path(item.source), Path(item.destination)
        destination = self._free_name(destination.parent, destination.name, set())  # someone may have added it meanwhile
        self.context.self_writes.mark(str(destination))
        if mode == MODE_MOVE:
            self.context.self_writes.mark(str(source))
        shutil.copy2(source, destination)
        try:
            if destination.stat().st_size != source.stat().st_size:
                raise OSError("Bản sao không đủ dung lượng (ổ đĩa đầy?)")
            if mode == MODE_MOVE:
                if not self.context.db.relocate_document(item.doc_id, str(destination), destination.stat().st_size):
                    raise OSError("Sách không còn trong thư viện")
        except OSError:
            destination.unlink(missing_ok=True)  # only the copy we just made
            raise
        if mode == MODE_MOVE:
            try:
                source.unlink()
            except OSError as exc:
                # The library now points at the copy, so the book is safe; only the old file lingers.
                logger.warning("Moved %s but could not remove the original: %s", source, exc)
