from smartdoc.presentation.collection_dialog import NewCollectionDialog


def test_body_scrolls_instead_of_being_forced_to_show_every_row_at_once(qapp):
    """Task A2 (docs/UI_DIALOG_AUDIT.md): "Thêm điều kiện" adds rows up to MAX_ROWS (6) -- name field + 6 rows +
    match box can still run taller than a small/scaled-up screen, so the body scrolls instead of the dialog being
    forced to always show every row (which would push "Tạo bộ sưu tập" off screen with no way to reach it)."""
    from smartdoc.presentation.collection_dialog import MAX_ROWS

    dialog = NewCollectionDialog()
    assert dialog._scroll_area is not None
    for _ in range(MAX_ROWS + 3):  # a few clicks past the cap are harmlessly no-ops (add_row_button disables itself)
        dialog.add_row_button.click()
    assert len(dialog._rows) == MAX_ROWS

    # A scroll area's minimum size hint is independent of its content by design -- that is exactly what lets the
    # dialog be shown/resized shorter than its full content, scrolling instead of forcing every row on screen.
    assert dialog.minimumSizeHint().height() < dialog.body_widget.sizeHint().height()


def test_build_collection_returns_none_when_name_is_blank(qapp):
    dialog = NewCollectionDialog()
    dialog.name_edit.setText("")
    dialog.value_edit.setText("pdf")
    assert dialog.build_collection() is None


def test_build_collection_returns_none_when_value_is_blank(qapp):
    dialog = NewCollectionDialog()
    dialog.name_edit.setText("My Collection")
    dialog.value_edit.setText("")
    assert dialog.build_collection() is None


def test_build_collection_builds_expected_rule(qapp):
    dialog = NewCollectionDialog()
    dialog.name_edit.setText("PDF sach")
    dialog.field_combo.setCurrentIndex(0)  # "Định dạng bằng" -> extension/eq
    dialog.value_edit.setText("pdf")

    collection = dialog.build_collection()
    assert collection is not None
    assert collection.name == "PDF sach"
    sql, params = collection.to_sql_where_clause()
    assert sql == "extension = ?"
    assert params == ("pdf",)


def test_several_conditions_and_the_match_mode_are_kept(qapp):
    dialog = NewCollectionDialog()
    dialog.name_edit.setText("Nhiều điều kiện")
    dialog.value_edit.setText("pdf")
    dialog._add_row(None)
    dialog._rows[1].field_combo.setCurrentIndex(1)  # Tác giả chứa
    dialog._rows[1].value_edit.setText("Osho")
    dialog.logic_combo.setCurrentIndex(1)  # bất kỳ

    collection = dialog.build_collection()

    assert collection.logic == "OR" and [r.value for r in collection.rules] == ["pdf", "Osho"]
    sql, params = collection.to_sql_where_clause()
    assert " OR " in sql and params[0] == "pdf"
    dialog.deleteLater()


def test_an_empty_row_is_ignored_and_the_last_row_cannot_be_removed(qapp):
    dialog = NewCollectionDialog()
    dialog.name_edit.setText("X")
    dialog.value_edit.setText("pdf")
    dialog._add_row(None)  # left empty
    assert len(dialog.build_collection().rules) == 1
    dialog._remove_row(dialog._rows[1])
    dialog._remove_row(dialog._rows[0])  # the only row stays
    assert len(dialog._rows) == 1
    dialog.deleteLater()


def test_the_live_count_shows_how_many_books_match(qapp, app_context):
    app_context.db.add_or_update_document("a", {"title": "A", "file_path": "a.pdf", "extension": "pdf", "created_at": 1.0})
    app_context.db.add_or_update_document("b", {"title": "B", "file_path": "b.epub", "extension": "epub", "created_at": 2.0})
    dialog = NewCollectionDialog(context=app_context)
    dialog.name_edit.setText("PDF")
    dialog.value_edit.setText("pdf")
    dialog._update_count()
    assert dialog.match_label.text() == "1 sách khớp ngay bây giờ"
    dialog.deleteLater()


def test_editing_offers_delete_and_reports_it(qapp):
    from smartdoc.domain.smart_collections import SmartRule, VirtualCollection

    existing = VirtualCollection(name="Cũ", rules=[SmartRule(field="extension", operator="eq", value="pdf")])
    dialog = NewCollectionDialog(collection=existing)
    dialog.delete_button.click()
    assert dialog.delete_requested
    assert dialog.build_collection().id == existing.id
    dialog.deleteLater()
