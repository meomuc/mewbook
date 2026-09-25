from PySide6.QtCore import Qt

from smartdoc.presentation.library_view import COLUMN_DEFS, OPTIONAL_COLUMN_KEYS, LibraryTableModel


def _doc(**overrides):
    base = {
        "id": "d1",
        "title": "Sample Title",
        "author": "Sample Author",
        "extension": "pdf",
        "file_size": 2_500_000,
        "tags": "AI,ML",
        "avg_rating": 4.2,
        "review_count": 7,
        "created_at": 1700000000.0,
        "updated_at": 1700003600.0,
    }
    base.update(overrides)
    return base


def test_default_columns_include_title_plus_all_optional_ones():
    model = LibraryTableModel()
    assert model.columnCount() == len(COLUMN_DEFS)


def test_title_is_always_the_first_column_even_if_not_requested():
    model = LibraryTableModel()
    model.set_visible_columns(["author"])
    assert model.columnCount() == 2  # title + author
    assert model.headerData(0, Qt.Horizontal) == "TÊN SÁCH"
    assert model.headerData(1, Qt.Horizontal) == "TÁC GIẢ"


def test_set_visible_columns_ignores_unknown_keys():
    model = LibraryTableModel()
    model.set_visible_columns(["author", "not_a_real_column"])
    assert model.visible_optional_columns() == ["author"]


def test_data_formats_rating_and_dates(qapp):
    model = LibraryTableModel()
    model.set_visible_columns(OPTIONAL_COLUMN_KEYS)
    model.set_documents([_doc()])


    columns = ["title", *OPTIONAL_COLUMN_KEYS]
    values = {col: model.data(model.index(0, i), Qt.DisplayRole) for i, col in enumerate(columns)}

    assert values["title"] == "Sample Title"
    assert values["author"] == "Sample Author"
    assert values["tags"] == "AI,ML"
    assert values["avg_rating"] == "★ 4,2"
    assert values["review_count"] == "7"
    assert "2023" in values["created_at"] or "/" in values["created_at"]  # a formatted date, not blank
    assert values["updated_at"] != "—"


def test_data_shows_dash_for_missing_optional_values(qapp):
    model = LibraryTableModel()
    model.set_visible_columns(OPTIONAL_COLUMN_KEYS)
    model.set_documents([_doc(avg_rating=None, review_count=0, tags="", updated_at=None)])


    columns = ["title", *OPTIONAL_COLUMN_KEYS]
    values = {col: model.data(model.index(0, i), Qt.DisplayRole) for i, col in enumerate(columns)}

    assert values["avg_rating"] == "—"
    assert values["tags"] == "—"
    assert values["updated_at"] == "—"
    assert values["review_count"] == "0"  # a real zero, not a dash


def test_document_at_returns_the_right_row():
    model = LibraryTableModel()
    model.set_documents([_doc(id="d1"), _doc(id="d2")])
    assert model.document_at(0)["id"] == "d1"
    assert model.document_at(1)["id"] == "d2"
    assert model.document_at(5) is None


def test_format_and_file_size_columns(qapp):
    model = LibraryTableModel()
    model.set_visible_columns(["format", "file_size"])
    model.set_documents([_doc(extension="epub", file_size=1024)])

    assert model.data(model.index(0, 1), Qt.DisplayRole) == "EPUB"
    assert model.data(model.index(0, 2), Qt.DisplayRole) == "1.0 KB"


def test_title_column_has_a_cover_thumbnail_decoration(qapp):
    from PySide6.QtGui import QIcon

    model = LibraryTableModel()
    model.set_documents([_doc()])

    icon = model.data(model.index(0, 0), Qt.DecorationRole)
    assert isinstance(icon, QIcon)
    assert not icon.isNull()


def test_thumbnail_is_cached_per_cover_or_doc_id(qapp):
    model = LibraryTableModel()
    model.set_documents([_doc(id="d1"), _doc(id="d2")])

    icon1 = model.data(model.index(0, 0), Qt.DecorationRole)
    icon2 = model.data(model.index(1, 0), Qt.DecorationRole)
    assert icon1.cacheKey() != icon2.cacheKey()  # different doc_ids -> different placeholder gradients
    assert len(model._icon_cache) == 2



def test_list_view_title_column_stretches_to_fill_the_table(qapp, app_context):
    from PySide6.QtWidgets import QHeaderView

    from smartdoc.presentation.library_view import LibraryListWidget

    widget = LibraryListWidget(app_context)
    header = widget.table_view.horizontalHeader()
    keys = widget.table_model.column_keys()

    assert not header.stretchLastSection()
    assert header.sectionResizeMode(keys.index("title")) == QHeaderView.Stretch
    for section, key in enumerate(keys):
        if key != "title":
            assert header.sectionResizeMode(section) == QHeaderView.Interactive
            assert header.sectionSize(section) >= 48


def test_list_view_column_widths_reapplied_after_toggling_a_column(qapp, app_context):
    from PySide6.QtWidgets import QHeaderView

    from smartdoc.presentation.library_view import LibraryListWidget

    widget = LibraryListWidget(app_context)
    widget.table_model.set_visible_columns(["tags", "created_at"])
    widget._apply_column_widths()
    header = widget.table_view.horizontalHeader()

    assert header.sectionResizeMode(0) == QHeaderView.Stretch
    date_width = header.sectionSize(2)
    assert date_width >= widget.table_view.fontMetrics().horizontalAdvance("31/12/2026")
