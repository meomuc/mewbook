# SPDX-License-Identifier: AGPL-3.0-or-later
"""The sheet layout ("Tối giản"): the window opens on "Trang đầu", the top bar moves between it and the library (with the
filters that "Sẽ đọc" etc. mean), the home screen shows what the database says (reading history, author of the month, what
was added), and the cover grid loses its shelves. Same window functions as the shelf look -- only the shape differs."""
from __future__ import annotations

import time

import pytest

from smartdoc.core.event_bus import DocumentSelectedEvent
from smartdoc.domain.library_filter import COLLECTIONS, FORMATS, TAGS
from smartdoc.presentation import theme_manager as tm_module
from smartdoc.presentation.sheet_topbar import HOME, LIBRARY, READING_LIST
from smartdoc.presentation.sheet_window import SheetMainWindow
from smartdoc.presentation.theme import apply_theme
from smartdoc.presentation.theme_manager import theme_manager


@pytest.fixture
def sheet_look(qapp, monkeypatch):
    """The sheet layout applied to the whole application for one test, then everything put back as found."""
    monkeypatch.setattr(tm_module, "load_app_fonts", lambda: [])
    sheet, palette, font = qapp.styleSheet(), qapp.palette(), qapp.font()
    manager = theme_manager()
    manager.apply(qapp, "japandi", "toi-gian")
    apply_theme(qapp, manager.key, manager.tokens())
    yield manager
    manager.apply(qapp, "broadsheet", "ke-sach")
    apply_theme(qapp, "broadsheet")
    qapp.setStyleSheet(sheet)
    qapp.setPalette(palette)
    qapp.setFont(font)


def _docs(context, count=6, *, author="Nguyễn Văn Hải"):
    now = time.time()
    for i in range(count):
        context.db.add_or_update_document(f"d{i}", {
            "title": f"Sách số {i}", "author": author if i % 2 == 0 else "Phạm Thu Hà", "file_path": f"{i}.pdf",
            "extension": "pdf", "file_size": 1, "created_at": now - i * 3600, "tags": "điện-nhẹ" if i < 4 else ""})


@pytest.fixture
def window(qapp, app_context, sheet_look):
    _docs(app_context)
    win = SheetMainWindow(app_context)
    win.resize(1600, 960)
    win.show()
    qapp.processEvents()
    yield win
    win.close()
    win.deleteLater()


def test_the_window_opens_on_the_home_screen(window):
    assert window.pages.currentWidget() is window.home_page
    assert window.top_bar.current_destination() == HOME
    assert window.sidebar_shell is None and window.centralWidget().objectName() == "SheetCanvas"


def test_top_bar_destinations_show_the_library_with_the_matching_filter(window, app_context):
    window.go_to(LIBRARY)
    assert window.pages.currentWidget() is window.library_page and window.top_bar.current_destination() == LIBRARY
    window.go_to(READING_LIST)
    reading_list = app_context.db.ensure_reading_list()
    assert app_context.filters.current.collections == (reading_list,)
    assert window.top_bar.current_destination() == READING_LIST
    app_context.filters.select(TAGS, "điện-nhẹ")  # a further filter: no longer "just the reading list"
    window._sync_destination()
    assert window.top_bar.current_destination() == LIBRARY
    window.go_to(LIBRARY)
    assert not app_context.filters.current.tags  # "Thư viện" starts unfiltered
    window.go_to(HOME)
    assert window.pages.currentWidget() is window.home_page


def test_the_library_page_holds_the_same_parts_as_the_shelf_window(window):
    for name in ("sidebar", "omnibar", "toolbar", "library_view", "detail_panel", "filter_bar", "import_card", "missing_strip"):
        assert getattr(window, name).window() is window


def test_the_grid_has_no_shelves_and_captions_fit_the_cell(window):
    view = window.library_view.list_view
    window.go_to(LIBRARY)
    view._relayout()
    assert view._captioned()
    assert all(shelf.label is None for shelf in view._shelves)
    cell = view._rects[0]
    assert view._row_height() > cell.height()  # room under the cover for stars, title and author
    assert view._two_lines("Một tên sách rất dài " * 6, view.font(), cell.width())[-1].endswith("…")
    assert view._two_lines("Ngắn", view.font(), cell.width()) == ["Ngắn"]


