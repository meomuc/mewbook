"""The "Lọc nhanh" box and the "Xem tất cả" picker."""
from PySide6.QtCore import Qt
from PySide6.QtTest import QTest
from PySide6.QtWidgets import QDialog

from smartdoc.domain.library_filter import AUTHORS, LibraryFilter
from smartdoc.domain.smart_collections import VirtualCollection
from smartdoc.presentation.facet_panel import AUTHOR_ROW_LIMIT, FacetPanel
from smartdoc.presentation.facet_picker_dialog import FacetPickerDialog
from smartdoc.presentation.quick_filter import QuickFilterBox


def _add(ctx, doc_id, author="", tags="", ext="pdf"):
    ctx.db.add_or_update_document(
        doc_id,
        {"title": doc_id, "author": author, "tags": tags, "extension": ext, "file_path": f"{doc_id}.{ext}", "created_at": 1.0},
    )


def _seed(ctx):
    _add(ctx, "d1", "Nhã Ca", "Thơ")
    _add(ctx, "d2", "Cổ Long", "Kiếm hiệp")
    collection = VirtualCollection(name="Nhã tuyển")
    ctx.db.save_collection(collection.id, collection.name, collection.to_json(), collection.logic, 1.0)
    return collection


def _type(box, text):
    box.edit.setText(text)
    box.update_suggestions()  # what the debounce timer does


def _rows(box):
    return [box.suggestions.item(i).text() for i in range(box.suggestions.count())]


# -- quick filter ------------------------------------------------------------------------------------


def test_typing_lists_matches_from_every_group_ignoring_accents(qapp, app_context):
    _seed(app_context)
    box = QuickFilterBox(app_context)
    box.show()

    _type(box, "nha")

    assert _rows(box) == ["Nhã Ca · Tác giả (1)", "Nhã tuyển · Bộ sưu tập (0)"]
    assert box.suggestions.isVisible()


def test_no_match_or_a_single_letter_shows_nothing(qapp, app_context):
    _seed(app_context)
    box = QuickFilterBox(app_context)
    box.show()

    _type(box, "zzz")
    assert not box.suggestions.isVisible()
    _type(box, "n")
    assert not box.suggestions.isVisible()


def test_enter_applies_the_highlighted_suggestion_and_clears_the_box(qapp, app_context):
    _seed(app_context)
    box = QuickFilterBox(app_context)
    _type(box, "cổ")

    box._apply_current()

    assert app_context.filters.current == LibraryFilter(authors=("Cổ Long",))
    assert box.edit.text() == ""
    assert box.suggestions.isHidden()


def test_enter_before_the_debounce_fired_still_uses_what_is_typed(qapp, app_context):
    _seed(app_context)
    box = QuickFilterBox(app_context)
    box.edit.setText("kiếm")  # the timer is running, suggestions not built yet

    box._apply_current()

    assert app_context.filters.current.tags == ("Kiếm hiệp",)


def test_a_click_on_a_suggestion_applies_it(qapp, app_context):
    _seed(app_context)
    box = QuickFilterBox(app_context)
    _type(box, "thơ")

    box._on_item_clicked(box.suggestions.item(0))

    assert app_context.filters.current.tags == ("Thơ",)


def test_ctrl_click_adds_instead_of_switching(qapp, app_context, monkeypatch):
    _seed(app_context)
    app_context.filters.select(AUTHORS, "Cổ Long")
    box = QuickFilterBox(app_context)
    monkeypatch.setattr(QuickFilterBox, "_additive_click", lambda self: True)
    _type(box, "nhã")

    box._on_item_clicked(box.suggestions.item(0))

    assert app_context.filters.current.authors == ("Cổ Long", "Nhã Ca")


def test_already_selected_values_are_not_suggested_again(qapp, app_context):
    _seed(app_context)
    app_context.filters.select(AUTHORS, "Nhã Ca")
    box = QuickFilterBox(app_context)

    _type(box, "nhã")

    assert all("Nhã Ca" not in row for row in _rows(box))


def test_arrow_keys_move_through_the_suggestions_and_escape_clears(qapp, app_context):
    _seed(app_context)
    box = QuickFilterBox(app_context)
    box.show()
    _type(box, "nhã")
    assert box.suggestions.currentRow() == 0

    QTest.keyClick(box.edit, Qt.Key_Down)
    assert box.suggestions.currentRow() == 1

    QTest.keyClick(box.edit, Qt.Key_Escape)
    assert box.edit.text() == ""
    assert box.suggestions.isHidden()


def test_the_panel_has_a_quick_filter_at_the_top(qapp, app_context):
    panel = FacetPanel(app_context)

    assert isinstance(panel.quick_filter, QuickFilterBox)


# -- "Xem tất cả" picker ------------------------------------------------------------------------------


def _many_authors(ctx, n=AUTHOR_ROW_LIMIT + 12):
    for i in range(n):
        _add(ctx, f"d{i}", f"Tác giả {i:02d}")
    _add(ctx, "x1", "Nhã Ca")


def _picker_rows(dialog):
    return [dialog.list.item(i).text() for i in range(dialog.list.count())]


def test_the_picker_lists_every_author_and_narrows_as_you_type(qapp, app_context):
    _many_authors(app_context)
    dialog = FacetPickerDialog(app_context, AUTHORS)

    assert dialog.list.count() == AUTHOR_ROW_LIMIT + 13
    dialog.search_edit.setText("nha")  # no accents typed
    assert _picker_rows(dialog) == ["Nhã Ca (1)"]
    assert "1 kết quả" in dialog.info_label.text()


def test_a_click_in_the_picker_switches_the_filter_and_closes(qapp, app_context):
    _many_authors(app_context)
    dialog = FacetPickerDialog(app_context, AUTHORS)
    dialog.search_edit.setText("nhã")

    dialog._on_clicked(dialog.list.item(0))

    assert app_context.filters.current.authors == ("Nhã Ca",)
    assert dialog.result() == QDialog.Accepted


def test_ctrl_click_in_the_picker_adds_and_stays_open(qapp, app_context, monkeypatch):
    _many_authors(app_context)
    dialog = FacetPickerDialog(app_context, AUTHORS)
    monkeypatch.setattr(FacetPickerDialog, "_additive_click", lambda self: True)

    dialog.search_edit.setText("tác giả 01")
    dialog._on_clicked(dialog.list.item(0))
    dialog.search_edit.setText("tác giả 02")
    dialog._on_clicked(dialog.list.item(0))

    assert app_context.filters.current.authors == ("Tác giả 01", "Tác giả 02")
    assert dialog.result() != QDialog.Accepted
    assert dialog.list.item(0).background().style() != 0  # the picked one is highlighted


def test_the_see_all_button_opens_the_picker(qapp, app_context, monkeypatch):
    _many_authors(app_context)
    panel = FacetPanel(app_context)
    opened = []
    monkeypatch.setattr(FacetPickerDialog, "exec", lambda self: opened.append(self.category))

    panel.open_author_picker()

    assert opened == [AUTHORS]


def test_a_huge_list_is_capped_but_says_how_many_matched(qapp, app_context):
    for i in range(450):
        app_context.db.add_or_update_document(
            f"d{i}", {"title": "t", "author": f"Người {i:03d}", "file_path": f"{i}.pdf", "created_at": 1.0}
        )
    dialog = FacetPickerDialog(app_context, AUTHORS)

    assert dialog.list.count() == 400
    assert "450 kết quả" in dialog.info_label.text()
