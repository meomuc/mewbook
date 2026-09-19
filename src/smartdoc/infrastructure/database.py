"""TDD-001: SQLite FTS5 Search Database.

Local library database. Bulk metadata lives in `documents`; full-text search
is served by the external-content virtual table `documents_fts`, kept in
sync by triggers.

Note on schema (deliberate deviation from the literal TDD spec): FTS5's
`content_rowid` must reference an INTEGER rowid column, but our document
IDs are MD5 hex strings (see domain.models.MetadataNormalizer). So
`documents` keeps an autoincrement integer `doc_rowid` as the real rowid
for FTS linkage, and `id` is a separate unique text column that the rest
of the app addresses documents by. Declaring `id TEXT` as the
content_rowid (as a literal reading of the spec would do) does not work in
SQLite and would fail at CREATE VIRTUAL TABLE time.
"""
from __future__ import annotations

import json
import logging
import re
import sqlite3
import threading
import time
import uuid
from typing import Any

from smartdoc.domain.author_names import (
    author_key,
    author_keys,
    normalize_key,
    rename_person_in_field,
    split_author_names,
    tag_key,
    tag_keys,
)
from smartdoc.domain.library_filter import AUTHORS, COLLECTIONS, FORMATS, TAGS, LibraryFilter, value_key
from smartdoc.domain.smart_collections import VirtualCollection

logger = logging.getLogger(__name__)

# The built-in reading list the library's ★ button files documents into.
READING_LIST_ID = "reading-list"
READING_LIST_NAME = "Sẽ đọc"

# split_author_names (imported above) stays importable from this module: older callers use that path.


def _mb_has_author(author: str | None, key: str) -> int:
    return 1 if key in author_keys(author) else 0


def _mb_has_tag(tags: str | None, key: str) -> int:
    return 1 if key in tag_keys(tags) else 0


_SANITIZE_RE = re.compile(r"[^\w\sÀ-ỹ]", re.UNICODE)
# The omnibar's own placeholder text advertises "author:nam python" as valid
# search syntax -- this is real FTS5 syntax (a column-filtered MATCH term)
# and SQLite genuinely supports it natively, but _sanitize_query used to
# strip the ':' as an unsafe character before the query ever reached FTS5,
# silently turning it into a query that could never match anything. Only a
# fixed whitelist of real documents_fts column names is accepted as a
# prefix -- anything else falls back to being sanitized as a plain term,
# so this can't be used to smuggle arbitrary syntax into the MATCH expression.
_SEARCH_FIELD_RE = re.compile(r"^(title|author|tags|content):(.+)$", re.IGNORECASE | re.UNICODE)

_SCHEMA = """
CREATE TABLE IF NOT EXISTS documents (
    doc_rowid INTEGER PRIMARY KEY AUTOINCREMENT,
    id TEXT UNIQUE NOT NULL,
    title TEXT NOT NULL DEFAULT '',
    author TEXT NOT NULL DEFAULT '',
    file_path TEXT NOT NULL,
    file_size INTEGER NOT NULL DEFAULT 0,
    extension TEXT NOT NULL DEFAULT '',
    tags TEXT NOT NULL DEFAULT '',
    content TEXT NOT NULL DEFAULT '',
    cover_path TEXT,
    ai_summary TEXT,
    content_hash TEXT,
    created_at REAL NOT NULL,
    updated_at REAL,
    avg_rating REAL,
    review_count INTEGER NOT NULL DEFAULT 0
);

CREATE VIRTUAL TABLE IF NOT EXISTS documents_fts USING fts5(
    title, author, tags, content,
    content='documents',
    content_rowid='doc_rowid'
);

CREATE TRIGGER IF NOT EXISTS documents_ai AFTER INSERT ON documents BEGIN
    INSERT INTO documents_fts(rowid, title, author, tags, content)
    VALUES (new.doc_rowid, new.title, new.author, new.tags, new.content);
END;

CREATE TRIGGER IF NOT EXISTS documents_ad AFTER DELETE ON documents BEGIN
    INSERT INTO documents_fts(documents_fts, rowid, title, author, tags, content)
    VALUES ('delete', old.doc_rowid, old.title, old.author, old.tags, old.content);
END;

CREATE TRIGGER IF NOT EXISTS documents_au AFTER UPDATE ON documents BEGIN
    INSERT INTO documents_fts(documents_fts, rowid, title, author, tags, content)
    VALUES ('delete', old.doc_rowid, old.title, old.author, old.tags, old.content);
    INSERT INTO documents_fts(rowid, title, author, tags, content)
    VALUES (new.doc_rowid, new.title, new.author, new.tags, new.content);
END;

CREATE TABLE IF NOT EXISTS collections (
    id TEXT PRIMARY KEY,
    name TEXT NOT NULL,
    rules_json TEXT NOT NULL,
    logic TEXT NOT NULL DEFAULT 'AND',
    created_at REAL NOT NULL
);

-- Manual collection membership, independent of a collection's Smart Rules
-- (TDD-009) -- a document can be filtered into a collection by rule, added
-- to it by hand, or both; see VirtualCollection usage in library_view.py.
CREATE TABLE IF NOT EXISTS collection_documents (
    collection_id TEXT NOT NULL,
    doc_id TEXT NOT NULL,
    PRIMARY KEY (collection_id, doc_id)
);

-- User-made groups inside the sidebar's facet tree (e.g. a "Văn học Nga"
-- group holding several authors). Purely organisational: they don't
-- change any document, they just nest facet values under a folder.
-- category is one of FACET_CATEGORIES. A value belongs to at most one
-- group within its category, hence the (category, value) key.
CREATE TABLE IF NOT EXISTS facet_groups (
    id TEXT PRIMARY KEY,
    category TEXT NOT NULL,
    name TEXT NOT NULL,
    created_at REAL NOT NULL
);

CREATE TABLE IF NOT EXISTS facet_group_members (
    category TEXT NOT NULL,
    value TEXT NOT NULL,
    group_id TEXT NOT NULL,
    PRIMARY KEY (category, value)
);

-- What the smart classifier (application/smart_classifier.py) decided for a
-- document. category_id is NULL when it looked and had no confident answer --
-- remembered so the next run doesn't redo that work (until the model changes).
-- applied_tag is the hashtag this run *added* to the document (NULL if the
-- document already had it or nothing was added): it is what "Hoàn tác" (undo)
-- removes again, and what tells a tag the machine wrote apart from one the
-- user chose (train.py must not treat the former as ground truth).
CREATE TABLE IF NOT EXISTS smart_classification (
    doc_id TEXT PRIMARY KEY,
    category_id TEXT,
    confidence REAL NOT NULL DEFAULT 0,
    model_version TEXT NOT NULL DEFAULT '',
    classified_at REAL NOT NULL,
    applied_tag TEXT,
    run_id TEXT NOT NULL DEFAULT ''
);
CREATE INDEX IF NOT EXISTS idx_smart_classification_run ON smart_classification(run_id);

-- One row per field changed by a metadata update (application/metadata_applier.py):
-- what it was, what it became and where the new value came from. A run_id groups
-- the rows of one "Áp dụng" click, which is what "Hoàn tác" (undo) takes back.
-- written_to_file / backup_path say whether the update was also written into the
-- book file itself and where the pre-write copy of the file is kept.
CREATE TABLE IF NOT EXISTS metadata_history (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    doc_id TEXT NOT NULL,
    run_id TEXT NOT NULL,
    field TEXT NOT NULL,
    old_value TEXT,
    new_value TEXT,
    source TEXT NOT NULL DEFAULT '',
    confidence REAL,
    applied_at REAL NOT NULL,
    written_to_file INTEGER NOT NULL DEFAULT 0,
    backup_path TEXT,
    undone_at REAL
);
CREATE INDEX IF NOT EXISTS idx_metadata_history_run ON metadata_history(run_id);
CREATE INDEX IF NOT EXISTS idx_metadata_history_doc ON metadata_history(doc_id);
"""

