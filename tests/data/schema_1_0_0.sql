-- Frozen copy of the library.db schema as MewBook 1.0.0 leaves it (PRAGMA user_version = 0).
-- Generated once from DatabaseManager.initialize_tables() before any versioned migration existed. NEVER edit it:
-- tests/test_schema_migrations.py loads it to prove an old library upgrades in place.

CREATE TABLE collection_documents (
    collection_id TEXT NOT NULL,
    doc_id TEXT NOT NULL,
    PRIMARY KEY (collection_id, doc_id)
);

CREATE TABLE collections (
    id TEXT PRIMARY KEY,
    name TEXT NOT NULL,
    rules_json TEXT NOT NULL,
    logic TEXT NOT NULL DEFAULT 'AND',
    created_at REAL NOT NULL
);

CREATE TABLE documents (
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
, fingerprint TEXT, publisher TEXT, pub_year INTEGER, language TEXT, isbn TEXT, series TEXT, description TEXT, locked_fields TEXT, page_count INTEGER);

CREATE VIRTUAL TABLE documents_fts USING fts5(
    title, author, tags, content,
    content='documents',
    content_rowid='doc_rowid'
);

CREATE TABLE facet_group_members (
    category TEXT NOT NULL,
    value TEXT NOT NULL,
    group_id TEXT NOT NULL,
    PRIMARY KEY (category, value)
);

CREATE TABLE facet_groups (
    id TEXT PRIMARY KEY,
    category TEXT NOT NULL,
    name TEXT NOT NULL,
    created_at REAL NOT NULL
);

CREATE TABLE metadata_history (
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

CREATE TABLE smart_classification (
    doc_id TEXT PRIMARY KEY,
    category_id TEXT,
    confidence REAL NOT NULL DEFAULT 0,
    model_version TEXT NOT NULL DEFAULT '',
    classified_at REAL NOT NULL,
    applied_tag TEXT,
    run_id TEXT NOT NULL DEFAULT ''
);

CREATE INDEX idx_documents_fingerprint ON documents(fingerprint);

CREATE INDEX idx_documents_isbn ON documents(isbn);

CREATE INDEX idx_metadata_history_doc ON metadata_history(doc_id);

CREATE INDEX idx_metadata_history_run ON metadata_history(run_id);

CREATE INDEX idx_smart_classification_run ON smart_classification(run_id);

CREATE TRIGGER documents_ad AFTER DELETE ON documents BEGIN
    INSERT INTO documents_fts(documents_fts, rowid, title, author, tags, content)
    VALUES ('delete', old.doc_rowid, old.title, old.author, old.tags, old.content);
END;

CREATE TRIGGER documents_ai AFTER INSERT ON documents BEGIN
    INSERT INTO documents_fts(rowid, title, author, tags, content)
    VALUES (new.doc_rowid, new.title, new.author, new.tags, new.content);
END;

CREATE TRIGGER documents_au AFTER UPDATE ON documents BEGIN
    INSERT INTO documents_fts(documents_fts, rowid, title, author, tags, content)
    VALUES ('delete', old.doc_rowid, old.title, old.author, old.tags, old.content);
    INSERT INTO documents_fts(rowid, title, author, tags, content)
    VALUES (new.doc_rowid, new.title, new.author, new.tags, new.content);
END;
