# SPDX-License-Identifier: AGPL-3.0-or-later
"""Backup and restore of `library.db` (S1-03, FR-OPS-03).

Backups are consistent copies made with SQLite's online backup API (safe while the app is running and the
database is in WAL mode), verified before they are kept, stored next to the library in `backups/` and pruned
to the newest `AppConfig.backup_retention`. Three things create one:

- the user ("Sao lưu ngay" in Settings);
- an upgrade of the library: `before_migration` is the hook `DatabaseManager.initialize_tables` calls before the
  first versioned migration of an existing library, so **no backup, no migration** (a failing backup aborts it);
- a restore: the current library is backed up first, so a wrong restore can itself be undone.

Restoring copies the chosen backup *into the open connection* (under the write lock), then re-runs the schema
upgrade so an older backup is brought up to date. Only the database is handled here: the user's book files are
never touched, and cover images are a cache that is rebuilt.
"""
from __future__ import annotations

import logging
import os
import re
import sqlite3
import time
from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path

from smartdoc.infrastructure import schema_migrations
from smartdoc.infrastructure.database import DatabaseManager

logger = logging.getLogger(__name__)

BACKUP_DIR_NAME = "backups"
DEFAULT_RETENTION = 5
MIN_RETENTION = 1
MAX_RETENTION = 50

REASON_MANUAL = "manual"
REASON_PRE_UPGRADE = "pre-upgrade"
REASON_PRE_RESTORE = "pre-restore"

_NAME = re.compile(r"^library-(?P<stamp>\d{8}-\d{6}-\d{3,})-(?P<reason>[a-z][a-z0-9-]*)\.db$")


class BackupError(Exception):
    """A backup or restore could not be done; the message is written for the user."""


@dataclass(frozen=True)
class BackupInfo:
    path: Path
    created_at: float
    size: int
    reason: str
    schema_version: int | None
    """`PRAGMA user_version` of the backup, or None if it could not be read."""


def snapshot(connection: sqlite3.Connection, target: Path) -> None:
    """Write a verified, consistent copy of `connection`'s database to `target` (atomically).

    The caller decides about locking: `BackupService.create_backup` holds the write lock, the migration hook
    already runs under it."""
    part = target.with_name(target.name + ".part")
    try:
        target.parent.mkdir(parents=True, exist_ok=True)
        part.unlink(missing_ok=True)
        connection.commit()
        destination = sqlite3.connect(part)
        try:
            connection.backup(destination)
            # The copy inherits WAL mode from the library; a backup must be ONE self-contained file, not a
            # .db plus -wal/-shm side files that appear whenever it is opened.
            destination.execute("PRAGMA journal_mode=DELETE")
            destination.commit()
        finally:
            destination.close()
        _verify(part, expected_documents=_count_documents(connection))
        os.replace(part, target)
    except (sqlite3.Error, OSError, BackupError) as exc:
        part.unlink(missing_ok=True)
        if isinstance(exc, BackupError):
            raise
        raise BackupError(f"Không sao lưu được thư viện: {exc}") from exc


def _count_documents(connection: sqlite3.Connection) -> int:
    row = connection.execute("SELECT COUNT(*) FROM documents").fetchone()
    return int(row[0])


def _open_readonly(path: Path) -> sqlite3.Connection:
    return sqlite3.connect(f"file:{path.as_posix()}?mode=ro", uri=True)


def _verify(path: Path, expected_documents: int | None = None) -> None:
    """The copy opens, passes SQLite's own check and holds as many books as the source."""
    try:
        connection = _open_readonly(path)
        try:
            if connection.execute("PRAGMA quick_check").fetchone()[0] != "ok":
                raise BackupError("Bản sao lưu bị lỗi (kiểm tra toàn vẹn không đạt).")
            count = _count_documents(connection)
        finally:
            connection.close()
    except sqlite3.Error as exc:
        raise BackupError(f"Bản sao lưu không đọc được: {exc}") from exc
    if expected_documents is not None and count != expected_documents:
        raise BackupError(f"Bản sao lưu thiếu dữ liệu ({count} thay vì {expected_documents} tài liệu).")


