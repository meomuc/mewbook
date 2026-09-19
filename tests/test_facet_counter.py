"""FacetCounter (live drill-down counts) and the SQL side of LibraryFilter."""
from smartdoc.domain.author_names import NO_TAG, UNKNOWN_AUTHOR
from smartdoc.domain.library_filter import AUTHORS, FORMATS, TAGS, LibraryFilter
from smartdoc.domain.smart_collections import VirtualCollection


def _add(ctx, doc_id, author="", tags="", ext="pdf", title=None):
    ctx.db.add_or_update_document(
        doc_id,
        {
            "title": title or doc_id,
            "author": author,
            "tags": tags,
            "extension": ext,
            "file_path": f"{doc_id}.{ext}",
            "created_at": 1.0,
        },
    )


def _shown(ctx, flt):
    where_sql, params = ctx.db.filter_where(flt)
    return sorted(
        d["id"] for d in ctx.db.query_documents(fts_query=flt.query, where_sql=where_sql, params=params, limit=1000)
    )


def _counts(ctx, category, flt=None):
    return {c.label: c.count for c in ctx.facets.counts(category, flt or LibraryFilter())}


# -- filter_where ---------------------------------------------------------------------------


def test_author_filter_matches_spelling_variants_and_co_authored_books(app_context):
    _add(app_context, "a", "NHÃ CA")
    _add(app_context, "b", "Nhã Ca")
    _add(app_context, "c", "Trịnh Công Sơn, Nhã Ca")
    _add(app_context, "d", "Nhã Cát")  # a different person whose name starts the same

    assert _shown(app_context, LibraryFilter(authors=("Nhã Ca",))) == ["a", "b", "c"]


def test_tag_filter_matches_a_whole_tag_case_insensitively(app_context):
    _add(app_context, "a", tags="Khoa học")
    _add(app_context, "b", tags="Khoa học viễn tưởng")  # merely starts the same
    _add(app_context, "c", tags="khoa học, AI")

    assert _shown(app_context, LibraryFilter(tags=("Khoa học",))) == ["a", "c"]


def test_the_special_buckets_are_filterable(app_context):
    _add(app_context, "a", "Unknown", tags="")
    _add(app_context, "b", "nhiều tác giả", tags="AI")
    _add(app_context, "c", "Nhã Ca", tags="AI")

    assert _shown(app_context, LibraryFilter(authors=(UNKNOWN_AUTHOR,))) == ["a", "b"]
    assert _shown(app_context, LibraryFilter(tags=(NO_TAG,))) == ["a"]


def test_or_within_a_group_and_and_between_groups(app_context):
    _add(app_context, "a", "A", "AI", "pdf")
    _add(app_context, "b", "B", "AI", "epub")
    _add(app_context, "c", "A", "Thơ", "pdf")

    assert _shown(app_context, LibraryFilter(authors=("A", "B"))) == ["a", "b", "c"]
    assert _shown(app_context, LibraryFilter(authors=("A",), tags=("AI",))) == ["a"]
    assert _shown(app_context, LibraryFilter(authors=("A", "B"), formats=("epub",))) == ["b"]


def test_the_search_text_combines_with_the_filter(app_context):
    _add(app_context, "a", "A", "AI", title="Python cơ bản")
    _add(app_context, "b", "A", "Thơ", title="Python nâng cao")

    assert _shown(app_context, LibraryFilter(query="Python", tags=("AI",))) == ["a"]


def test_a_collection_in_the_filter_restricts_to_its_documents(app_context):
    _add(app_context, "a", "A")
    _add(app_context, "b", "A")
    collection = VirtualCollection(name="Một")
    app_context.db.save_collection(collection.id, collection.name, collection.to_json(), collection.logic, 1.0)
    app_context.db.add_documents_to_collection(collection.id, ["a"])

    assert _shown(app_context, LibraryFilter(collections=(collection.id,))) == ["a"]


def test_excluding_a_group_leaves_its_values_out_of_the_where(app_context):
    _add(app_context, "a", "A", "AI")
    _add(app_context, "b", "B", "AI")
    flt = LibraryFilter(authors=("A",), tags=("AI",))

    where_sql, params = app_context.db.filter_where(flt, exclude=(AUTHORS,))
    ids = sorted(d["id"] for d in app_context.db.query_documents(where_sql=where_sql, params=params))

    assert ids == ["a", "b"]


