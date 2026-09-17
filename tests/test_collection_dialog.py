from smartdoc.presentation.collection_dialog import NewCollectionDialog


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
