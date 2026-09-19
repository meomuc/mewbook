"""The library view reads its filter from FilterService, whoever changed it."""
from smartdoc.domain.library_filter import AUTHORS, FORMATS, TAGS, LibraryFilter
from smartdoc.domain.smart_collections import SmartRule, VirtualCollection
from smartdoc.presentation.library_view import PAGE_SIZE, LibraryListWidget


def _add(ctx, doc_id, author="A", tags="", ext="pdf", title=None):
    ctx.db.add_or_update_document(
        doc_id,
        {
            "title": title or doc_id,
            "author": author,
            "tags": tags,
            "extension": ext,
            "file_path": f"{doc_id}.{ext}",
            "created_at": float(len(doc_id)),
        },
    )


def _shown(widget):
    return sorted(widget.model.document_at(r)["id"] for r in range(widget.model.rowCount()))


def test_a_filter_change_reloads_the_list_and_clearing_restores_it(qapp, app_context):
    _add(app_context, "d1", tags="Thơ")
    _add(app_context, "d2", tags="AI")
    widget = LibraryListWidget(app_context)
    assert _shown(widget) == ["d1", "d2"]

    app_context.filters.select(TAGS, "thơ")  # spelling does not matter
    assert _shown(widget) == ["d1"]

    app_context.filters.clear()
    assert _shown(widget) == ["d1", "d2"]


def test_every_part_of_the_filter_applies_together(qapp, app_context):
    _add(app_context, "d1", "Nhã Ca", "Thơ", "epub", title="Python thơ")
    _add(app_context, "d2", "Nhã Ca", "Thơ", "pdf", title="Python thơ")
    _add(app_context, "d3", "Cổ Long", "Thơ", "epub", title="Python thơ")
    _add(app_context, "d4", "Nhã Ca", "AI", "epub", title="Python thơ")
    widget = LibraryListWidget(app_context)

    app_context.filters.set(
        LibraryFilter(query="Python", authors=("NHÃ CA",), tags=("Thơ",), formats=("epub",))
    )

    assert _shown(widget) == ["d1"]


def test_a_new_filter_goes_back_to_the_first_page(qapp, app_context):
    for i in range(PAGE_SIZE + 5):
        _add(app_context, f"d{i:04d}", tags="Nhiều")
    widget = LibraryListWidget(app_context)
    widget._current_page = 1
    widget.reload()

    app_context.filters.select(TAGS, "Nhiều")

    assert widget._current_page == 0


def test_co_authored_books_are_found_from_either_author(qapp, app_context):
    _add(app_context, "d1", "Nguyễn A, Trần B")
    _add(app_context, "d2", "Trần B")
    _add(app_context, "d3", "Người khác")
    widget = LibraryListWidget(app_context)

    app_context.filters.select(AUTHORS, "Trần B")

    assert _shown(widget) == ["d1", "d2"]


def test_a_collection_and_a_hashtag_narrow_each_other(qapp, app_context):
    _add(app_context, "d1", tags="AI")
    _add(app_context, "d2", tags="Thơ")
    collection = VirtualCollection(name="Sách hay", rules=[SmartRule(field="extension", operator="eq", value="pdf")])
    app_context.db.save_collection(collection.id, collection.name, collection.to_json(), collection.logic, 1.0)
    widget = LibraryListWidget(app_context)

    app_context.filters.set(LibraryFilter(collections=(collection.id,), tags=("AI",)))

    assert _shown(widget) == ["d1"]


def test_the_classification_scope_matches_the_list_on_screen(qapp, app_context):
    _add(app_context, "d1", "Nhã Ca", "Thơ")
    _add(app_context, "d2", "Cổ Long", "Thơ")
    widget = LibraryListWidget(app_context)
    app_context.filters.set(LibraryFilter(authors=("Nhã Ca",), tags=("Thơ",), query="d"))

    scope = widget.classification_scope()

    assert scope.fts_query == "d"
    ids = app_context.db.list_document_ids_matching(scope.fts_query, scope.where_sql, scope.params)
    assert ids == ["d1"]
    assert "Tác giả: Nhã Ca" in scope.description


def test_the_view_created_after_a_filter_was_set_starts_filtered(qapp, app_context):
    _add(app_context, "d1", tags="Thơ")
    _add(app_context, "d2", tags="AI")
    app_context.filters.select(FORMATS, "pdf")
    app_context.filters.select(TAGS, "Thơ")

    assert _shown(LibraryListWidget(app_context)) == ["d1"]
