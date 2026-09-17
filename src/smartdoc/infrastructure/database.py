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

import logging
import re
import sqlite3
import threading
import time
from typing import Any

logger = logging.getLogger(__name__)

_SANITIZE_RE = re.compile(r"[^\w\sÀ-ỹ]", re.UNICODE)

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
"""


class DatabaseManager:
    def __init__(self, db_path: str = "library.db") -> None:
        self.db_path = db_path
        self.write_lock = threading.Lock()
        self.connection = sqlite3.connect(db_path, check_same_thread=False)
        self.connection.row_factory = sqlite3.Row
        self.connection.execute("PRAGMA journal_mode=WAL;")
        self.connection.execute("PRAGMA foreign_keys=ON;")

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
        }
        ran_any = False
        for column, statement in migrations.items():
            if column not in existing_columns:
                self.connection.execute(statement)
                ran_any = True
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
        )
        with self.write_lock:
            try:
                self.connection.execute(
                    """
                    INSERT INTO documents
                        (id, title, author, file_path, file_size, extension, tags, content, cover_path, content_hash, created_at, updated_at)
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
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
                        updated_at=excluded.updated_at
                    """,
                    params,
                )
                self.connection.commit()
            except sqlite3.OperationalError:
                logger.exception("Failed to write document %s (db locked?)", doc_id)
                raise

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
            self.connection.commit()

    def get_document(self, doc_id: str) -> dict[str, Any] | None:
        """Fetch a single document by ID, or None if it no longer exists."""
        row = self.connection.execute(
            "SELECT * FROM documents WHERE id = ?", (doc_id,)
        ).fetchone()
        return dict(row) if row else None

    @staticmethod
    def _sanitize_query(keyword: str) -> str:
        """Strip FTS5 syntax characters and turn each token into a prefix match."""
        cleaned = _SANITIZE_RE.sub(" ", keyword)
        tokens = [t for t in cleaned.split() if t]
        return " ".join(f"{t}*" for t in tokens)

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

    def find_duplicate_groups_by_content_hash(self) -> list[list[dict[str, Any]]]:
        """TDD-021 exact-duplicate detection: documents whose file bytes hash
        identically (see infrastructure/file_hash.py), grouped together.
        Files imported before content_hash existed have a NULL hash and are
        correctly excluded rather than lumped into one giant "NULL" group.
        """
        rows = self.connection.execute(
            """
            SELECT * FROM documents
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

    def list_collection_document_ids(self, collection_id: str) -> list[str]:
        rows = self.connection.execute(
            "SELECT doc_id FROM collection_documents WHERE collection_id = ?", (collection_id,)
        ).fetchall()
        return [row["doc_id"] for row in rows]

    def close(self) -> None:
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
