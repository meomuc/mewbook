import pytest

from smartdoc.infrastructure.database import DatabaseManager


@pytest.fixture
def db():
    manager = DatabaseManager(":memory:")
    manager.initialize_tables()
    yield manager
    manager.close()


def _seed(db: DatabaseManager):
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


def test_search_prefix_match_finds_python_docs(db):
    _seed(db)
    results = db.search("py")
    titles = {r["title"] for r in results}
    assert titles == {"Python Co Ban", "Machine Learning"}


def test_search_matches_author(db):
    _seed(db)
    results = db.search("Nguyen")
    assert [r["id"] for r in results] == ["doc1"]


def test_update_document_fields_changes_only_given_fields(db):
    _seed(db)
    db.update_document_fields("doc1", {"author": "New Author"})
    docs = db.list_all_documents()
    doc1 = next(d for d in docs if d["id"] == "doc1")
    assert doc1["author"] == "New Author"
    assert doc1["title"] == "Python Co Ban"  # untouched


def test_update_document_fields_resyncs_fts(db):
    db.add_or_update_document(
        "docX",
        {"title": "Xyzzyx Original Title", "author": "A", "file_path": "x.pdf", "created_at": 0.0},
        extracted_text="unrelated body text",
    )
    assert db.search("Xyzzyx") and db.search("Xyzzyx")[0]["id"] == "docX"

    db.update_document_fields("docX", {"title": "Renamed Title"})

    assert db.search("Renamed") and db.search("Renamed")[0]["id"] == "docX"
    assert db.search("Xyzzyx") == []


def test_update_document_fields_ignores_unknown_columns(db):
    _seed(db)
    db.update_document_fields("doc1", {"file_path": "/etc/passwd", "author": "Safe Author"})
    doc1 = next(d for d in db.list_all_documents() if d["id"] == "doc1")
    assert doc1["file_path"] == "a.pdf"  # not editable, unchanged
    assert doc1["author"] == "Safe Author"


def test_bulk_update_documents_applies_to_all_given_ids(db):
    _seed(db)
    db.bulk_update_documents(["doc1", "doc2"], {"tags": "reviewed"})
    docs = {d["id"]: d for d in db.list_all_documents()}
    assert docs["doc1"]["tags"] == "reviewed"
    assert docs["doc2"]["tags"] == "reviewed"
    assert docs["doc3"]["tags"] == ""  # not in the batch


def test_bulk_update_documents_with_no_fields_is_a_noop(db):
    _seed(db)
    before = db.list_all_documents()
    db.bulk_update_documents(["doc1"], {})
    assert db.list_all_documents() == before


def test_delete_document_removes_from_fts(db):
    _seed(db)
    db.delete_document("doc2")
    results = db.search("java")
    assert results == []


def test_add_or_update_document_upserts_by_id(db):
    _seed(db)
    db.add_or_update_document(
        "doc1",
        {"title": "Python Nang Cao", "author": "Nguyen Nam", "file_path": "a.pdf", "extension": "pdf", "created_at": 0.0},
        extracted_text="noi dung moi",
    )
    results = db.search("nang")
    titles = {r["title"] for r in results}
    assert "Python Nang Cao" in titles
    assert "Python Co Ban" not in titles


def test_search_sanitizes_fts_special_characters(db):
    _seed(db)
    # A naive query containing FTS syntax characters must not raise.
    results = db.search('python" OR 1=1 --')
    assert isinstance(results, list)


def test_search_empty_query_returns_empty_list(db):
    _seed(db)
    assert db.search("   ") == []


def test_list_all_documents_returns_everything_newest_first(db):
    db.add_or_update_document(
        "doc1", {"title": "First", "author": "A", "file_path": "a.pdf", "created_at": 1.0}
    )
    db.add_or_update_document(
        "doc2", {"title": "Second", "author": "B", "file_path": "b.pdf", "created_at": 2.0}
    )
    results = db.list_all_documents()
    assert [r["title"] for r in results] == ["Second", "First"]


