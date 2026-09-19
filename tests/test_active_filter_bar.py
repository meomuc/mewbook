"""The "Đang lọc" bar, the search box's two-way link to the filter, and Esc / "Xóa lọc"."""
from PySide6.QtCore import Qt
from PySide6.QtWidgets import QInputDialog

from smartdoc.domain.library_filter import LibraryFilter
from smartdoc.domain.smart_collections import VirtualCollection
from smartdoc.presentation.active_filter_bar import CLEAR_LABEL, ActiveFilterBar
from smartdoc.presentation.library_view import LibraryListWidget
from smartdoc.presentation.omnibar import OmnibarSearchBar
from smartdoc.presentation import save_filter_dialog


def _add(ctx, doc_id, author="A", tags="", ext="pdf", title=None):
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


def _chip_texts(bar):
    return [chip.text() for chip in bar.chip_buttons]


# -- the bar ------------------------------------------------------------------------------------


def test_the_bar_takes_no_room_when_nothing_is_filtered(qapp, app_context):
    bar = ActiveFilterBar(app_context)

    assert bar.isHidden()


def test_every_filter_part_shows_as_a_chip(qapp, app_context):
    _add(app_context, "d1", "Nhã Ca", "Thơ")
    bar = ActiveFilterBar(app_context)

    app_context.filters.set(LibraryFilter(authors=("NHÃ CA",), tags=("Thơ",), formats=("pdf",), query="sài gòn"))

    assert not bar.isHidden()
    assert _chip_texts(bar) == [
        "Hashtag: Thơ  ✕",
        "Tác giả: Nhã Ca  ✕",  # shown under the commonest spelling in the library
        "Định dạng: PDF  ✕",
        "Tìm: “sài gòn”  ✕",
    ]


def test_the_bar_shows_a_filter_that_the_sidebar_used_to_hide(qapp, app_context):
    """The detail panel's "xem tài liệu của tác giả" link is now visible as a chip."""
    _add(app_context, "d1", "Nhã Ca")
    bar = ActiveFilterBar(app_context)

    app_context.filters.set(LibraryFilter(authors=("Nhã Ca",)))

    assert _chip_texts(bar) == ["Tác giả: Nhã Ca  ✕"]


def test_the_special_buckets_and_collections_are_named_readably(qapp, app_context):
    collection = VirtualCollection(name="Sách hay")
    app_context.db.save_collection(collection.id, collection.name, collection.to_json(), collection.logic, 1.0)
    bar = ActiveFilterBar(app_context)

    app_context.filters.set(
        LibraryFilter(collections=(collection.id,), authors=("__unknown_author__",), tags=("__no_tag__",))
    )

    assert _chip_texts(bar) == [
        "Bộ sưu tập: Sách hay  ✕",
        "Hashtag: Chưa phân loại  ✕",
        "Tác giả: Không rõ / Nhiều tác giả  ✕",
    ]


def test_clicking_a_chip_removes_just_that_part(qapp, app_context):
    bar = ActiveFilterBar(app_context)
    app_context.filters.set(LibraryFilter(authors=("A",), tags=("Thơ", "AI"), query="q"))

    bar.chip_buttons[0].click()  # the first hashtag
    assert app_context.filters.current == LibraryFilter(authors=("A",), tags=("AI",), query="q")

    bar.chip_buttons[-1].click()  # the search text
    assert app_context.filters.current == LibraryFilter(authors=("A",), tags=("AI",))


def test_clear_button_removes_everything_including_the_search(qapp, app_context):
    bar = ActiveFilterBar(app_context)
    app_context.filters.set(LibraryFilter(authors=("A",), tags=("Thơ",), collections=("c1",), query="q"))

    assert bar.clear_button.text() == CLEAR_LABEL
    bar.clear_button.click()

    assert app_context.filters.current == LibraryFilter()
    assert bar.isHidden()


def test_the_count_shows_how_many_of_the_library_remain(qapp, app_context):
    for i in range(3):
        _add(app_context, f"d{i}", "A", "Thơ")
    _add(app_context, "d9", "B", "AI")
    bar = ActiveFilterBar(app_context)

    app_context.filters.set(LibraryFilter(tags=("Thơ",)))

    assert bar.count_label.text() == "3 / 4 tài liệu"


def test_the_count_uses_dots_for_thousands(qapp, app_context):
    bar = ActiveFilterBar(app_context)
    bar.context.facets.total = lambda flt: 1234
    bar.context.facets.library_total = lambda: 7545

    app_context.filters.set(LibraryFilter(query="x"))

    assert bar.count_label.text() == "1.234 / 7.545 tài liệu"


def test_a_query_only_filter_offers_no_save_button(qapp, app_context):
    bar = ActiveFilterBar(app_context)

    app_context.filters.set(LibraryFilter(query="x"))
    assert bar.save_button.isHidden()

    app_context.filters.set(LibraryFilter(query="x", tags=("AI",)))
    assert not bar.save_button.isHidden()


# -- Esc in the list -------------------------------------------------------------------------------


def test_escape_in_the_library_clears_the_whole_filter(qapp, app_context):
    _add(app_context, "d1")
    library = LibraryListWidget(app_context)
    library.show()
    app_context.filters.set(LibraryFilter(tags=("Thơ",), query="q"))

    shortcut = library._clear_filter_shortcut
    assert shortcut.key().toString() == "Esc"
    assert shortcut.context() == Qt.WidgetWithChildrenShortcut  # only while the library has focus, not in dialogs
    shortcut.activated.emit()  # offscreen Qt has no active window for a real key press to reach

    assert app_context.filters.current == LibraryFilter()