FACET_CATEGORIES = ("extension", "author", "tag")


def parse_locked_fields(value: str | None) -> set[str]:
    """The `locked_fields` column (a JSON list) as a set; anything unreadable is empty."""
    try:
        parsed = json.loads(value) if value else []
    except ValueError:
        return set()
    return {field for field in parsed if isinstance(field, str)} if isinstance(parsed, list) else set()


class DatabaseManager:
    def __init__(self, db_path: str = "library.db") -> None:
        self.db_path = db_path
        self.write_lock = threading.Lock()
        self.connection = sqlite3.connect(db_path, check_same_thread=False)
        self.connection.row_factory = sqlite3.Row
        self.connection.execute("PRAGMA journal_mode=WAL;")
        self.connection.execute("PRAGMA foreign_keys=ON;")
        # Person/tag matching that SQLite's own LIKE can't do: it only folds
        # ASCII case ("NHÃ CA" != "Nhã Ca") and can't split co-author lists.
        self.connection.create_function("mb_has_author", 2, _mb_has_author, deterministic=True)
        self.connection.create_function("mb_has_tag", 2, _mb_has_tag, deterministic=True)

    def initialize_tables(self) -> None:
        with self.write_lock:
            self.connection.executescript(_SCHEMA)
            self.connection.commit()
            self._migrate_add_missing_columns()

    def _migrate_add_missing_columns(self) -> None:
        """`CREATE TABLE IF NOT EXISTS` does nothing for a table that
        already exists under an older schema version -- a library.db from
        before a column was added won't have it until this runs once."""
        existing_columns = {row["name"] for row in self.connection.execute("PRAGMA table_info(documents)")}
        migrations = {
            "content_hash": "ALTER TABLE documents ADD COLUMN content_hash TEXT",
            "updated_at": "ALTER TABLE documents ADD COLUMN updated_at REAL",
            "avg_rating": "ALTER TABLE documents ADD COLUMN avg_rating REAL",
            "review_count": "ALTER TABLE documents ADD COLUMN review_count INTEGER NOT NULL DEFAULT 0",
            # Metadata lookup (docs/METADATA_LOOKUP_SPEC.md): identity that survives a
            # metadata write, the bibliographic fields, and the fields the user typed
            # by hand (never overwritten by a suggestion).
            "fingerprint": "ALTER TABLE documents ADD COLUMN fingerprint TEXT",
            "publisher": "ALTER TABLE documents ADD COLUMN publisher TEXT",
            "pub_year": "ALTER TABLE documents ADD COLUMN pub_year INTEGER",
            "language": "ALTER TABLE documents ADD COLUMN language TEXT",
            "isbn": "ALTER TABLE documents ADD COLUMN isbn TEXT",
            "series": "ALTER TABLE documents ADD COLUMN series TEXT",
            "description": "ALTER TABLE documents ADD COLUMN description TEXT",
            "locked_fields": "ALTER TABLE documents ADD COLUMN locked_fields TEXT",
            # NULL = not counted yet, 0 = counted and unknown (see infrastructure/page_count.py).
            "page_count": "ALTER TABLE documents ADD COLUMN page_count INTEGER",
        }
        ran_any = False
        for column, statement in migrations.items():
            if column not in existing_columns:
                self.connection.execute(statement)
                ran_any = True
        self.connection.execute("CREATE INDEX IF NOT EXISTS idx_documents_fingerprint ON documents(fingerprint)")
        self.connection.execute("CREATE INDEX IF NOT EXISTS idx_documents_isbn ON documents(isbn)")
        if ran_any:
            self.connection.commit()

    def add_or_update_document(self, doc_id: str, metadata: dict[str, Any], extracted_text: str = "") -> None:
        tags = metadata.get("tags", "")
        if isinstance(tags, (list, tuple)):
            tags = ",".join(tags)
        # updated_at is always "now" at write time -- on a first insert
        # that makes it equal to created_at (both "now"), which is exactly
        # right; on a re-index of an existing file it advances while
        # created_at (not in the UPDATE SET list below) stays put.
        now = time.time()
        params = (
            doc_id,
            metadata.get("title", ""),
            metadata.get("author", ""),
            metadata.get("file_path", ""),
            metadata.get("file_size", 0),
            metadata.get("extension", ""),
            tags,
            extracted_text,
            metadata.get("cover_path"),
            metadata.get("content_hash"),
            metadata.get("created_at", 0.0),
            now,
            metadata.get("fingerprint"),
            metadata.get("page_count"),
        )
        with self.write_lock:
            try:
                self.connection.execute(
                    """
                    INSERT INTO documents
                        (id, title, author, file_path, file_size, extension, tags, content, cover_path, content_hash, created_at, updated_at, fingerprint, page_count)
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                    ON CONFLICT(id) DO UPDATE SET
                        title=excluded.title,
                        author=excluded.author,
                        file_path=excluded.file_path,
                        file_size=excluded.file_size,
                        extension=excluded.extension,
                        tags=excluded.tags,
                        content=excluded.content,
                        cover_path=excluded.cover_path,
                        content_hash=excluded.content_hash,
                        updated_at=excluded.updated_at,
                        fingerprint=COALESCE(excluded.fingerprint, documents.fingerprint),
                        page_count=COALESCE(excluded.page_count, documents.page_count)
                    """,
                    params,
                )
                self.connection.commit()
            except sqlite3.OperationalError:
                logger.exception("Failed to write document %s (db locked?)", doc_id)
                raise

    def set_page_count(self, doc_id: str, page_count: int) -> None:
        """Stores a counted page total (0 = looked at, unknown). Deliberately leaves
        updated_at alone: counting pages is not an edit of the book."""
        with self.write_lock:
            self.connection.execute("UPDATE documents SET page_count = ? WHERE id = ?", (page_count, doc_id))
            self.connection.commit()

    _EDITABLE_FIELDS = ("title", "author", "tags")

    def update_document_fields(self, doc_id: str, fields: dict[str, Any]) -> None:
        self.bulk_update_documents([doc_id], fields)

    def bulk_update_documents(self, doc_ids: list[str], fields: dict[str, Any]) -> None:
        """Used by both the single-document editor (TDD-020) and the batch
        editor (TDD-023): only fields explicitly present in `fields` are
        overwritten, so callers omit whatever the user didn't check/edit.
        All rows are written under one commit rather than one per row.
        """
        set_fields = {k: v for k, v in fields.items() if k in self._EDITABLE_FIELDS}
        if not set_fields or not doc_ids:
            return
        set_fields["updated_at"] = time.time()  # this is a genuine user edit, unlike update_rating_stats
        set_clause = ", ".join(f"{col} = ?" for col in set_fields)
        values = tuple(set_fields.values())
        with self.write_lock:
            for doc_id in doc_ids:
                self.connection.execute(f"UPDATE documents SET {set_clause} WHERE id = ?", (*values, doc_id))
            self.connection.commit()

    # -- Metadata lookup: fingerprint, history, locked fields --------------

    # What a metadata update may change. `tags` and the cover have their own flows.
    METADATA_FIELDS = ("title", "author", "publisher", "pub_year", "language", "isbn", "series", "description")

    def set_fingerprint(self, doc_id: str, fingerprint: str) -> None:
        with self.write_lock:
            self.connection.execute("UPDATE documents SET fingerprint = ? WHERE id = ?", (fingerprint, doc_id))
            self.connection.commit()

    def documents_missing_fingerprint(self, limit: int = 50, after_rowid: int = 0) -> list[dict[str, Any]]:
        """Books without a fingerprint, in stable order; `after_rowid` continues after the last row
        of a previous batch, so a book that was skipped is not offered again in the same pass."""
        rows = self.connection.execute(
            "SELECT doc_rowid, id, file_path, extension FROM documents"
            " WHERE fingerprint IS NULL AND doc_rowid > ? ORDER BY doc_rowid LIMIT ?",
            (after_rowid, limit),
        ).fetchall()
        return [dict(row) for row in rows]

    def find_documents_by_fingerprint(self, fingerprint: str, exclude_id: str = "") -> list[dict[str, Any]]:
        rows = self.connection.execute(
            "SELECT * FROM documents WHERE fingerprint = ? AND id != ?", (fingerprint, exclude_id)
        ).fetchall()
        return [dict(row) for row in rows]

    def find_documents_by_isbn(self, isbn: str, exclude_id: str = "") -> list[dict[str, Any]]:
        rows = self.connection.execute(
            "SELECT * FROM documents WHERE isbn = ? AND id != ?", (isbn, exclude_id)
        ).fetchall()
        return [dict(row) for row in rows]

    def set_file_stats(self, doc_id: str, content_hash: str | None, file_size: int) -> None:
        """After MewBook rewrote the book file: its whole-file hash and size changed."""
        with self.write_lock:
            self.connection.execute(
                "UPDATE documents SET content_hash = ?, file_size = ? WHERE id = ?", (content_hash, file_size, doc_id)
            )
            self.connection.commit()

    def apply_metadata(
        self,
        doc_id: str,
        run_id: str,
        changes: dict[str, Any],
        *,
        source: str = "",
        confidence: float | None = None,
        written_to_file: bool = False,
        backup_path: str | None = None,
    ) -> list[str]:
        """Writes `changes` (only METADATA_FIELDS, only values that differ from
        what is stored) and records each one in metadata_history under `run_id`.
        Returns the fields that actually changed."""
        now = time.time()
        with self.write_lock:
            row = self.connection.execute("SELECT * FROM documents WHERE id = ?", (doc_id,)).fetchone()
            if row is None:
                return []
            changed: list[str] = []
            for field, new_value in changes.items():
                if field not in self.METADATA_FIELDS:
                    continue
                old_value = row[field]
                if str(old_value if old_value is not None else "") == str(new_value if new_value is not None else ""):
                    continue
                self.connection.execute(f"UPDATE documents SET {field} = ? WHERE id = ?", (new_value, doc_id))
                self.connection.execute(
                    "INSERT INTO metadata_history (doc_id, run_id, field, old_value, new_value, source, confidence,"
                    " applied_at, written_to_file, backup_path) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
                    (
                        doc_id,
                        run_id,
                        field,
                        None if old_value is None else str(old_value),
                        None if new_value is None else str(new_value),
                        source,
                        confidence,
                        now,
                        1 if written_to_file else 0,
                        backup_path,
                    ),
                )
                changed.append(field)
            if changed:
                self.connection.execute("UPDATE documents SET updated_at = ? WHERE id = ?", (now, doc_id))
            self.connection.commit()
            return changed

    def metadata_run(self, run_id: str) -> list[dict[str, Any]]:
        rows = self.connection.execute(
            "SELECT * FROM metadata_history WHERE run_id = ? ORDER BY id", (run_id,)
        ).fetchall()
        return [dict(row) for row in rows]

    def latest_metadata_run(self, doc_id: str) -> str | None:
        """The newest run of this document that has not been undone."""
        row = self.connection.execute(
            "SELECT run_id FROM metadata_history WHERE doc_id = ? AND undone_at IS NULL ORDER BY id DESC LIMIT 1",
            (doc_id,),
        ).fetchone()
        return row["run_id"] if row else None

    def undo_metadata_run(self, run_id: str) -> list[dict[str, Any]]:
        """Puts every field of the run back to its old value and marks the run
        undone. Returns the history rows (the caller restores the file from
        `backup_path` when `written_to_file` is set)."""
        now = time.time()
        with self.write_lock:
            rows = [
                dict(row)
                for row in self.connection.execute(
                    "SELECT * FROM metadata_history WHERE run_id = ? AND undone_at IS NULL ORDER BY id", (run_id,)
                )
            ]
            for row in rows:
                old_value = row["old_value"]
                if old_value is None and row["field"] in ("title", "author"):
                    old_value = ""  # these two columns are NOT NULL
                elif old_value is not None and row["field"] == "pub_year":
                    old_value = int(old_value)
                self.connection.execute(f"UPDATE documents SET {row['field']} = ? WHERE id = ?", (old_value, row["doc_id"]))
                self.connection.execute("UPDATE metadata_history SET undone_at = ? WHERE id = ?", (now, row["id"]))
            if rows:
                self.connection.execute("UPDATE documents SET updated_at = ? WHERE id = ?", (now, rows[0]["doc_id"]))
            self.connection.commit()
            return rows

    def locked_fields(self, doc_id: str) -> set[str]:
        row = self.connection.execute("SELECT locked_fields FROM documents WHERE id = ?", (doc_id,)).fetchone()
        return parse_locked_fields(row["locked_fields"] if row else None)

    def lock_fields(self, doc_id: str, fields) -> None:
        """Marks fields the user typed by hand: a suggestion never overwrites them."""
        locked = self.locked_fields(doc_id) | {f for f in fields if f in self.METADATA_FIELDS}
        with self.write_lock:
            self.connection.execute(
                "UPDATE documents SET locked_fields = ? WHERE id = ?", (json.dumps(sorted(locked)), doc_id)
            )
            self.connection.commit()

    # -- Facet groups (sidebar tree folders) -------------------------------

    def create_facet_group(self, category: str, name: str) -> str:
        group_id = uuid.uuid4().hex
        with self.write_lock:
            self.connection.execute(
                "INSERT INTO facet_groups (id, category, name, created_at) VALUES (?, ?, ?, ?)",
                (group_id, category, name.strip(), time.time()),
            )
            self.connection.commit()
        return group_id

    def rename_facet_group(self, group_id: str, name: str) -> None:
        with self.write_lock:
            self.connection.execute("UPDATE facet_groups SET name = ? WHERE id = ?", (name.strip(), group_id))
            self.connection.commit()

    def delete_facet_group(self, group_id: str) -> None:
        """Deletes the folder only -- its members simply become ungrouped
        again; no document is touched."""
        with self.write_lock:
            self.connection.execute("DELETE FROM facet_group_members WHERE group_id = ?", (group_id,))
            self.connection.execute("DELETE FROM facet_groups WHERE id = ?", (group_id,))
            self.connection.commit()

    def list_facet_groups(self, category: str) -> list[dict[str, Any]]:
        """Groups for one category, oldest first, each with a `members`
        list of the facet values filed under it."""
        groups = [
            dict(row)
            for row in self.connection.execute(
                "SELECT * FROM facet_groups WHERE category = ? ORDER BY created_at ASC", (category,)
            )
        ]
        members: dict[str, list[str]] = {}
        for row in self.connection.execute(
            "SELECT group_id, value FROM facet_group_members WHERE category = ?", (category,)
        ):
            members.setdefault(row["group_id"], []).append(row["value"])
        for group in groups:
            group["members"] = sorted(members.get(group["id"], []), key=str.casefold)
        return groups

    def move_facet_value(self, category: str, value: str, group_id: str | None) -> None:
        """Files `value` under `group_id`, or takes it out of any group when
        group_id is None. Moving replaces any previous group."""
        with self.write_lock:
            self.connection.execute(
                "DELETE FROM facet_group_members WHERE category = ? AND value = ?", (category, value)
            )
            if group_id:
                self.connection.execute(
                    "INSERT INTO facet_group_members (category, value, group_id) VALUES (?, ?, ?)",
                    (category, value, group_id),
                )
            self.connection.commit()

    def _rename_facet_member(self, category: str, old_value: str, new_value: str | None) -> None:
        """Keeps group membership following a renamed (or deleted, when
        new_value is None) author/tag instead of stranding the old name."""
        with self.write_lock:
            if new_value:
                taken = self.connection.execute(
                    "SELECT 1 FROM facet_group_members WHERE category = ? AND value = ?", (category, new_value)
                ).fetchone()
                if taken:
                    # Renamed onto a value that's already filed somewhere --
                    # that filing wins; drop the old name's.
                    self.connection.execute(
                        "DELETE FROM facet_group_members WHERE category = ? AND value = ?", (category, old_value)
                    )
                else:
                    self.connection.execute(
                        "UPDATE facet_group_members SET value = ? WHERE category = ? AND value = ?",
                        (new_value, category, old_value),
                    )
            else:
                self.connection.execute(
                    "DELETE FROM facet_group_members WHERE category = ? AND value = ?", (category, old_value)
                )
            self.connection.commit()

    def rename_author(self, old_name: str, new_name: str) -> int:
        """Renames an author across every document carrying it, and returns
        how many rows changed. Used by the sidebar's facet tree, where the
        author list is derived from the documents themselves -- there is no
        separate author table to rename in, so "renaming an author" really
        means rewriting that field on each of their documents."""
        old_name, new_name = old_name.strip(), new_name.strip()
        if not old_name or not new_name or old_name == new_name:
            return 0
        with self.write_lock:
            cursor = self.connection.execute(
                "UPDATE documents SET author = ?, updated_at = ? WHERE author = ?",
                (new_name, time.time(), old_name),
            )
            self.connection.commit()
            changed = cursor.rowcount
        self._rename_facet_member("author", old_name, new_name)
        return changed

    def rename_person(self, old_name: str, new_name: str) -> int:
        """Renames one *person* in every author field that names them, whatever
        the spelling ("NHÃ CA", "nhã ca") and even inside a co-author list
        ("Nhã Ca, X" keeps X). Returns how many documents changed. rename_author
        above only rewrites fields that equal `old_name` exactly."""
        old_name, new_name = old_name.strip(), new_name.strip()
        old_key = normalize_key(old_name)
        if not old_key or not new_name or old_name == new_name:
            return 0
        rows = self.connection.execute("SELECT id, author FROM documents").fetchall()
        now = time.time()
        updates = []
        for row in rows:
            if old_key in author_keys(row["author"]):
                rewritten = rename_person_in_field(row["author"], old_name, new_name)
                if rewritten != row["author"]:
                    updates.append((rewritten, now, row["id"]))
        if updates:
            with self.write_lock:
                self.connection.executemany("UPDATE documents SET author = ?, updated_at = ? WHERE id = ?", updates)
                self.connection.commit()
        self._rename_facet_member("author", old_name, new_name)
        return len(updates)

    def rename_tag(self, old_tag: str, new_tag: str) -> int:
        """Renames one hashtag everywhere it appears. Tags live as a
        comma-joined string per document, so each affected row is rewritten
        element-wise rather than with a blind string replace -- a plain
        REPLACE() would also rewrite tags that merely *contain* the old one
        ("Khoa hoc" inside "Khoa hoc vien tuong")."""
        changed = self._rewrite_tags(old_tag, new_tag)
        self._rename_facet_member("tag", old_tag.strip(), new_tag.strip())
        return changed

    def delete_tag(self, tag: str) -> int:
        """Removes one hashtag from every document carrying it."""
        changed = self._rewrite_tags(tag, None)
        self._rename_facet_member("tag", tag.strip(), None)
        return changed

    def _rewrite_tags(self, old_tag: str, new_tag: str | None) -> int:
        old_tag = old_tag.strip()
        new_tag = new_tag.strip() if new_tag else None
        if not old_tag or old_tag == new_tag:
            return 0

        rows = self.connection.execute("SELECT id, tags FROM documents WHERE tags != ''").fetchall()
        updates: list[tuple[str, float, str]] = []
        now = time.time()
        for row in rows:
            tags = [t.strip() for t in row["tags"].split(",")]
            if old_tag not in tags:
                continue
            rewritten: list[str] = []
            for tag in tags:
                if tag != old_tag:
                    if tag:
                        rewritten.append(tag)
                elif new_tag and new_tag not in rewritten:
                    rewritten.append(new_tag)
            updates.append((", ".join(rewritten), now, row["id"]))

        if not updates:
            return 0
        with self.write_lock:
            self.connection.executemany(
                "UPDATE documents SET tags = ?, updated_at = ? WHERE id = ?", updates
            )
            self.connection.commit()
        return len(updates)

    def update_ai_summary(self, doc_id: str, summary: str) -> None:
        """Persists a generated AI summary (application/ai_summary.py) --
        generation and saving are deliberately separate steps (see
        presentation/ai_summary_dialog.py), so nothing calls this until the
        user has reviewed the text and chosen to keep it."""
        with self.write_lock:
            self.connection.execute(
                "UPDATE documents SET ai_summary = ?, updated_at = ? WHERE id = ?",
                (summary, time.time(), doc_id),
            )
            self.connection.commit()

    def update_document_cover(self, doc_id: str, cover_path: str) -> None:
        """Used by the Cover Image Search feature to replace a document's
        cover after the user picks a candidate -- separate from
        update_document_fields since cover_path isn't a user-editable text
        field (see _EDITABLE_FIELDS) and this is not a metadata edit."""
        with self.write_lock:
            self.connection.execute(
                "UPDATE documents SET cover_path = ?, updated_at = ? WHERE id = ?",
                (cover_path, time.time(), doc_id),
            )
            self.connection.commit()

    def update_rating_stats(self, doc_id: str, avg_rating: float | None, review_count: int) -> None:
        """Caches Supabase-side review aggregates locally so the list view's
        rating/review-count columns and the "highest rated" sort can read
        them instantly without a network round trip on every render. Does
        NOT touch updated_at -- refreshing cached community rating stats
        isn't a user edit to the document's own metadata.
        """
        with self.write_lock:
            self.connection.execute(
                "UPDATE documents SET avg_rating = ?, review_count = ? WHERE id = ?",
                (avg_rating, review_count, doc_id),
            )
            self.connection.commit()

    def delete_document(self, doc_id: str) -> None:
        with self.write_lock:
            self.connection.execute("DELETE FROM documents WHERE id = ?", (doc_id,))
            self.connection.execute("DELETE FROM collection_documents WHERE doc_id = ?", (doc_id,))
            self.connection.execute("DELETE FROM smart_classification WHERE doc_id = ?", (doc_id,))
            self.connection.execute("DELETE FROM metadata_history WHERE doc_id = ?", (doc_id,))
            self.connection.commit()

    def get_document(self, doc_id: str) -> dict[str, Any] | None:
        """Fetch a single document by ID, or None if it no longer exists."""
        row = self.connection.execute(
            "SELECT * FROM documents WHERE id = ?", (doc_id,)
        ).fetchone()
        return dict(row) if row else None

    @staticmethod
    def _sanitize_query(keyword: str) -> str:
        """Strip FTS5 syntax characters and turn each token into a prefix
        match -- except a "field:term" token (field one of
        title/author/tags/content), which becomes a column-filtered prefix
        match instead of a plain keyword search across every column."""
        tokens: list[str] = []
        for raw_token in keyword.split():
            field_match = _SEARCH_FIELD_RE.match(raw_token)
            if field_match:
                field = field_match.group(1).lower()
                words = _SANITIZE_RE.sub(" ", field_match.group(2)).split()
                if words:
                    # Only the first word is column-filtered -- "author:jane
                    # doe" typed with a space is two separate raw tokens
                    # already, so this only affects "author:jane" glued
                    # to extra text with no space, which is an edge case
                    # either way.
                    tokens.append(f"{field}:{words[0]}*")
                    tokens.extend(f"{w}*" for w in words[1:])
                continue
            words = _SANITIZE_RE.sub(" ", raw_token).split()
            tokens.extend(f"{w}*" for w in words)
        return " ".join(tokens)

    def search(self, query_string: str) -> list[dict[str, Any]]:
        match_expr = self._sanitize_query(query_string)
        if not match_expr:
            return []
        sql = """
            SELECT documents.*
            FROM documents_fts
            JOIN documents ON documents.doc_rowid = documents_fts.rowid
            WHERE documents_fts MATCH ?
            ORDER BY rank
        """
        try:
            cursor = self.connection.execute(sql, (match_expr,))
            return [dict(row) for row in cursor.fetchall()]
        except sqlite3.OperationalError:
            logger.error("FTS MATCH syntax error for query %r (sanitized: %r)", query_string, match_expr)
            return []

    def list_all_documents(self, limit: int = 1000, offset: int = 0) -> list[dict[str, Any]]:
        """Browse the library without a search query (e.g. initial UI load)."""
        cursor = self.connection.execute(
            "SELECT * FROM documents ORDER BY created_at DESC LIMIT ? OFFSET ?",
            (limit, offset),
        )
        return [dict(row) for row in cursor.fetchall()]

    def count_documents(self) -> int:
        return self.connection.execute("SELECT COUNT(*) FROM documents").fetchone()[0]

    def list_document_ids(self) -> list[str]:
        return [row["id"] for row in self.connection.execute("SELECT id FROM documents")]

    # Everything the duplicate finder shows or compares -- deliberately *not*
    # `content`, the full extracted text of each book: SELECT * pulled every
    # book's whole text into memory just to compare titles, which on a large
    # library is hundreds of MB for nothing.
    _DEDUP_COLUMNS = "id, title, author, file_path, extension, file_size, content_hash, created_at, cover_path"

    def list_documents_for_dedup(self) -> list[dict[str, Any]]:
        cursor = self.connection.execute(f"SELECT {self._DEDUP_COLUMNS} FROM documents ORDER BY created_at DESC")
        return [dict(row) for row in cursor.fetchall()]

    def find_duplicate_groups_by_content_hash(self) -> list[list[dict[str, Any]]]:
        """TDD-021 exact-duplicate detection: documents whose file bytes hash
        identically (see infrastructure/file_hash.py), grouped together.
        Files imported before content_hash existed have a NULL hash and are
        correctly excluded rather than lumped into one giant "NULL" group.
        """
        rows = self.connection.execute(
            f"""
            SELECT {self._DEDUP_COLUMNS} FROM documents
            WHERE content_hash IS NOT NULL AND content_hash IN (
                SELECT content_hash FROM documents
                WHERE content_hash IS NOT NULL
                GROUP BY content_hash HAVING COUNT(*) > 1
            )
            ORDER BY content_hash, created_at
            """
        ).fetchall()
        groups: dict[str, list[dict]] = {}
        for row in rows:
            doc = dict(row)
            groups.setdefault(doc["content_hash"], []).append(doc)
        return list(groups.values())

    def query_documents(
        self,
        fts_query: str = "",
        where_sql: str = "",
        params: tuple = (),
        limit: int = 1000,
        offset: int = 0,
        order_by: str | None = None,
    ) -> list[dict[str, Any]]:
        """General-purpose read path: an optional FTS text query combined
        with an optional parameterized WHERE clause (facet filters, virtual
        collection rules). `where_sql` must only ever be built from trusted
        fixed fragments with `?` placeholders -- never from raw user text --
        exactly like Smart Rules (TDD-009) and the facet panel (TDD-012) do.
        `order_by` is the same kind of trusted fragment (e.g. "documents.title
        ASC") -- it is spliced directly into the SQL, so it must come from a
        fixed whitelist (see library_view.SORT_OPTIONS), never raw user text.
        Left as None, it defaults to relevance rank for an FTS query or
        newest-first otherwise.

        When `fts_query` is also given, `where_sql` joins against
        `documents_fts` too, and title/author/tags/content exist as column
        names on *both* tables -- an unqualified `author = ?` is an
        "ambiguous column name" error from SQLite in that case. Callers must
        qualify those four columns as `documents.<col>` in `where_sql`
        (`extension`, `file_size`, etc. are only on `documents` and don't
        need it, but qualifying everything is the simpler habit).
        """
        match_expr = self._sanitize_query(fts_query) if fts_query else ""
        try:
            if match_expr:
                extra = f"AND ({where_sql})" if where_sql else ""
                order_clause = order_by or "rank"
                sql = f"""
                    SELECT documents.*
                    FROM documents_fts
                    JOIN documents ON documents.doc_rowid = documents_fts.rowid
                    WHERE documents_fts MATCH ? {extra}
                    ORDER BY {order_clause}
                    LIMIT ? OFFSET ?
                """
                query_params = (match_expr, *params, limit, offset)
            else:
                extra = f"WHERE {where_sql}" if where_sql else ""
                order_clause = order_by or "created_at DESC"
                sql = f"""
                    SELECT * FROM documents
                    {extra}
                    ORDER BY {order_clause}
                    LIMIT ? OFFSET ?
                """
                query_params = (*params, limit, offset)
            cursor = self.connection.execute(sql, query_params)
            return [dict(row) for row in cursor.fetchall()]
        except sqlite3.OperationalError:
            logger.error("query_documents failed (fts=%r, where=%r, order_by=%r)", fts_query, where_sql, order_by)
            return []

    def count_documents_matching(self, fts_query: str = "", where_sql: str = "", params: tuple = ()) -> int:
        """Same filters as query_documents, but a COUNT(*) -- used to compute
        page counts for pagination without fetching every row."""
        match_expr = self._sanitize_query(fts_query) if fts_query else ""
        try:
            if match_expr:
                extra = f"AND ({where_sql})" if where_sql else ""
                sql = f"""
                    SELECT COUNT(*)
                    FROM documents_fts
                    JOIN documents ON documents.doc_rowid = documents_fts.rowid
                    WHERE documents_fts MATCH ? {extra}
                """
                query_params = (match_expr, *params)
            else:
                extra = f"WHERE {where_sql}" if where_sql else ""
                sql = f"SELECT COUNT(*) FROM documents {extra}"
                query_params = tuple(params)
            return self.connection.execute(sql, query_params).fetchone()[0]
        except sqlite3.OperationalError:
            logger.error("count_documents_matching failed (fts=%r, where=%r)", fts_query, where_sql)
            return 0

    def list_document_ids_matching(self, fts_query: str = "", where_sql: str = "", params: tuple = ()) -> list[str]:
        """Every id matching the same filters as query_documents -- no paging.
        "Apply to the current list" (smart classification) means the whole
        filtered result, not just the page on screen."""
        match_expr = self._sanitize_query(fts_query) if fts_query else ""
        try:
            if match_expr:
                extra = f"AND ({where_sql})" if where_sql else ""
                sql = f"""
                    SELECT documents.id
                    FROM documents_fts
                    JOIN documents ON documents.doc_rowid = documents_fts.rowid
                    WHERE documents_fts MATCH ? {extra}
                """
                query_params: tuple = (match_expr, *params)
            else:
                extra = f"WHERE {where_sql}" if where_sql else ""
                sql = f"SELECT id FROM documents {extra} ORDER BY created_at DESC"
                query_params = tuple(params)
            return [row[0] for row in self.connection.execute(sql, query_params)]
        except sqlite3.OperationalError:
            logger.error("list_document_ids_matching failed (fts=%r, where=%r)", fts_query, where_sql)
            return []

    _LIGHT_COLUMNS = "id, title, author, tags, file_path, extension"

    def get_documents_light(self, doc_ids: list[str]) -> list[dict[str, Any]]:
        """Just the columns the classifier needs -- never `content`, the full
        extracted text, which for a big library is hundreds of MB."""
        rows: list[dict[str, Any]] = []
        for start in range(0, len(doc_ids), 500):  # stay well under SQLite's bound-variable limit
            chunk = doc_ids[start : start + 500]
            placeholders = ",".join("?" for _ in chunk)
            cursor = self.connection.execute(
                f"SELECT {self._LIGHT_COLUMNS} FROM documents WHERE id IN ({placeholders})", tuple(chunk)
            )
            rows.extend(dict(row) for row in cursor.fetchall())
        return rows

    # -- Smart classification (application/smart_classifier.py) ---------------

    def smart_classification_records(self, doc_ids: list[str]) -> dict[str, dict[str, Any]]:
        """doc_id -> its smart_classification row, for the ids that have one."""
        found: dict[str, dict[str, Any]] = {}
        for start in range(0, len(doc_ids), 500):
            chunk = doc_ids[start : start + 500]
            placeholders = ",".join("?" for _ in chunk)
            for row in self.connection.execute(
                f"SELECT * FROM smart_classification WHERE doc_id IN ({placeholders})", tuple(chunk)
            ):
                found[row["doc_id"]] = dict(row)
        return found

    def apply_smart_classifications(self, run_id: str, model_version: str, items: list[dict[str, Any]]) -> dict[str, int]:
        """Records the classifier's decisions in one transaction.

        Each item: doc_id, category_id (None = no confident answer),
        confidence, and -- when a category was chosen -- tag (the hashtag to
        add) and group (the sidebar folder to file that hashtag under).

        Only ever *adds*: the tag is appended to the document's existing tags
        (never replacing them), and a hashtag the user has already filed into
        some folder stays where they put it. The folder is created on first
        use, or re-used if one with that name exists. The one exception is an
        item's `replace_tag` -- the hashtag an *earlier classification run*
        added, which is swapped for the new one so a re-run doesn't leave two
        categories on a book. Returns counts: tagged, already_tagged, unknown,
        missing (documents deleted meanwhile).
        """
        stats = {"tagged": 0, "already_tagged": 0, "unknown": 0, "missing": 0}
        now = time.time()
        with self.write_lock:
            groups = {
                row["name"].casefold(): row["id"]
                for row in self.connection.execute("SELECT id, name FROM facet_groups WHERE category = 'tag'")
            }
            filed = {
                row["value"] for row in self.connection.execute("SELECT value FROM facet_group_members WHERE category = 'tag'")
            }
            for item in items:
                doc_id, tag = item["doc_id"], item.get("tag")
                row = self.connection.execute("SELECT tags FROM documents WHERE id = ?", (doc_id,)).fetchone()
                if row is None:
                    stats["missing"] += 1
                    continue
                applied: str | None = None
                if tag:
                    current = [t.strip() for t in (row["tags"] or "").split(",") if t.strip()]
                    replaced = item.get("replace_tag")
                    if replaced and replaced.casefold() != tag.casefold():
                        current = [t for t in current if t.casefold() != replaced.casefold()]
                    if tag.casefold() in {t.casefold() for t in current}:
                        stats["already_tagged"] += 1
                    else:
                        current.append(tag)
                        applied = tag
                        stats["tagged"] += 1
                    if applied or (replaced and replaced.casefold() != tag.casefold()):
                        self.connection.execute(
                            "UPDATE documents SET tags = ?, updated_at = ? WHERE id = ?", (", ".join(current), now, doc_id)
                        )
                    group_name = item.get("group")
                    if group_name and tag not in filed:
                        group_id = groups.get(group_name.casefold())
                        if group_id is None:
                            group_id = uuid.uuid4().hex
                            self.connection.execute(
                                "INSERT INTO facet_groups (id, category, name, created_at) VALUES (?, 'tag', ?, ?)",
                                (group_id, group_name, now),
                            )
                            groups[group_name.casefold()] = group_id
                        self.connection.execute(
                            "INSERT OR IGNORE INTO facet_group_members (category, value, group_id) VALUES ('tag', ?, ?)",
                            (tag, group_id),
                        )
                        filed.add(tag)
                else:
                    stats["unknown"] += 1
                self.connection.execute(
                    """
                    INSERT INTO smart_classification (doc_id, category_id, confidence, model_version, classified_at, applied_tag, run_id)
                    VALUES (?, ?, ?, ?, ?, ?, ?)
                    ON CONFLICT(doc_id) DO UPDATE SET
                        category_id=excluded.category_id, confidence=excluded.confidence,
                        model_version=excluded.model_version, classified_at=excluded.classified_at,
                        applied_tag=excluded.applied_tag, run_id=excluded.run_id
                    """,
                    (doc_id, item.get("category_id"), float(item.get("confidence") or 0.0), model_version, now, applied, run_id),
                )
            self.connection.commit()
        return stats

    def undo_smart_classification(self, run_id: str) -> int:
        """Takes back one classification run: removes the hashtags it added
        (only those -- tags that were already on a document, or that the user
        added since, are left alone) and forgets its records. The sidebar
        folders it created stay (they are harmless and may hold other
        hashtags). Returns how many documents lost a tag."""
        changed = 0
        now = time.time()
        with self.write_lock:
            rows = self.connection.execute(
                "SELECT doc_id, applied_tag FROM smart_classification WHERE run_id = ? AND applied_tag IS NOT NULL", (run_id,)
            ).fetchall()
            for row in rows:
                doc = self.connection.execute("SELECT tags FROM documents WHERE id = ?", (row["doc_id"],)).fetchone()
                if doc is None:
                    continue
                current = [t.strip() for t in (doc["tags"] or "").split(",") if t.strip()]
                remaining = [t for t in current if t.casefold() != row["applied_tag"].casefold()]
                if len(remaining) != len(current):
                    self.connection.execute(
                        "UPDATE documents SET tags = ?, updated_at = ? WHERE id = ?", (", ".join(remaining), now, row["doc_id"])
                    )
                    changed += 1
            self.connection.execute("DELETE FROM smart_classification WHERE run_id = ?", (run_id,))
            self.connection.commit()
        return changed

    def count_by_extension(self) -> dict[str, int]:
        rows = self.connection.execute(
            "SELECT extension, COUNT(*) AS n FROM documents GROUP BY extension ORDER BY n DESC"
        ).fetchall()
        return {row["extension"]: row["n"] for row in rows}

    def count_by_author(self) -> dict[str, int]:
        rows = self.connection.execute(
            "SELECT author, COUNT(*) AS n FROM documents GROUP BY author ORDER BY n DESC"
        ).fetchall()
        return {row["author"]: row["n"] for row in rows}

    def count_by_tag(self) -> dict[str, int]:
        """Distinct hashtags across the library, with live counts. Tags are
        stored as one comma-joined string per document (see
        add_or_update_document), so this splits and aggregates in Python --
        SQLite has no built-in way to explode a delimited column into rows.
        """
        counts: dict[str, int] = {}
        rows = self.connection.execute("SELECT tags FROM documents WHERE tags != ''").fetchall()
        for row in rows:
            for tag in row["tags"].split(","):
                tag = tag.strip()
                if tag:
                    counts[tag] = counts.get(tag, 0) + 1
        return dict(sorted(counts.items(), key=lambda kv: kv[1], reverse=True))

    def save_collection(self, collection_id: str, name: str, rules_json: str, logic: str, created_at: float) -> None:
        with self.write_lock:
            self.connection.execute(
                """
                INSERT INTO collections (id, name, rules_json, logic, created_at)
                VALUES (?, ?, ?, ?, ?)
                ON CONFLICT(id) DO UPDATE SET name=excluded.name, rules_json=excluded.rules_json, logic=excluded.logic
                """,
                (collection_id, name, rules_json, logic, created_at),
            )
            self.connection.commit()

    def list_collections(self) -> list[dict[str, Any]]:
        cursor = self.connection.execute("SELECT * FROM collections ORDER BY created_at ASC")
        return [dict(row) for row in cursor.fetchall()]

    def get_collection(self, collection_id: str) -> dict[str, Any] | None:
        row = self.connection.execute("SELECT * FROM collections WHERE id = ?", (collection_id,)).fetchone()
        return dict(row) if row else None

    def delete_collection(self, collection_id: str) -> None:
        with self.write_lock:
            self.connection.execute("DELETE FROM collections WHERE id = ?", (collection_id,))
            self.connection.execute("DELETE FROM collection_documents WHERE collection_id = ?", (collection_id,))
            self.connection.commit()

    def rename_collection(self, collection_id: str, new_name: str) -> None:
        with self.write_lock:
            self.connection.execute("UPDATE collections SET name = ? WHERE id = ?", (new_name, collection_id))
            self.connection.commit()

    def add_documents_to_collection(self, collection_id: str, doc_ids: list[str]) -> None:
        if not doc_ids:
            return
        with self.write_lock:
            self.connection.executemany(
                "INSERT OR IGNORE INTO collection_documents (collection_id, doc_id) VALUES (?, ?)",
                [(collection_id, doc_id) for doc_id in doc_ids],
            )
            self.connection.commit()

    def remove_documents_from_collection(self, collection_id: str, doc_ids: list[str]) -> None:
        if not doc_ids:
            return
        with self.write_lock:
            self.connection.executemany(
                "DELETE FROM collection_documents WHERE collection_id = ? AND doc_id = ?",
                [(collection_id, doc_id) for doc_id in doc_ids],
            )
            self.connection.commit()

    def ensure_reading_list(self) -> str:
        """Creates the built-in "Sẽ đọc" collection on first use and returns
        its id. It has a fixed id (READING_LIST_ID) rather than being looked
        up by name, so a user renaming it -- or creating an unrelated
        collection that happens to also be called "Sẽ đọc" -- can't make
        the star button start filing books somewhere else."""
        if self.get_collection(READING_LIST_ID) is None:
            collection = VirtualCollection(name=READING_LIST_NAME, id=READING_LIST_ID)
            self.save_collection(
                collection.id, collection.name, collection.to_json(), collection.logic, collection.created_at
            )
        return READING_LIST_ID

    def reading_list_ids(self) -> set[str]:
        """One query for the whole set, so the library view can mark every
        starred row on a page without a lookup per row."""
        return set(self.list_collection_document_ids(READING_LIST_ID))

    def toggle_reading_list(self, doc_id: str) -> bool:
        """Stars/unstars one document. Returns the new state (True = now in
        the reading list)."""
        self.ensure_reading_list()
        if doc_id in self.reading_list_ids():
            self.remove_documents_from_collection(READING_LIST_ID, [doc_id])
            return False
        self.add_documents_to_collection(READING_LIST_ID, [doc_id])
        return True

    def list_collection_document_ids(self, collection_id: str) -> list[str]:
        rows = self.connection.execute(
            "SELECT doc_id FROM collection_documents WHERE collection_id = ?", (collection_id,)
        ).fetchall()
        return [row["doc_id"] for row in rows]

    def collection_where_fragment(self, collection_id: str) -> tuple[str, tuple]:
        """(sql_fragment, params) for "is this document in this Virtual
        Collection" -- (rule match) OR (manually added). "1=0" (matches
        nothing) if the collection has neither a rule nor any manual
        member -- an empty collection must show zero documents, not
        silently fall back to "no filter at all". Shared by the library
        view's filtering (library_view.py) and the status bar's
        per-collection count (count_documents_in_collection, below) so the
        two never drift apart on what "in this collection" means.
        """
        row = self.get_collection(collection_id)
        manual_ids = self.list_collection_document_ids(collection_id)
        parts: list[str] = []
        params: list = []
        if row:
            collection = VirtualCollection.from_row(row)
            if collection.rules:
                rule_sql, rule_params = collection.to_sql_where_clause()
                parts.append(f"({rule_sql})")
                params.extend(rule_params)
        if manual_ids:
            placeholders = ",".join("?" for _ in manual_ids)
            parts.append(f"documents.id IN ({placeholders})")
            params.extend(manual_ids)
        if not parts:
            return "1=0", ()
        return "(" + " OR ".join(parts) + ")", tuple(params)

    def collections_where_fragment(self, collection_ids) -> tuple[str, tuple]:
        """Union of several collections: a document in *any* of them."""
        parts: list[str] = []
        params: list = []
        for collection_id in collection_ids:
            sql, collection_params = self.collection_where_fragment(collection_id)
            parts.append(sql)
            params.extend(collection_params)
        if not parts:
            return "1=0", ()
        return "(" + " OR ".join(parts) + ")", tuple(params)

    def filter_where(self, flt: LibraryFilter, exclude: tuple[str, ...] = ()) -> tuple[str, tuple]:
        """The WHERE fragment for a LibraryFilter's sidebar groups: OR within a
        group, AND between groups. (The text query is not part of it -- it goes
        to FTS separately, see query_documents.) `exclude` leaves whole groups
        out, which is how a facet count answers "what if I picked this
        instead?" without its own group narrowing the options."""
        fragments: list[str] = []
        params: list = []

        if flt.formats and FORMATS not in exclude:
            keys = [value_key(FORMATS, ext) for ext in flt.formats]
            fragments.append(f"documents.extension IN ({','.join('?' for _ in keys)})")
            params.extend(keys)

        if flt.authors and AUTHORS not in exclude:
            fragments.append("(" + " OR ".join("mb_has_author(documents.author, ?)" for _ in flt.authors) + ")")
            params.extend(author_key(name) for name in flt.authors)

        if flt.tags and TAGS not in exclude:
            fragments.append("(" + " OR ".join("mb_has_tag(documents.tags, ?)" for _ in flt.tags) + ")")
            params.extend(tag_key(tag) for tag in flt.tags)

        if flt.collections and COLLECTIONS not in exclude:
            collection_sql, collection_params = self.collections_where_fragment(flt.collections)
            fragments.append(collection_sql)
            params.extend(collection_params)

        return " AND ".join(fragments), tuple(params)

    def list_facet_rows(self) -> list[tuple[str, str, str, str]]:
        """(id, author, tags, extension) of every document -- just the columns
        the sidebar counts are built from, never the extracted text."""
        rows = self.connection.execute("SELECT id, author, tags, extension FROM documents").fetchall()
        return [(row["id"], row["author"] or "", row["tags"] or "", row["extension"] or "") for row in rows]

    def count_documents_in_collection(self, collection_id: str) -> int:
        where_sql, params = self.collection_where_fragment(collection_id)
        return self.count_documents_matching(where_sql=where_sql, params=params)

    def count_metadata_completeness(self) -> tuple[int, int]:
        """Returns (complete_count, incomplete_count). "Incomplete" means
        the extractor couldn't fill in a real title/author, or there's no
        cover -- tags are deliberately excluded, since nothing in this app
        ever fills tags in automatically, so an empty tags field isn't a
        sign anything went wrong.
        """
        total = self.count_documents()
        incomplete = self.connection.execute(
            "SELECT COUNT(*) FROM documents "
            "WHERE title = '' OR author = '' OR author = 'Unknown' OR cover_path IS NULL"
        ).fetchone()[0]
        return total - incomplete, incomplete

    def close(self) -> None:
        # Waits for a write that is running on another thread (e.g. the detail
        # panel's background page counter): closing a sqlite3 connection under a
        # statement that is executing is a hard crash (access violation), not an exception.
        with self.write_lock:
            self.connection.close()


if __name__ == "__main__":
    db = DatabaseManager(":memory:")
    db.initialize_tables()

    db.add_or_update_document(
        "doc1",
        {"title": "Python Co Ban", "author": "Nguyen Nam", "file_path": "a.pdf", "extension": "pdf", "created_at": 0.0},
        extracted_text="Hoc lap trinh Python tu co ban den nang cao",
    )
    db.add_or_update_document(
        "doc2",
        {"title": "Java Nang Cao", "author": "Tran An", "file_path": "b.pdf", "extension": "pdf", "created_at": 0.0},
        extracted_text="Java threading va concurrency",
    )
    db.add_or_update_document(
        "doc3",
        {"title": "Machine Learning", "author": "Le Binh", "file_path": "c.pdf", "extension": "pdf", "created_at": 0.0},
        extracted_text="Python cho khoa hoc du lieu",
    )

    results = db.search("py*")
    print("search('py*') ->", [r["title"] for r in results])
    assert len(results) == 2

    db.delete_document("doc2")
    remaining_titles = {r["title"] for r in db.search("py*")}
    print("after delete doc2, search('py*') ->", remaining_titles)
    assert "Java Nang Cao" not in remaining_titles
