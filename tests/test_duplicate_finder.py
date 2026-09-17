from smartdoc.application.duplicate_finder import DuplicateEngine


def test_find_exact_duplicates_groups_by_content_hash(app_context):
    app_context.db.add_or_update_document(
        "d1", {"title": "A", "author": "X", "file_path": "a.pdf", "content_hash": "h1", "created_at": 1.0}
    )
    app_context.db.add_or_update_document(
        "d2", {"title": "A copy", "author": "X", "file_path": "a2.pdf", "content_hash": "h1", "created_at": 2.0}
    )
    app_context.db.add_or_update_document(
        "d3", {"title": "B", "author": "Y", "file_path": "b.pdf", "content_hash": "h2", "created_at": 3.0}
    )

    engine = DuplicateEngine(app_context)
    groups = engine.find_exact_duplicates()

    assert len(groups) == 1
    assert {d["id"] for d in groups[0]} == {"d1", "d2"}


def test_find_fuzzy_duplicates_groups_near_identical_titles(app_context):
    app_context.db.add_or_update_document(
        "d1", {"title": "Python Co Ban", "author": "Nguyen Van A", "file_path": "a.pdf", "created_at": 1.0}
    )
    app_context.db.add_or_update_document(
        "d2", {"title": "Python Co Ban ", "author": "Nguyen Van A", "file_path": "a2.pdf", "created_at": 2.0}
    )
    app_context.db.add_or_update_document(
        "d3", {"title": "Machine Learning Nang Cao", "author": "Someone Else", "file_path": "b.pdf", "created_at": 3.0}
    )

    engine = DuplicateEngine(app_context)
    groups = engine.find_fuzzy_duplicates(threshold=0.9)

    assert len(groups) == 1
    assert {d["id"] for d in groups[0]} == {"d1", "d2"}


def test_find_fuzzy_duplicates_respects_threshold(app_context):
    app_context.db.add_or_update_document(
        "d1", {"title": "Python Co Ban", "author": "A", "file_path": "a.pdf", "created_at": 1.0}
    )
    app_context.db.add_or_update_document(
        "d2", {"title": "Java Nang Cao", "author": "B", "file_path": "b.pdf", "created_at": 2.0}
    )

    engine = DuplicateEngine(app_context)
    assert engine.find_fuzzy_duplicates(threshold=0.95) == []


def test_find_fuzzy_duplicates_skips_documents_with_empty_title_and_author(app_context):
    app_context.db.add_or_update_document("d1", {"title": "", "author": "", "file_path": "a.pdf", "created_at": 1.0})
    app_context.db.add_or_update_document("d2", {"title": "", "author": "", "file_path": "b.pdf", "created_at": 2.0})

    engine = DuplicateEngine(app_context)
    assert engine.find_fuzzy_duplicates() == []


def test_no_duplicates_returns_empty_lists(app_context):
    app_context.db.add_or_update_document(
        "d1", {"title": "Unique One", "author": "A", "file_path": "a.pdf", "content_hash": "h1", "created_at": 1.0}
    )
    engine = DuplicateEngine(app_context)
    assert engine.find_exact_duplicates() == []
    assert engine.find_fuzzy_duplicates() == []