def test_list_all_documents_respects_limit_and_offset(db):
    _seed(db)
    page1 = db.list_all_documents(limit=2, offset=0)
    page2 = db.list_all_documents(limit=2, offset=2)
    assert len(page1) == 2
    assert len(page2) == 1
    assert db.count_documents() == 3


def _seed_with_extensions(db: DatabaseManager):
    db.add_or_update_document(
        "d1", {"title": "PDF Book", "author": "A", "file_path": "a.pdf", "extension": "pdf", "created_at": 1.0}
    )
    db.add_or_update_document(
        "d2", {"title": "Epub Book", "author": "B", "file_path": "b.epub", "extension": "epub", "created_at": 2.0}
    )
    db.add_or_update_document(
        "d3", {"title": "Another PDF", "author": "A", "file_path": "c.pdf", "extension": "pdf", "created_at": 3.0}
    )


def test_count_by_extension(db):
    _seed_with_extensions(db)
    assert db.count_by_extension() == {"pdf": 2, "epub": 1}


def test_count_by_author(db):
    _seed_with_extensions(db)
    assert db.count_by_author() == {"A": 2, "B": 1}


def test_count_by_tag_splits_comma_joined_tags(db):
    db.add_or_update_document(
        "d1", {"title": "A", "author": "X", "file_path": "a.pdf", "tags": "Python,AI", "created_at": 1.0}
    )
    db.add_or_update_document(
        "d2", {"title": "B", "author": "Y", "file_path": "b.pdf", "tags": "Python", "created_at": 2.0}
    )
    db.add_or_update_document("d3", {"title": "C", "author": "Z", "file_path": "c.pdf", "created_at": 3.0})

    assert db.count_by_tag() == {"Python": 2, "AI": 1}


def test_count_by_tag_ignores_whitespace_around_tags(db):
    db.add_or_update_document(
        "d1", {"title": "A", "author": "X", "file_path": "a.pdf", "tags": " Python , AI ", "created_at": 1.0}
    )
    assert db.count_by_tag() == {"Python": 1, "AI": 1}


def test_query_documents_with_where_only(db):
    _seed_with_extensions(db)
    results = db.query_documents(where_sql="extension = ?", params=("epub",))
    assert [r["id"] for r in results] == ["d2"]


def test_query_documents_with_fts_and_where_combined(db):
    _seed_with_extensions(db)
    results = db.query_documents(fts_query="pdf", where_sql="documents.author = ?", params=("A",))
    assert {r["id"] for r in results} == {"d1", "d3"}


def test_query_documents_ambiguous_unqualified_column_fails_safely(db):
    # Documents that this behavior is real, not just "works if you're careful":
    # an unqualified column shared with documents_fts must not silently
    # return wrong results when combined with an FTS query -- it should
    # fail (and query_documents degrades to an empty list rather than
    # raising) so the bug is loud during development, not returning
    # plausible-looking wrong data.
    _seed_with_extensions(db)
    results = db.query_documents(fts_query="pdf", where_sql="author = ?", params=("A",))
    assert results == []


def test_query_documents_no_filters_returns_everything(db):
    _seed_with_extensions(db)
    results = db.query_documents()
    assert len(results) == 3


def test_query_documents_custom_order_by_title(db):
    _seed_with_extensions(db)
    results = db.query_documents(order_by="documents.title ASC")
    assert [r["title"] for r in results] == ["Another PDF", "Epub Book", "PDF Book"]


def test_query_documents_custom_order_by_with_fts_query(db):
    _seed_with_extensions(db)
    results = db.query_documents(fts_query="pdf", order_by="documents.title ASC")
    assert [r["title"] for r in results] == ["Another PDF", "PDF Book"]


def test_count_documents_matching_no_filters(db):
    _seed_with_extensions(db)
    assert db.count_documents_matching() == 3


def test_count_documents_matching_where_only(db):
    _seed_with_extensions(db)
    assert db.count_documents_matching(where_sql="extension = ?", params=("pdf",)) == 2