def test_home_shows_the_newest_book_until_something_was_read(window, app_context):
    home = window.home_page
    home.refresh()
    assert home._hero["id"] == "d0" and home._hero_caption == "Mới thêm"
    assert home._total == 6 and len(home._new_docs) >= 4
    app_context.db.record_reading_open("d3", unit="page", total=10)
    app_context.db.record_reading_position("d3", 4, total=10)
    home.refresh()
    assert home._hero["id"] == "d3" and home._hero_caption == "Đang đọc · trang 4 / 10"
    assert "d3" not in [d["id"] for d in home._new_docs]  # the book on the ledge is not repeated under it


def test_the_recently_read_card_steps_through_the_history(window, app_context):
    home = window.home_page
    now = time.time()
    for n, doc_id in enumerate(("d1", "d2", "d3")):
        app_context.db.record_reading_open(doc_id, total=10, now=now - n * 10)
    home.refresh()
    assert [d["id"] for d in home._recent] == ["d1", "d2", "d3"]
    home._step_recent(1)
    assert home._recent[home._recent_index]["id"] == "d2"
    home._step_recent(-1)
    home._step_recent(-1)
    assert home._recent[home._recent_index]["id"] == "d3"  # wraps round
    opened = []
    home.open_requested.connect(opened.append)
    home._read_current()
    assert opened[0]["id"] == "d3"


def test_home_names_the_author_of_the_month(window):
    window.home_page.refresh()
    author = window.home_page._author
    assert author["author"] in {"Nguyễn Văn Hải", "Phạm Thu Hà"} and author["books"] == 3


def test_shortcut_chips_set_the_filter_and_open_the_library(window, app_context):
    home = window.home_page
    labels = [chip.label for chip in home._chips]
    assert labels[0] == "#điện-nhẹ" and "PDF" in labels and "Chưa phân loại" in labels and "Sẽ đọc" in labels
    seen = []
    home.library_requested.connect(lambda: seen.append(1))
    home._apply_chip(next(c for c in home._chips if c.category == FORMATS))
    assert app_context.filters.current.formats == ("pdf",) and seen
    home._apply_chip(next(c for c in home._chips if c.category == COLLECTIONS))
    assert app_context.filters.current.collections and not app_context.filters.current.formats  # replaces, not adds


def test_the_home_search_box_filters_the_library(window, app_context):
    window.home_page.search.setText("sách số 2")
    window.home_page._on_search()
    assert window.pages.currentWidget() is window.library_page
    assert app_context.filters.current.query == "sách số 2"


def test_see_books_of_the_author_opens_the_library_on_that_author(window, app_context):
    window.home_page.refresh()
    name = window.home_page._author["author"]
    window.home_page._on_author_link()
    assert app_context.filters.current.authors == (name,) and window.pages.currentWidget() is window.library_page


def test_an_empty_library_says_so_and_offers_to_add_books(qapp, app_context, sheet_look):
    win = SheetMainWindow(app_context)
    win.resize(1600, 960)
    win.show()
    qapp.processEvents()
    home = win.home_page
    assert home._total == 0 and home._hero is None and not home._chips
    assert not home.add_folder_button.isHidden() and home.search.isHidden()
    win.close()
    win.deleteLater()


def test_a_small_window_drops_the_recent_card_and_folds_a_destination(window, qapp):
    window.resize(1024, 660)
    for _ in range(3):
        qapp.processEvents()
    assert window.home_page._compact
    assert window.top_bar.buttons["collections"].isHidden() and window.top_bar.add_button.text() == "Thêm"
    assert window._detail_floating  # under 1200 px the detail card floats over the sheet


def test_the_detail_card_can_be_closed_and_comes_back_with_a_selection(window, qapp):
    window.go_to(LIBRARY)
    window._on_detail_close_requested()
    assert not window._show_detail and window.detail_panel.isHidden()
    window.context.event_bus.publish(DocumentSelectedEvent(doc={"id": "d1", "title": "x"}))
    for _ in range(3):
        qapp.processEvents()
    assert window._show_detail and not window.detail_panel.isHidden()


def test_opening_a_book_from_home_uses_the_reader(window, monkeypatch):
    opened = []
    monkeypatch.setattr("smartdoc.presentation.sheet_window.open_reader", lambda ctx, doc, parent: opened.append(doc))
    window.home_page.open_requested.emit({"id": "d1"})
    assert opened == [{"id": "d1"}]


def test_the_shelf_look_keeps_its_shelves(qapp, app_context):
    from smartdoc.presentation.main_window import MainWindow

    _docs(app_context)
    win = MainWindow(app_context)
    win.resize(1400, 860)
    win.show()
    qapp.processEvents()
    view = win.library_view.list_view
    assert not view._captioned() and any(shelf.label for shelf in view._shelves)
    win.close()
    win.deleteLater()
