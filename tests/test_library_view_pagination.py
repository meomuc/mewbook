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
    assert list(widget.page_buttons) == [0] and widget.page_buttons[0].isChecked()
    assert "5 tài liệu" in widget.page_buttons[0].toolTip()


def test_pagination_splits_results_across_pages(qapp, app_context):
    total_docs = PAGE_SIZE + 10
    _seed_n_docs(app_context, total_docs)

    widget = LibraryListWidget(app_context)
    assert widget._total_pages == 2
    assert widget.model.rowCount() == PAGE_SIZE

    widget._go_to_page(1)
    assert widget._current_page == 1
    assert widget.model.rowCount() == 10


def test_next_prev_and_page_number_navigation(qapp, app_context):
    _seed_n_docs(app_context, PAGE_SIZE * 2 + 10)  # 3 pages
    widget = LibraryListWidget(app_context)
    assert widget._total_pages == 3

    widget.next_page_button.click()
    assert widget._current_page == 1

    widget.page_buttons[2].click()  # the "3" button
    assert widget._current_page == 2

    widget.prev_page_button.click()
    assert widget._current_page == 1

    widget.page_buttons[0].click()
    assert widget._current_page == 0


def test_page_navigation_buttons_disabled_at_boundaries(qapp, app_context):
    _seed_n_docs(app_context, PAGE_SIZE * 2)  # 2 pages
    widget = LibraryListWidget(app_context)

    assert not widget.prev_page_button.isEnabled()
    assert widget.next_page_button.isEnabled()

    widget._go_to_page(1)
    assert widget.prev_page_button.isEnabled()
    assert not widget.next_page_button.isEnabled()


def test_page_window_always_keeps_the_first_and_last_page_and_marks_gaps():
    window = LibraryListWidget.page_window
    assert window(0, 3) == [0, 1, 2]
    assert window(10, 40) == [0, None, 9, 10, 11, None, 39]
    assert window(0, 40) == [0, 1, None, 39]


def test_page_size_can_be_changed_and_is_remembered(qapp, app_context):
    _seed_n_docs(app_context, 30)
    widget = LibraryListWidget(app_context)
    assert widget.model.rowCount() == PAGE_SIZE
    combo = widget.page_size_combo
    combo.setCurrentIndex(combo.findData(48))
    combo.activated.emit(combo.currentIndex())
    assert widget.model.rowCount() == 30 and widget._total_pages == 1
    assert app_context.config.config.page_size == 48


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