def test_count_documents_matching_fts_and_where_combined(db):
    _seed_with_extensions(db)
    assert db.count_documents_matching(fts_query="pdf", where_sql="documents.author = ?", params=("A",)) == 2


def test_add_or_update_document_sets_updated_at_equal_to_created_at_on_insert(db):
    db.add_or_update_document("d1", {"title": "A", "author": "X", "file_path": "a.pdf", "created_at": 100.0})
    doc = db.list_all_documents()[0]
    assert doc["updated_at"] is not None
    assert doc["updated_at"] >= doc["created_at"]  # written "now", not backdated


def test_add_or_update_document_on_reindex_advances_updated_at_but_not_created_at(db):
    db.add_or_update_document("d1", {"title": "A", "author": "X", "file_path": "a.pdf", "created_at": 100.0})
    first = db.list_all_documents()[0]

    db.add_or_update_document("d1", {"title": "A v2", "author": "X", "file_path": "a.pdf", "created_at": 999.0})
    second = db.list_all_documents()[0]

    assert second["created_at"] == 100.0  # original "date added" preserved
    assert second["updated_at"] >= first["updated_at"]


def test_bulk_update_documents_bumps_updated_at(db):
    db.add_or_update_document("d1", {"title": "A", "author": "X", "file_path": "a.pdf", "created_at": 0.0})
    before = db.list_all_documents()[0]["updated_at"]

    db.bulk_update_documents(["d1"], {"author": "New Author"})

    after = db.list_all_documents()[0]["updated_at"]
    assert after >= before


def test_update_rating_stats_does_not_touch_updated_at(db):
    db.add_or_update_document("d1", {"title": "A", "author": "X", "file_path": "a.pdf", "created_at": 0.0})
    before = db.list_all_documents()[0]["updated_at"]

    db.update_rating_stats("d1", 4.5, 10)

    doc = db.list_all_documents()[0]
    assert doc["avg_rating"] == 4.5
    assert doc["review_count"] == 10
    assert doc["updated_at"] == before


def test_new_documents_have_null_rating_and_zero_review_count(db):
    db.add_or_update_document("d1", {"title": "A", "author": "X", "file_path": "a.pdf", "created_at": 0.0})
    doc = db.list_all_documents()[0]
    assert doc["avg_rating"] is None
    assert doc["review_count"] == 0


def test_list_document_ids(db):
    db.add_or_update_document("d1", {"title": "A", "author": "X", "file_path": "a.pdf", "created_at": 0.0})
    db.add_or_update_document("d2", {"title": "B", "author": "Y", "file_path": "b.pdf", "created_at": 0.0})
    assert set(db.list_document_ids()) == {"d1", "d2"}


def test_migration_adds_content_hash_column_to_pre_existing_db(tmp_path):
    db_path = str(tmp_path / "old.db")
    old_db = DatabaseManager(db_path)
    # Simulate a library.db created before content_hash existed: build the
    # table by hand without that column, the way the old _SCHEMA used to.
    old_db.connection.execute(
        """
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
            created_at REAL NOT NULL
        )
        """
    )
    old_db.connection.commit()
    old_db.close()

    migrated_db = DatabaseManager(db_path)
    migrated_db.initialize_tables()  # must not raise despite the table already existing
    migrated_db.add_or_update_document(
        "d1", {"title": "T", "author": "A", "file_path": "a.pdf", "content_hash": "abc123", "created_at": 1.0}
    )
    assert migrated_db.list_all_documents()[0]["content_hash"] == "abc123"
    migrated_db.close()


def test_find_duplicate_groups_by_content_hash(db):
    db.add_or_update_document(
        "d1", {"title": "Copy A", "author": "X", "file_path": "a.pdf", "content_hash": "hash1", "created_at": 1.0}
    )
    db.add_or_update_document(
        "d2", {"title": "Copy B", "author": "X", "file_path": "b.pdf", "content_hash": "hash1", "created_at": 2.0}
    )
    db.add_or_update_document(
        "d3", {"title": "Unique", "author": "Y", "file_path": "c.pdf", "content_hash": "hash2", "created_at": 3.0}
    )
    db.add_or_update_document(
        "d4", {"title": "No hash yet", "author": "Z", "file_path": "d.pdf", "created_at": 4.0}
    )

    groups = db.find_duplicate_groups_by_content_hash()
    assert len(groups) == 1
    assert {d["id"] for d in groups[0]} == {"d1", "d2"}


