# SPDX-License-Identifier: AGPL-3.0-or-later
"""MewBook's own trash: a file removed from the duplicate finder goes here first instead of being deleted for good.

Every trashed book is one folder `trash/<id>/` under the app data folder holding the file itself, `meta.json` (where it
came from, when it was trashed, the library row and its collections) and `content.txt` (the search text, so a restored
book is searchable again without being re-read). No database table: the trash survives a library restore and a
migration because it is just files.

- `send(items)` moves the files, then removes the library entries. A file that cannot be moved (locked, no rights) is
  left exactly where it is *and* stays in the library -- nothing is half-done -- and is reported.
- `restore(item_id)` puts the file back where it was (never over another file: a name clash gets a " (khôi phục)"
  suffix) and re-adds the book with its hashtags, collections and search text.
- After `AppConfig.trash_retention_days` days (0 = never) an item is deleted for good by `purge_expired`, which the app
  runs at start-up. The user can also delete one item or empty the trash by hand. Only files inside `trash/` are ever
  deleted from here; the original ebook files are never touched by anything but `send`, which moves them.
"""
from __future__ import annotations

import json
import logging
import shutil
import time
import uuid
from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path

from smartdoc.core.event_bus import LibraryUpdatedEvent

logger = logging.getLogger(__name__)

TRASH_DIR_NAME = "trash"
DEFAULT_RETENTION_DAYS = 30
MAX_RETENTION_DAYS = 365
_META = "meta.json"
_CONTENT = "content.txt"
_DAY = 86_400.0


class TrashError(Exception):
    """An item could not be restored or deleted; the message is written for the user."""


