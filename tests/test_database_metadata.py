import sqlite3

from smartdoc.infrastructure.database import DatabaseManager, parse_locked_fields


def _add(db, doc_id="d1", **extra):
    metadata = {"title": "Old Title", "author": "Old Author", "file_path": f"{doc_id}.pdf", "created_at": 1.0}
    metadata.update(extra)
    db.add_or_update_document(doc_id, metadata)


def test_an_old_library_gains_the_new_columns_and_history_table(tmp_path):
    path = str(tmp_path / "old.db")
    old = sqlite3.connect(path)
    old.execute(
        "CREATE TABLE documents (doc_rowid INTEGER PRIMARY KEY AUTOINCREMENT, id TEXT UNIQUE NOT NULL,"
        " title TEXT NOT NULL DEFAULT '', author TEXT NOT NULL DEFAULT '', file_path TEXT NOT NULL,"
        " file_size INTEGER NOT NULL DEFAULT 0, extension TEXT NOT NULL DEFAULT '', tags TEXT NOT NULL DEFAULT '',"
        " content TEXT NOT NULL DEFAULT '', cover_path TEXT, ai_summary TEXT, content_hash TEXT,"
        " created_at REAL NOT NULL, updated_at REAL, avg_rating REAL, review_count INTEGER NOT NULL DEFAULT 0)"
    )
    old.execute("INSERT INTO documents (id, title, file_path, created_at) VALUES ('keep', 'Kept', 'k.pdf', 1.0)")
    old.commit()
    old.close()

    db = DatabaseManager(path)
    db.initialize_tables()

    columns = {row["name"] for row in db.connection.execute("PRAGMA table_info(documents)")}
    assert {"fingerprint", "publisher", "pub_year", "language", "isbn", "series", "description", "locked_fields"} <= columns
    assert db.get_document("keep")["title"] == "Kept"  # existing data untouched
    assert db.metadata_run("nothing") == []  # metadata_history exists
    db.close()


def test_apply_metadata_records_history_and_skips_unchanged_or_foreign_fields(app_context):
    db = app_context.db
    _add(db)

    changed = db.apply_metadata(
        "d1",
        "run1",
        {"title": "New Title", "author": "Old Author", "publisher": "NXB Trẻ", "pub_year": 2020, "file_path": "hack.pdf"},
        source="Open Library",
        confidence=0.93,
    )

    assert changed == ["title", "publisher", "pub_year"]
    doc = db.get_document("d1")
    assert (doc["title"], doc["publisher"], doc["pub_year"], doc["file_path"]) == ("New Title", "NXB Trẻ", 2020, "d1.pdf")
    history = {row["field"]: row for row in db.metadata_run("run1")}
    assert set(history) == {"title", "publisher", "pub_year"}
    assert history["title"]["old_value"] == "Old Title" and history["title"]["new_value"] == "New Title"
    assert history["publisher"]["old_value"] is None
    assert history["title"]["source"] == "Open Library" and history["title"]["confidence"] == 0.93


def test_the_search_index_follows_a_metadata_update(app_context):
    db = app_context.db
    _add(db)
    db.apply_metadata("d1", "run1", {"title": "Gia Định thành thông chí"})
    assert [d["id"] for d in db.search("thông")] == ["d1"]


def test_undo_restores_old_values_once(app_context):
    db = app_context.db
    _add(db, pub_year=None)
    db.apply_metadata("d1", "run1", {"title": "New", "pub_year": 1999, "isbn": "9781234567897"})

    rows = db.undo_metadata_run("run1")

    assert {row["field"] for row in rows} == {"title", "pub_year", "isbn"}
    doc = db.get_document("d1")
    assert (doc["title"], doc["pub_year"], doc["isbn"]) == ("Old Title", None, None)
    assert db.undo_metadata_run("run1") == []  # already undone


def test_latest_run_ignores_undone_runs(app_context):
    db = app_context.db
    _add(db)
    db.apply_metadata("d1", "run1", {"title": "A"})
    db.apply_metadata("d1", "run2", {"title": "B"})
    assert db.latest_metadata_run("d1") == "run2"
    db.undo_metadata_run("run2")
    assert db.latest_metadata_run("d1") == "run1"
    db.undo_metadata_run("run1")
    assert db.latest_metadata_run("d1") is None


def test_locked_fields_accumulate_and_reject_unknown_names(app_context):
    db = app_context.db
    _add(db)
    db.lock_fields("d1", ["title"])
    db.lock_fields("d1", ["author", "file_path", "nonsense"])
    assert db.locked_fields("d1") == {"title", "author"}
    assert parse_locked_fields("not json") == set()
    assert parse_locked_fields('{"a": 1}') == set()
    assert parse_locked_fields(None) == set()


def test_fingerprint_is_stored_kept_on_reindex_and_findable(app_context):
    db = app_context.db
    _add(db, "d1", fingerprint="fp1")
    _add(db, "d2", fingerprint="fp1")
    _add(db, "d3")

    assert [d["id"] for d in db.find_documents_by_fingerprint("fp1", exclude_id="d1")] == ["d2"]
    assert [row["id"] for row in db.documents_missing_fingerprint()] == ["d3"]
    _add(db, "d1")  # re-indexed without a fingerprint: the stored one stays
    assert db.get_document("d1")["fingerprint"] == "fp1"
    db.set_fingerprint("d3", "fp3")
    assert db.documents_missing_fingerprint() == []


def test_find_by_isbn_and_delete_removes_history(app_context):
    db = app_context.db
    _add(db, "d1")
    db.apply_metadata("d1", "run1", {"isbn": "9781234567897"})
    _add(db, "d2")
    assert [d["id"] for d in db.find_documents_by_isbn("9781234567897", exclude_id="d2")] == ["d1"]

    db.delete_document("d1")
    assert db.metadata_run("run1") == []
