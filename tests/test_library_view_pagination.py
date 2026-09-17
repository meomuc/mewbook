from smartdoc.presentation.library_view import PAGE_SIZE, LibraryListWidget


def _seed_n_docs(app_context, n: int) -> None:
    for i in range(n):
        app_context.db.add_or_update_document(
            f"d{i}", {"title": f"Doc {i:04d}", "author": "A", "file_path": f"{i}.pdf", "created_at": float(i)}
        )


def test_single_page_when_below_page_size(qapp, app_context):
    _seed_n_docs(app_context, 5)
    widget = LibraryListWidget(app_context)
    assert widget.model.rowCount() == 5
    assert widget._total_pages == 1
    assert widget.page_label.text() == "Trang 1 / 1 (5 tài liệu)"


def test_pagination_splits_results_across_pages(qapp, app_context):
    total_docs = PAGE_SIZE + 30
    _seed_n_docs(app_context, total_docs)

    widget = LibraryListWidget(app_context)
    assert widget._total_pages == 2
    assert widget.model.rowCount() == PAGE_SIZE

    widget._go_to_page(1)
    assert widget._current_page == 1
    assert widget.model.rowCount() == 30


def test_next_prev_first_last_navigation(qapp, app_context):
    _seed_n_docs(app_context, PAGE_SIZE * 2 + 10)  # 3 pages
    widget = LibraryListWidget(app_context)
    assert widget._total_pages == 3

    widget.next_page_button.click()
    assert widget._current_page == 1

    widget.last_page_button.click()
    assert widget._current_page == 2

    widget.prev_page_button.click()
    assert widget._current_page == 1

    widget.first_page_button.click()
    assert widget._current_page == 0


def test_page_navigation_buttons_disabled_at_boundaries(qapp, app_context):
    _seed_n_docs(app_context, PAGE_SIZE * 2)  # 2 pages
    widget = LibraryListWidget(app_context)

    assert not widget.first_page_button.isEnabled()
    assert not widget.prev_page_button.isEnabled()
    assert widget.next_page_button.isEnabled()
    assert widget.last_page_button.isEnabled()

    widget._go_to_page(1)
    assert widget.first_page_button.isEnabled()
    assert widget.prev_page_button.isEnabled()
    assert not widget.next_page_button.isEnabled()
    assert not widget.last_page_button.isEnabled()


def test_jump_spin_navigates_to_typed_page(qapp, app_context):
    _seed_n_docs(app_context, PAGE_SIZE * 2 + 5)  # 3 pages
    widget = LibraryListWidget(app_context)

    widget.jump_spin.setValue(3)
    widget.jump_button.click()

    assert widget._current_page == 2  # page 3 is index 2


def test_searching_resets_to_first_page(qapp, app_context):
    _seed_n_docs(app_context, PAGE_SIZE * 2)
    widget = LibraryListWidget(app_context)
    widget._go_to_page(1)
    assert widget._current_page == 1

    from smartdoc.core.event_bus import SearchRequestedEvent

    app_context.event_bus.publish(SearchRequestedEvent(query="Doc"))
    assert widget._current_page == 0


def test_out_of_range_page_clamped_when_result_set_shrinks(qapp, app_context):
    _seed_n_docs(app_context, PAGE_SIZE * 2)
    widget = LibraryListWidget(app_context)
    widget._go_to_page(1)
    assert widget._current_page == 1

    # Delete everything but a handful of documents -> only 1 page left now.
    for i in range(PAGE_SIZE * 2 - 3):
        app_context.db.delete_document(f"d{i}")

    widget.reload()
    assert widget._current_page == 0
    assert widget._total_pages == 1