@dataclass(frozen=True)
class TrashItem:
    item_id: str
    title: str
    original_path: str
    file_name: str
    size: int
    trashed_at: float
    expires_at: float | None
    """None when the trash is set to keep things until they are deleted by hand."""

    def days_left(self, now: float | None = None) -> int | None:
        if self.expires_at is None:
            return None
        return max(0, int((self.expires_at - (time.time() if now is None else now)) // _DAY) + 1)


@dataclass
class SendResult:
    moved: list[str]  # doc ids now in the trash
    missing: list[str]  # doc ids whose file was already gone: only the library entry was removed
    failed: list[tuple[str, str]]  # (doc id, reason) -- untouched


class TrashService:
    def __init__(self, context) -> None:
        self.context = context

    @property
    def directory(self) -> Path:
        return self.context.config.app_data_dir / TRASH_DIR_NAME

    def retention_days(self) -> int:
        return max(0, min(MAX_RETENTION_DAYS, int(getattr(self.context.config.config, "trash_retention_days", DEFAULT_RETENTION_DAYS))))

    # -- into the trash -------------------------------------------------------------------------------------------
    def send(self, items: list[tuple[str, str | None]], progress: Callable[[int, int], None] | None = None) -> SendResult:
        """Move each book's file into the trash and drop it from the library. `progress(done, total)` is told after each file:
        moving between drives copies the bytes, so a long list takes a while and the caller shows how far it is."""
        result = SendResult([], [], [])
        # Which collections each book is in, read once: asking per book made a long list slower with every collection.
        membership = {c["id"]: set(self.context.db.list_collection_document_ids(c["id"])) for c in self.context.db.list_collections()}
        for done, (doc_id, file_path) in enumerate(items):
            if progress is not None:
                progress(done, len(items))
            doc = self.context.db.get_document(doc_id)
            if doc is None:
                continue
            path = Path(file_path or doc.get("file_path") or "")
            if not path.is_file():
                self.context.db.delete_document(doc_id)
                result.missing.append(doc_id)
                continue
            try:
                self._store(doc, path, membership)
            except OSError as exc:
                logger.warning("Could not move %s to the trash: %s", path, exc)
                result.failed.append((doc_id, "File đang được chương trình khác dùng hoặc không có quyền di chuyển"
                                      if isinstance(exc, PermissionError) else f"Không di chuyển được file: {exc.strerror or exc}"))
                continue
            self.context.db.delete_document(doc_id)
            result.moved.append(doc_id)
        if result.moved or result.missing:
            self.context.event_bus.publish(LibraryUpdatedEvent())
        return result

    def _store(self, doc: dict, path: Path, membership: dict[str, set[str]]) -> None:
        folder = self.directory / uuid.uuid4().hex
        folder.mkdir(parents=True)
        try:
            row = {k: v for k, v in doc.items() if k != "content"}
            collections = [collection_id for collection_id, members in membership.items() if doc["id"] in members]
            (folder / _CONTENT).write_text(doc.get("content") or "", encoding="utf-8")
            self.context.self_writes.mark(str(path))  # the watcher will see it vanish; that is not news
            shutil.move(str(path), str(folder / path.name))
            meta = {"doc": row, "collections": collections, "reading": self.context.db.get_reading_progress(doc["id"]), "original_path": str(path), "file_name": path.name,
                    "trashed_at": time.time()}
            (folder / _META).write_text(json.dumps(meta, ensure_ascii=False), encoding="utf-8")
        except OSError:
            shutil.rmtree(folder, ignore_errors=True)  # only ever our own fresh folder
            raise

    # -- looking --------------------------------------------------------------------------------------------------
    def list_items(self) -> list[TrashItem]:
        """Newest first."""
        found: list[TrashItem] = []
        if not self.directory.is_dir():
            return found
        days = self.retention_days()
        for folder in self.directory.iterdir():
            meta = self._read_meta(folder)
            if meta is None:
                continue
            trashed_at = float(meta.get("trashed_at") or 0)
            stored = folder / meta.get("file_name", "")
            found.append(TrashItem(
                item_id=folder.name, title=(meta.get("doc") or {}).get("title") or meta.get("file_name", ""),
                original_path=meta.get("original_path", ""), file_name=meta.get("file_name", ""),
                size=stored.stat().st_size if stored.is_file() else 0, trashed_at=trashed_at,
                expires_at=trashed_at + days * _DAY if days else None))
        found.sort(key=lambda item: item.trashed_at, reverse=True)
        return found

    @staticmethod
    def _read_meta(folder: Path) -> dict | None:
        try:
            return json.loads((folder / _META).read_text(encoding="utf-8"))
        except (OSError, ValueError):
            return None

    def _folder(self, item_id: str) -> Path:
        if not item_id or item_id != Path(item_id).name:  # an id is a bare folder name, never a path
            raise TrashError("Mục này không hợp lệ.")
        return self.directory / item_id

    # -- out of the trash -----------------------------------------------------------------------------------------
    def restore(self, item_id: str) -> Path:
        """Put the file back and re-add the book; returns where the file is now."""
        folder = self._folder(item_id)
        meta = self._read_meta(folder)
        if meta is None:
            raise TrashError("Không đọc được thông tin của mục này trong thùng rác.")
        stored = folder / meta["file_name"]
        if not stored.is_file():
            raise TrashError("File của mục này không còn trong thùng rác.")
        target = Path(meta["original_path"])
        if target.exists():
            target = target.with_name(f"{target.stem} (khôi phục){target.suffix}")
            counter = 2
            while target.exists():
                target = target.with_name(f"{Path(meta['original_path']).stem} (khôi phục {counter}){target.suffix}")
                counter += 1
        try:
            target.parent.mkdir(parents=True, exist_ok=True)
            shutil.move(str(stored), str(target))
        except OSError as exc:
            raise TrashError(f"Không khôi phục được file về {target.parent}: {exc.strerror or exc}") from exc
        doc = dict(meta["doc"])
        doc["file_path"] = str(target)
        try:
            content = (folder / _CONTENT).read_text(encoding="utf-8")
        except OSError:
            content = ""
        self.context.self_writes.mark(str(target))  # the folder watcher must not import it a second time
        self.context.db.add_or_update_document(doc["id"], doc, extracted_text=content)
        self.context.db.restore_document_columns(doc["id"], doc)  # publisher, ISBN, locked fields, AI summary...
        if meta.get("reading"):
            self.context.db.restore_reading_progress(doc["id"], meta["reading"])
        existing = {c["id"] for c in self.context.db.list_collections()}
        for collection_id in meta.get("collections", []):
            if collection_id in existing:
                self.context.db.add_documents_to_collection(collection_id, [doc["id"]])
        shutil.rmtree(folder, ignore_errors=True)
        self.context.event_bus.publish(LibraryUpdatedEvent())
        return target

    def delete_forever(self, item_id: str) -> None:
        folder = self._folder(item_id)
        if folder.is_dir():
            meta = self._read_meta(folder) or {}
            shutil.rmtree(folder, ignore_errors=False)
            logger.info("Trash: deleted for good %s (from %s)", meta.get("file_name", item_id), meta.get("original_path", "?"))

    def empty(self, progress: Callable[[int, int], None] | None = None) -> int:
        """Delete everything in the trash for good; returns how many items went."""
        count = 0
        items = self.list_items()
        for done, item in enumerate(items):
            if progress is not None:
                progress(done, len(items))
            try:
                self.delete_forever(item.item_id)
                count += 1
            except OSError:
                logger.warning("Could not delete trash item %s", item.item_id)
        return count

    def purge_expired(self, now: float | None = None) -> int:
        """Delete the items older than the retention period; returns how many went."""
        moment = time.time() if now is None else now
        count = 0
        for item in self.list_items():
            if item.expires_at is not None and item.expires_at <= moment:
                try:
                    self.delete_forever(item.item_id)
                    count += 1
                except OSError:
                    logger.warning("Could not purge trash item %s", item.item_id)
        return count