def test_collection_crud(db):
    assert db.list_collections() == []

    db.save_collection("c1", "Sach AI moi", '[{"field": "tags", "operator": "contains", "value": "AI"}]', "AND", 1.0)
    collections = db.list_collections()
    assert len(collections) == 1
    assert collections[0]["name"] == "Sach AI moi"

    fetched = db.get_collection("c1")
    assert fetched is not None
    assert fetched["logic"] == "AND"

    db.delete_collection("c1")
    assert db.get_collection("c1") is None


def test_rename_collection(db):
    db.save_collection("c1", "Old Name", "[]", "AND", 1.0)
    db.rename_collection("c1", "New Name")
    assert db.get_collection("c1")["name"] == "New Name"


def test_manual_collection_membership(db):
    _seed(db)
    db.save_collection("c1", "Yêu thích", "[]", "AND", 1.0)

    db.add_documents_to_collection("c1", ["doc1", "doc2"])
    assert set(db.list_collection_document_ids("c1")) == {"doc1", "doc2"}

    db.remove_documents_from_collection("c1", ["doc1"])
    assert db.list_collection_document_ids("c1") == ["doc2"]


def test_adding_same_document_to_collection_twice_is_idempotent(db):
    _seed(db)
    db.save_collection("c1", "Yêu thích", "[]", "AND", 1.0)
    db.add_documents_to_collection("c1", ["doc1"])
    db.add_documents_to_collection("c1", ["doc1"])
    assert db.list_collection_document_ids("c1") == ["doc1"]


def test_deleting_collection_clears_its_membership(db):
    _seed(db)
    db.save_collection("c1", "Yêu thích", "[]", "AND", 1.0)
    db.add_documents_to_collection("c1", ["doc1"])
    db.delete_collection("c1")
    assert db.list_collection_document_ids("c1") == []


def test_deleting_document_clears_its_collection_membership(db):
    _seed(db)
    db.save_collection("c1", "Yêu thích", "[]", "AND", 1.0)
    db.add_documents_to_collection("c1", ["doc1"])
    db.delete_document("doc1")
    assert db.list_collection_document_ids("c1") == []


def test_count_documents_in_collection_combines_rule_and_manual_membership(db):
    _seed_with_extensions(db)  # d1/d3 pdf, d2 epub
    db.save_collection(
        "c1",
        "PDFs plus one epub",
        '{"rules": [{"field": "extension", "operator": "eq", "value": "pdf"}]}',
        "AND",
        1.0,
    )
    db.add_documents_to_collection("c1", ["d2"])  # manually add the epub too

    assert db.count_documents_in_collection("c1") == 3


def test_count_documents_in_collection_empty_collection_is_zero(db):
    _seed(db)
    db.save_collection("c1", "Empty", '{"rules": []}', "AND", 1.0)
    assert db.count_documents_in_collection("c1") == 0


def test_count_metadata_completeness(db):
    db.add_or_update_document(
        "complete",
        {
            "title": "Full Book",
            "author": "Real Author",
            "file_path": "a.pdf",
            "cover_path": "/covers/a.webp",
            "created_at": 1.0,
        },
    )
    db.add_or_update_document(
        "no_author", {"title": "Some Book", "author": "Unknown", "file_path": "b.pdf", "created_at": 1.0}
    )
    db.add_or_update_document(
        "no_cover", {"title": "Another Book", "author": "Real Author", "file_path": "c.pdf", "created_at": 1.0}
    )

    complete, incomplete = db.count_metadata_completeness()

    assert complete == 1
    assert incomplete == 2