# -- the search box follows the filter ---------------------------------------------------------------


def test_typing_in_the_search_box_sets_the_query(qapp, app_context):
    box = OmnibarSearchBar(app_context)

    box.setText("  sài gòn ")
    box._publish_search()  # what the debounce timer does

    assert app_context.filters.current.query == "sài gòn"


def test_clearing_the_filter_elsewhere_empties_the_search_box(qapp, app_context):
    box = OmnibarSearchBar(app_context)
    box.setText("sài gòn")
    box._publish_search()

    app_context.filters.clear()

    assert box.text() == ""
    assert not box._timer.isActive()  # the reset must not bounce back as a new search


def test_the_echo_of_its_own_query_does_not_rewrite_what_is_typed(qapp, app_context):
    box = OmnibarSearchBar(app_context)
    box.setText("abc")
    box._publish_search()

    box.setText("abcd")  # typed on before the echo was handled
    box._on_filter_changed(type("E", (), {"filter": LibraryFilter(query="abc")})())

    assert box.text() == "abcd"


def test_a_query_set_elsewhere_shows_in_the_search_box(qapp, app_context):
    box = OmnibarSearchBar(app_context)

    app_context.filters.set_query("nhã ca")

    assert box.text() == "nhã ca"


def test_a_search_box_created_later_starts_with_the_current_query(qapp, app_context):
    app_context.filters.set_query("nhã ca")

    assert OmnibarSearchBar(app_context).text() == "nhã ca"


# -- save the filter as a collection ---------------------------------------------------------------------


def _accept_name(monkeypatch, name):
    prompts = []

    def fake_get_text(parent, title, label, *args, **kwargs):
        prompts.append(label)
        return name, True

    monkeypatch.setattr(QInputDialog, "getText", staticmethod(fake_get_text))
    return prompts


def test_saving_a_simple_filter_makes_a_self_updating_collection(qapp, app_context, monkeypatch):
    _add(app_context, "d1", "Nhã Ca", "Thơ")
    _add(app_context, "d2", "Cổ Long", "Kiếm hiệp")
    prompts = _accept_name(monkeypatch, "Thơ Nhã Ca")

    collection_id = save_filter_dialog.save_filter_as_collection(
        app_context, LibraryFilter(authors=("Nhã Ca",), tags=("Thơ",))
    )

    assert "tự cập nhật" in prompts[0]
    rules = VirtualCollection.from_row(app_context.db.get_collection(collection_id)).rules
    assert {r.operator for r in rules} == {"has_author", "has_tag"}
    assert app_context.filters.current == LibraryFilter(collections=(collection_id,))  # shows it right away
    assert app_context.facets.total(app_context.filters.current) == 1

    _add(app_context, "d3", "nhã ca", "thơ")  # a new matching book joins by itself
    assert app_context.facets.total(app_context.filters.current) == 2


def test_saving_a_complicated_filter_keeps_the_current_documents_and_says_so(qapp, app_context, monkeypatch):
    _add(app_context, "d1", "A", "Thơ")
    _add(app_context, "d2", "A", "AI")
    _add(app_context, "d3", "B", "Thơ")
    prompts = _accept_name(monkeypatch, "Cố định")

    collection_id = save_filter_dialog.save_filter_as_collection(
        app_context, LibraryFilter(tags=("Thơ", "AI"), authors=("A",))
    )

    assert "cố định" in prompts[0]
    assert sorted(app_context.db.list_collection_document_ids(collection_id)) == ["d1", "d2"]


def test_cancelling_or_reusing_a_name_saves_nothing(qapp, app_context, monkeypatch):
    existing = VirtualCollection(name="Có rồi")
    app_context.db.save_collection(existing.id, existing.name, existing.to_json(), existing.logic, 1.0)
    monkeypatch.setattr(QInputDialog, "getText", staticmethod(lambda *a, **k: ("", False)))
    assert save_filter_dialog.save_filter_as_collection(app_context, LibraryFilter(tags=("AI",))) is None

    _accept_name(monkeypatch, "CÓ RỒI")
    monkeypatch.setattr(save_filter_dialog.QMessageBox, "warning", staticmethod(lambda *a, **k: None))
    assert save_filter_dialog.save_filter_as_collection(app_context, LibraryFilter(tags=("AI",))) is None

    assert len(app_context.db.list_collections()) == 1


# -- filter suggestions while typing in the search box ------------------------------------------------------


def test_typing_a_name_offers_it_as_a_filter(qapp, app_context):
    _add(app_context, "d1", "Nhã Ca", "Thơ")
    box = OmnibarSearchBar(app_context)

    box._update_suggestions("nha")

    assert box._suggestion_model.stringList() == ["Tác giả: Nhã Ca (1)"]


def test_advanced_search_syntax_gets_no_suggestions(qapp, app_context):
    _add(app_context, "d1", "Nhã Ca")
    box = OmnibarSearchBar(app_context)

    box._update_suggestions("author:nha")

    assert box._suggestion_model.stringList() == []


def test_picking_a_suggestion_applies_the_filter_and_empties_the_text_search(qapp, app_context):
    _add(app_context, "d1", "Nhã Ca", "Thơ")
    box = OmnibarSearchBar(app_context)
    box.setText("nha")
    box._publish_search()
    box._update_suggestions("nha")

    box._on_suggestion_chosen("Tác giả: Nhã Ca (1)")
    qapp.processEvents()  # the deferred clear

    assert app_context.filters.current == LibraryFilter(authors=("Nhã Ca",))
    assert box.text() == ""