# -- counts -----------------------------------------------------------------------------------


def test_spelling_variants_are_counted_as_one_person_under_the_commonest_spelling(app_context):
    _add(app_context, "a", "NHÃ CA")
    _add(app_context, "b", "Nhã Ca")
    _add(app_context, "c", "Nhã Ca")

    assert _counts(app_context, AUTHORS) == {"Nhã Ca": 3}


def test_co_authored_books_count_for_every_author(app_context):
    _add(app_context, "a", "Nguyễn A, Trần B")
    _add(app_context, "b", "Trần B")

    assert _counts(app_context, AUTHORS) == {"Trần B": 2, "Nguyễn A": 1}


def test_unknown_authors_and_untagged_books_form_last_buckets(app_context):
    _add(app_context, "a", "Unknown")
    _add(app_context, "b", "nhiều tác giả")
    for i in range(3):
        _add(app_context, f"n{i}", "Nhã Ca", tags="")

    authors = app_context.facets.counts(AUTHORS, LibraryFilter())
    assert [c.label for c in authors] == ["Nhã Ca", "Không rõ / Nhiều tác giả"]
    assert authors[-1].count == 2
    assert app_context.facets.counts(TAGS, LibraryFilter())[-1].label == "Chưa phân loại"


def test_counts_follow_the_other_groups_of_the_filter(app_context):
    """Pick a hashtag and the author list shrinks to authors that have it -- no zero-result clicks."""
    _add(app_context, "a", "Sử gia", "Lịch sử")
    _add(app_context, "b", "Nhà thơ", "Thơ")

    flt = LibraryFilter(tags=("Lịch sử",))

    assert _counts(app_context, AUTHORS, flt) == {"Sử gia": 1}
    assert _counts(app_context, FORMATS, flt) == {"PDF": 1}


def test_a_group_is_counted_without_its_own_selection(app_context):
    """The sibling values of a selected one stay visible so the user can switch."""
    _add(app_context, "a", "A", "AI")
    _add(app_context, "b", "A", "Thơ")

    flt = LibraryFilter(tags=("AI",))

    assert _counts(app_context, TAGS, flt) == {"AI": 1, "Thơ": 1}


def test_a_selected_value_that_matches_nothing_stays_listed_with_zero(app_context):
    _add(app_context, "a", "A", "AI", "pdf")

    flt = LibraryFilter(formats=("epub",), tags=("AI",))

    assert _counts(app_context, TAGS, flt) == {"AI": 0}  # nothing is epub; the selected tag stays so it can be unselected
    assert _counts(app_context, FORMATS, flt) == {"PDF": 1, "EPUB": 0}


def test_counts_respect_the_search_text(app_context):
    _add(app_context, "a", "A", title="Python cơ bản")
    _add(app_context, "b", "B", title="Nấu ăn")

    assert _counts(app_context, AUTHORS, LibraryFilter(query="Python")) == {"A": 1}


def test_collection_counts_follow_the_other_filters(app_context):
    _add(app_context, "a", tags="AI")
    _add(app_context, "b", tags="Thơ")
    collection = VirtualCollection(name="Một")
    app_context.db.save_collection(collection.id, collection.name, collection.to_json(), collection.logic, 1.0)
    app_context.db.add_documents_to_collection(collection.id, ["a", "b"])

    assert app_context.facets.collection_counts(LibraryFilter()) == {collection.id: 2}
    assert app_context.facets.collection_counts(LibraryFilter(tags=("AI",))) == {collection.id: 1}


def test_group_count_is_documents_with_any_member(app_context):
    _add(app_context, "a", "A", "AI")
    _add(app_context, "b", "B", "Thơ")
    _add(app_context, "c", "C", "AI, Thơ")

    assert app_context.facets.group_count(TAGS, ["AI", "Thơ"], LibraryFilter()) == 3
    assert app_context.facets.group_count(TAGS, ["AI"], LibraryFilter(authors=("A", "C"))) == 2


