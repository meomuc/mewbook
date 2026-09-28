# SPDX-License-Identifier: AGPL-3.0-or-later
"""Gom sách về một thư mục: put the library's files in one folder, by copying or by moving.

Two steps, like the relink service, so nothing happens by surprise:

1. `plan` looks at the books and the target folder and returns what *would* happen, book by book (nothing is written).
   It also totals the size and compares it with the free space, so the person is told before, not after, that the
   target drive is too small.
2. `run` does it. **Copy** leaves every book exactly where it is (the library keeps pointing at the originals; the folder
   is a set of extra copies). **Move** puts the file in the folder and updates the path in the library, so nothing
   goes missing.

`by_category=True` (off by default) sorts the copies/moves into one subfolder per book instead of dumping everything
flat into the target: the book's first hashtag names its subfolder (a book with several hashtags uses whichever one
was typed or applied first), and a book with none goes into "Chưa phân loại" -- the same "no tag" bucket the sidebar
filter already uses (domain/author_names.NO_TAG_LABEL). The library's own hashtags decide the layout; nothing here
reads or changes them.

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
import re
import shutil
from collections.abc import Callable
from dataclasses import dataclass, field
from pathlib import Path

from smartdoc.core.event_bus import LibraryUpdatedEvent
from smartdoc.domain.author_names import NO_TAG_LABEL, split_tags

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
    by_category: bool = False  # whether `ready` items were sorted into a subfolder per hashtag

    @property
    def ready(self) -> list[GatherItem]:
        return [i for i in self.items if i.status == STATUS_READY]

    @property
    def category_count(self) -> int:
        """How many distinct subfolders `ready` will land in -- 0 when `by_category` is off."""
        if not self.by_category:
            return 0
        return len({Path(i.destination).parent for i in self.ready})

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


_INVALID_FOLDER_CHARS = re.compile(r'[<>:"/\\|?*\x00-\x1f]')


def _category_folder_name(tags: str | None) -> str:
    """The subfolder name for `by_category`: the first hashtag on the book (whichever was typed or applied first),
    or NO_TAG_LABEL when it has none -- the same "Chưa phân loại" bucket the sidebar filter already uses."""
    found = split_tags(tags)
    name = found[0] if found else NO_TAG_LABEL
    name = _INVALID_FOLDER_CHARS.sub("_", name).strip(" .")
    return name or NO_TAG_LABEL


class GatherService:
    def __init__(self, context) -> None:
        self.context = context

    # -- 1. what would happen -------------------------------------------------------------------------------------
    def plan(self, target: str, mode: str, doc_ids: list[str] | None = None, *, by_category: bool = False) -> GatherPlan:
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
            item_folder = folder / _category_folder_name(doc.get("tags")) if by_category else folder
            if item_folder.exists() and source.parent.resolve() == item_folder.resolve():
                items.append(GatherItem(doc["id"], doc["title"], str(source), source.stat().st_size, STATUS_THERE))
                continue
            destination = self._free_name(item_folder, source.name, taken)
            taken.add(os.path.normcase(str(destination)))
            items.append(GatherItem(doc["id"], doc["title"], str(source), source.stat().st_size, STATUS_READY, str(destination)))
        return GatherPlan(str(folder), mode, items, free, by_category)

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
        destination.parent.mkdir(parents=True, exist_ok=True)  # the category subfolder, when by_category is on
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
