"""Applies metadata the user accepted, and takes it back (docs/METADATA_LOOKUP_SPEC.md §4-5).

`MetadataApplier.apply()` is the only path by which a suggestion changes
anything, and it is only ever called after the user pressed "Áp dụng":

1. drop what must not be written: fields the user typed by hand (locked),
   blank values, and values that don't look right (a year that isn't a year,
   an ISBN that isn't one);
2. if the user ticked "Ghi vào file gốc" -- back the file up and write it
   (metadata_writer.py). A file that can't be written does NOT stop the
   library update; the reason comes back in `ApplyResult.file_error`;
3. update the library index and record every change in `metadata_history`
   under one run id;
4. tell the UI (`DocumentUpdatedEvent`, `LibraryUpdatedEvent`).

`undo_latest()` reverses the newest run of a book: fields back to their old
values and, if that run wrote the file, the file back from its backup. If the
file can't be restored nothing is changed, so the index never claims a state the
file isn't in.
"""
from __future__ import annotations

import datetime
import logging
import os
import unicodedata
import uuid
from dataclasses import dataclass, field

from smartdoc.application.metadata_lookup import normalize_isbn
from smartdoc.application.metadata_writer import MetadataWriteError, MetadataWriter
from smartdoc.core.event_bus import DocumentUpdatedEvent, LibraryUpdatedEvent
from smartdoc.infrastructure.file_hash import sha256_file

logger = logging.getLogger(__name__)

_MAX_LENGTH = {"title": 500, "author": 500, "publisher": 200, "series": 200, "language": 20, "description": 5000}


class MetadataApplyError(Exception):
    """The update could not be applied (or undone); the message is shown to the user."""


@dataclass
class ApplyResult:
    run_id: str
    changed_fields: list[str] = field(default_factory=list)
    written_fields: tuple[str, ...] = ()  # also written into the book file
    index_only_fields: tuple[str, ...] = ()  # the file's format can't hold these
    locked_fields: tuple[str, ...] = ()  # left alone: the user typed them by hand
    backup_made: bool = False  # the file's old copy was kept ("Sao lưu trước khi thay đổi")
    file_error: str = ""  # why the file was not written ("" if it was, or wasn't asked for)


@dataclass
class UndoResult:
    run_id: str | None
    restored_fields: list[str] = field(default_factory=list)
    file_restored: bool = False


class MetadataApplier:
    def __init__(self, context, writer: MetadataWriter | None = None) -> None:
        self.context = context
        config = context.config
        self.writer = writer or MetadataWriter(
            lambda: config.config.backup_dir,
            keep_backups=lambda: config.config.backup_keep,
            self_writes=getattr(context, "self_writes", None),
            enabled=lambda: config.config.backup_before_change,
        )

    # -- apply -----------------------------------------------------------------------

    def apply(
        self,
        doc_id: str,
        changes: dict[str, object],
        *,
        source: str,
        confidence: float | None = None,
        write_to_file: bool = False,
    ) -> ApplyResult:
        db = self.context.db
        doc = db.get_document(doc_id)
        if doc is None:
            raise MetadataApplyError("Không tìm thấy tài liệu trong thư viện.")

        clean = self._clean(changes)
        locked = db.locked_fields(doc_id)
        skipped_locked = tuple(name for name in clean if name in locked)
        clean = {name: value for name, value in clean.items() if name not in locked}
        run_id = uuid.uuid4().hex
        result = ApplyResult(run_id=run_id, locked_fields=skipped_locked)
        if not clean:
            return result

        path, extension = doc["file_path"], doc.get("extension") or os.path.splitext(doc["file_path"])[1]
        backup_path = None
        if write_to_file:
            try:
                written = self.writer.write(path, extension, clean, doc_id, run_id)
            except MetadataWriteError as exc:
                result.file_error = str(exc)
            else:
                backup_path = written.backup_path
                result.backup_made = bool(backup_path)
                result.written_fields = written.written_fields
                result.index_only_fields = written.skipped_fields

        try:
            result.changed_fields = db.apply_metadata(
                doc_id,
                run_id,
                clean,
                source=source,
                confidence=confidence,
                written_to_file=bool(result.written_fields),
                backup_path=backup_path,
            )
            if result.written_fields:
                db.set_file_stats(doc_id, sha256_file(path), os.path.getsize(path))
        except Exception:
            if backup_path:  # the file must not say something the library doesn't
                try:
                    self.writer.restore(backup_path, path)
                except MetadataWriteError:
                    logger.exception("Could not roll the file back after a failed update: %s", path)
            raise
        if result.changed_fields:
            self._announce(doc_id)
        return result

    # -- undo ------------------------------------------------------------------------

    def can_undo(self, doc_id: str) -> bool:
        return self.context.db.latest_metadata_run(doc_id) is not None

    def undo_latest(self, doc_id: str) -> UndoResult:
        db = self.context.db
        run_id = db.latest_metadata_run(doc_id)
        if run_id is None:
            return UndoResult(run_id=None)
        rows = db.metadata_run(run_id)
        backup = next((row["backup_path"] for row in rows if row["written_to_file"] and row["backup_path"]), None)
        doc = db.get_document(doc_id)
        if doc is None:
            raise MetadataApplyError("Không tìm thấy tài liệu trong thư viện.")

        if backup:
            try:
                self.writer.restore(backup, doc["file_path"])
            except MetadataWriteError as exc:
                raise MetadataApplyError(f"Không hoàn tác được vì không khôi phục được file: {exc}") from exc
            db.set_file_stats(doc_id, sha256_file(doc["file_path"]), os.path.getsize(doc["file_path"]))
        undone = db.undo_metadata_run(run_id)
        self._announce(doc_id)
        return UndoResult(run_id=run_id, restored_fields=[row["field"] for row in undone], file_restored=bool(backup))

    # -- helpers ---------------------------------------------------------------------

    @staticmethod
    def _clean(changes: dict[str, object]) -> dict[str, object]:
        """Only sensible, non-blank values of the fields a metadata update may set."""
        clean: dict[str, object] = {}
        for name, value in changes.items():
            if name in _MAX_LENGTH:
                text = unicodedata.normalize("NFC", str(value))
                text = " ".join(text.split()) if name != "description" else text.strip()
                if text:
                    clean[name] = text[: _MAX_LENGTH[name]]
            elif name == "isbn":
                isbn = normalize_isbn(str(value))
                if isbn:
                    clean[name] = isbn
            elif name == "pub_year":
                try:
                    year = int(value)
                except (TypeError, ValueError):
                    continue
                if 1000 <= year <= datetime.date.today().year + 1:
                    clean[name] = year
        if "language" in clean:
            clean["language"] = str(clean["language"]).lower()
        return clean

    def _announce(self, doc_id: str) -> None:
        self.context.event_bus.publish(DocumentUpdatedEvent(doc_id=doc_id))
        self.context.event_bus.publish(LibraryUpdatedEvent())