def test_counts_refresh_after_the_library_changes(app_context):
    _add(app_context, "a", "A")
    assert _counts(app_context, AUTHORS) == {"A": 1}

    _add(app_context, "b", "B")
    from smartdoc.core.event_bus import LibraryUpdatedEvent

    app_context.event_bus.publish(LibraryUpdatedEvent())

    assert _counts(app_context, AUTHORS) == {"A": 1, "B": 1}


def test_total_counts_the_whole_filter(app_context):
    _add(app_context, "a", "A", "AI")
    _add(app_context, "b", "B", "AI")

    assert app_context.facets.total(LibraryFilter(tags=("AI",))) == 2
    assert app_context.facets.total(LibraryFilter(tags=("AI",), authors=("A",))) == 1
    assert app_context.facets.library_total() == 2


# -- suggestions --------------------------------------------------------------------------------


def test_suggestions_search_every_group_ignoring_case_and_accents(app_context):
    _add(app_context, "a", "Nhã Ca", "Thơ")
    _add(app_context, "b", "Cổ Long", "Kiếm hiệp")
    collection = VirtualCollection(name="Nhã tuyển")
    app_context.db.save_collection(collection.id, collection.name, collection.to_json(), collection.logic, 1.0)

    found = app_context.facets.suggest("nha", LibraryFilter())

    assert [(s.category, s.label) for s in found] == [("authors", "Nhã Ca"), ("collections", "Nhã tuyển")]
    assert found[0].value == "Nhã Ca"


def test_suggestions_skip_values_already_selected_and_short_input(app_context):
    _add(app_context, "a", "Nhã Ca", "Thơ")

    assert app_context.facets.suggest("n", LibraryFilter()) == []
    assert app_context.facets.suggest("nhã", LibraryFilter(authors=("Nhã Ca",))) == []


def test_suggestions_rank_word_starts_before_middles(app_context):
    _add(app_context, "a", "Bùi Ca")
    _add(app_context, "b", "Cabral")  # "ca" at the start of a word

    labels = [s.label for s in app_context.facets.suggest("ca", LibraryFilter())]

    assert labels == ["Bùi Ca", "Cabral"] or labels == ["Cabral", "Bùi Ca"]
    assert set(labels) == {"Bùi Ca", "Cabral"}


# -- renaming a person -----------------------------------------------------------------------------


def test_renaming_a_person_rewrites_every_spelling_and_keeps_co_authors(app_context):
    _add(app_context, "a", "NHÃ CA")
    _add(app_context, "b", "Nhã Ca, Trịnh Công Sơn")
    _add(app_context, "c", "Nhã Cát")

    changed = app_context.db.rename_person("nhã ca", "Nhã Ca (thơ)")

    assert changed == 2
    assert app_context.db.get_document("a")["author"] == "Nhã Ca (thơ)"
    assert app_context.db.get_document("b")["author"] == "Nhã Ca (thơ), Trịnh Công Sơn"
    assert app_context.db.get_document("c")["author"] == "Nhã Cát"


# -- cleanup suggestions -----------------------------------------------------------------------------------


def test_accent_only_differences_are_suggested_for_merging_not_merged(app_context):
    for i in range(3):
        _add(app_context, f"a{i}", "Nguyễn Nhật Ánh")
    _add(app_context, "b", "Nguyen Nhat Anh")
    _add(app_context, "c", "Người khác")

    found = app_context.facets.cleanup_suggestions()

    assert [(s.kind, s.names) for s in found] == [("merge", (("Nguyễn Nhật Ánh", 3), ("Nguyen Nhat Anh", 1)))]
    assert _counts(app_context, AUTHORS)["Nguyen Nhat Anh"] == 1  # still two entries until the user agrees


def test_case_and_spacing_variants_are_already_merged_so_not_suggested(app_context):
    _add(app_context, "a", "NHÃ CA")
    _add(app_context, "b", "Nhã Ca")

    assert app_context.facets.cleanup_suggestions() == []


def test_a_username_used_as_author_of_many_books_is_flagged(app_context):
    for i in range(12):
        _add(app_context, f"u{i}", "CongThuc88")
    _add(app_context, "x", "Sachvui88")  # too few books to bother
    _add(app_context, "y", "Osho")

    found = app_context.facets.cleanup_suggestions()

    assert [(s.kind, s.names[0][0], s.books) for s in found] == [("uploader", "CongThuc88", 12)]
