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


def _add(app_context, doc_id, title, author="Tác giả", created_at=1.0):
    app_context.db.add_or_update_document(
        doc_id, {"title": title, "author": author, "file_path": f"{doc_id}.pdf", "created_at": created_at}
    )


def test_fuzzy_matching_ignores_vietnamese_diacritics_and_case(app_context):
    _add(app_context, "d1", "Lịch Sử Trung Quốc", "Lâm Hán Đạt")
    _add(app_context, "d2", "lich su trung quoc", "Lam Han Dat")

    groups = DuplicateEngine(app_context).find_fuzzy_duplicates()

    assert [{d["id"] for d in g} for g in groups] == [{"d1", "d2"}]


def test_different_volumes_are_not_flagged_as_duplicates(app_context):
    """"Tập 4" vs "Tập 5" are ~97% similar as strings but are different
    books -- and "select duplicates" would mark one for deletion."""
    _add(app_context, "d1", "Lịch Sử Trung Quốc 5000 Năm Tập 4", "Lâm Hán Đạt")
    _add(app_context, "d2", "Lịch Sử Trung Quốc 5000 Năm Tập 5", "Lâm Hán Đạt")

    assert DuplicateEngine(app_context).find_fuzzy_duplicates() == []


def test_the_same_volume_downloaded_twice_is_still_flagged(app_context):
    _add(app_context, "d1", "Lịch Sử Trung Quốc 5000 Năm Tập 4", "Lâm Hán Đạt")
    _add(app_context, "d2", "Lịch Sử Trung Quốc 5000 Năm Tập 4 (copy)", "Lâm Hán Đạt")

    groups = DuplicateEngine(app_context).find_fuzzy_duplicates()

    assert [{d["id"] for d in g} for g in groups] == [{"d1", "d2"}]


def test_fuzzy_search_reports_progress_and_can_be_cancelled(app_context):
    import pytest

    from smartdoc.application.duplicate_finder import DuplicateSearchCancelled

    for i in range(10):
        _add(app_context, f"d{i}", f"Book number {i}")
    engine = DuplicateEngine(app_context)

    reports = []
    engine.find_fuzzy_duplicates(progress=lambda done, total: reports.append((done, total)))
    assert reports[-1] == (10, 10)

    with pytest.raises(DuplicateSearchCancelled):
        engine.find_fuzzy_duplicates(should_cancel=lambda: True)


def test_fuzzy_search_scales_to_a_large_library(app_context):
    """Regression guard for the hang: the old all-pairs comparison took ~2
    minutes at this size (and ~54 minutes at 15,000 documents)."""
    import random
    import time

    rng = random.Random(3)
    words = "lich su van hoc nga chien tranh hoa binh tri tue nhan tao lap trinh kinh te tam ly toan vat ly".split()
    for i in range(3000):
        title = " ".join(rng.sample(words, 4))
        _add(app_context, f"d{i:05d}", f"{title} {i}", f"Author {i % 50}", float(i))

    started = time.perf_counter()
    DuplicateEngine(app_context).find_fuzzy_duplicates()
    assert time.perf_counter() - started < 5.0


def test_dedup_query_does_not_load_extracted_text(app_context):
    app_context.db.add_or_update_document(
        "d1", {"title": "t", "author": "a", "file_path": "a.pdf", "created_at": 1.0}, extracted_text="x" * 100_000
    )
    row = app_context.db.list_documents_for_dedup()[0]
    assert "content" not in row  # the full text of every book is never needed to compare titles