class BackupService:
    def __init__(self, db: DatabaseManager, retention: Callable[[], int] | int = DEFAULT_RETENTION,
                 folder: Callable[[], str] | str = "") -> None:
        self._db = db
        self._retention = retention
        self._folder = folder

    # -- where and how many ----------------------------------------------------------------------------------

    @property
    def default_directory(self) -> Path:
        if self._db.db_path == ":memory:":
            raise BackupError("Thư viện đang ở bộ nhớ tạm, không có tệp để sao lưu.")
        return Path(self._db.db_path).resolve().parent / BACKUP_DIR_NAME

    @property
    def custom_folder(self) -> str:
        return (self._folder() if callable(self._folder) else self._folder or "").strip()

    @property
    def directory(self) -> Path:
        """Where backups are kept: the folder the user chose, else `backups/` next to the library."""
        if not self.custom_folder:
            return self.default_directory
        return Path(self.custom_folder)

    def check_folder(self, folder: str | Path | None = None) -> str:
        """"" when backups can be written to `folder` (default: the current one), else the reason in plain words."""
        target = Path(folder) if folder else self.directory
        if not target.exists():
            try:
                target.mkdir(parents=True, exist_ok=True)
            except OSError:
                return f"Không tạo được thư mục sao lưu \"{target}\" (ổ đĩa chưa cắm hoặc không có quyền ghi)."
        if not target.is_dir():
            return f"\"{target}\" không phải là thư mục."
        probe = target / f".mewbook-write-test-{os.getpid()}"
        try:
            probe.write_bytes(b"")
            probe.unlink()
        except OSError:
            return f"Không ghi được vào thư mục sao lưu \"{target}\". Hãy chọn thư mục khác."
        return ""

    def _writable_directory(self) -> Path:
        problem = self.check_folder() if self.custom_folder else ""
        if problem:
            raise BackupError(problem)
        return self.directory

    def retention(self) -> int:
        value = self._retention() if callable(self._retention) else self._retention
        return max(MIN_RETENTION, min(MAX_RETENTION, int(value)))

    # -- create ----------------------------------------------------------------------------------------------

    def _new_path(self, reason: str, folder: Path | None = None) -> Path:
        safe = re.sub(r"[^a-z0-9-]+", "-", reason.lower()).strip("-") or REASON_MANUAL
        now = time.time()
        stamp = f"{time.strftime('%Y%m%d-%H%M%S', time.localtime(now))}-{int((now % 1) * 1000):03d}"
        folder = folder or self.directory
        path = folder / f"library-{stamp}-{safe}.db"
        counter = 1
        while path.exists():  # two backups in the same millisecond
            path = folder / f"library-{stamp}{counter}-{safe}.db"
            counter += 1
        return path

    def create_backup(self, reason: str = REASON_MANUAL) -> BackupInfo:
        self._writable_directory()  # a chosen folder that cannot be used is reported, not replaced by another one
        with self._db.write_lock:
            path = self._new_path(reason)
            snapshot(self._db.connection, path)
        logger.info("Library backed up to %s (%s)", path.name, reason)
        self.prune()
        return self._info(path)

    def before_migration(self, from_version: int, to_version: int) -> None:
        """`DatabaseManager.initialize_tables(before_migrate=...)` hook. Runs under the write lock already."""
        # Upgrading must still be possible with the chosen folder gone (an unplugged drive): this one safety copy
        # then goes to the default folder, and the log says so.
        if self.custom_folder and self.check_folder():
            logger.warning("Backup folder %s is not usable; the pre-upgrade backup goes to the default folder", self.custom_folder)
            path = self._new_path(f"{REASON_PRE_UPGRADE}-v{from_version}-to-v{to_version}", self.default_directory)
        else:
            path = self._new_path(f"{REASON_PRE_UPGRADE}-v{from_version}-to-v{to_version}")
        snapshot(self._db.connection, path)
        logger.info("Library backed up to %s before upgrading its schema", path.name)
        self.prune()

    # -- list and prune --------------------------------------------------------------------------------------

    @staticmethod
    def _info(path: Path) -> BackupInfo:
        match = _NAME.match(path.name)
        version: int | None = None
        try:
            connection = _open_readonly(path)
            try:
                version = schema_migrations.get_version(connection)
            finally:
                connection.close()
        except sqlite3.Error:
            pass
        return BackupInfo(
            path=path,
            created_at=path.stat().st_mtime,
            size=path.stat().st_size,
            reason=match["reason"] if match else "unknown",
            schema_version=version,
        )

    def list_backups(self) -> list[BackupInfo]:
        """Newest first."""
        folder = self.directory
        if not folder.is_dir():
            return []
        found = [p for p in folder.iterdir() if _NAME.match(p.name)]
        found.sort(key=lambda p: (p.stat().st_mtime, p.name), reverse=True)
        return [self._info(p) for p in found]

    def prune(self) -> list[Path]:
        """Delete the oldest backups beyond the retention count; returns what was deleted."""
        folder = self.directory
        if not folder.is_dir():
            return []
        found = sorted((p for p in folder.iterdir() if _NAME.match(p.name)), key=lambda p: (p.stat().st_mtime, p.name), reverse=True)
        removed: list[Path] = []
        for old in found[self.retention():]:
            try:
                old.unlink()
                removed.append(old)
            except OSError:
                logger.warning("Could not delete old backup %s", old)
        return removed

    # -- restore ---------------------------------------------------------------------------------------------

    def restore(self, path: Path) -> BackupInfo:
        """Replace the library with the backup at `path`; returns the safety backup of what it replaced.

        The caller (the UI) asks the user first and refreshes what it shows afterwards."""
        path = Path(path)
        if not path.is_file():
            raise BackupError("Không tìm thấy tệp sao lưu.")
        _verify(path)
        try:
            connection = _open_readonly(path)
            try:
                version = schema_migrations.get_version(connection)
            finally:
                connection.close()
        except sqlite3.Error as exc:
            raise BackupError(f"Bản sao lưu không đọc được: {exc}") from exc
        if version > schema_migrations.latest_version():
            raise schema_migrations.SchemaTooNewError(version, schema_migrations.latest_version())

        safety = self.create_backup(REASON_PRE_RESTORE)
        try:
            with self._db.write_lock:
                self._db.connection.commit()
                source = _open_readonly(path)
                try:
                    source.backup(self._db.connection)
                finally:
                    source.close()
        except sqlite3.Error as exc:
            raise BackupError(
                f"Không khôi phục được: {exc}. Bản sao lưu thư viện hiện tại được giữ tại {safety.path.name}."
            ) from exc
        # An older backup lacks newer columns/tables: bring it up to date (also re-creates the indexes/triggers).
        self._db.initialize_tables(before_migrate=self.before_migration)
        logger.info("Library restored from %s (previous state kept as %s)", path.name, safety.path.name)
        return safety
