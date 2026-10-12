from smartdoc.presentation.collection_dialog import NewCollectionDialog


def test_a_collection_needs_only_a_name_and_has_no_rules(qapp):
    dialog = NewCollectionDialog()
    assert not dialog.create_button.isEnabled()  # nothing typed yet
    dialog.name_edit.setText("  Sách mùa hè  ")
    assert dialog.create_button.isEnabled()

    collection = dialog.build_collection()

    assert collection is not None and collection.name == "Sách mùa hè" and collection.rules == []
    assert collection.to_sql_where_clause() == ("1=1", ())  # no rule to follow: it is filled by hand
    dialog.deleteLater()


def test_a_blank_name_builds_nothing(qapp):
    dialog = NewCollectionDialog()
    dialog.name_edit.setText("   ")
    assert dialog.build_collection() is None and not dialog.create_button.isEnabled()
    dialog.deleteLater()


def test_the_dialog_offers_no_conditions(qapp):
    dialog = NewCollectionDialog()
    assert not hasattr(dialog, "add_row_button") and not hasattr(dialog, "logic_combo")
    assert "tự chọn" in dialog.subtitle_label.text()
    dialog.deleteLater()
