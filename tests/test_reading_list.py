from PySide6.QtCore import Qt

from smartdoc.core.event_bus import LibraryUpdatedEvent
from smartdoc.infrastructure.database import READING_LIST_ID, READING_LIST_NAME
from smartdoc.presentation.library_view import LibraryListWidget
from smartdoc.presentation.sidebar import LibrarySidebar


def _items(sidebar):
    """The rows that are All / reading list / saved collections. The "Chưa phân loại" pill and the "BỘ SƯU TẬP"
    heading are display rows of the pill list, not collections."""
    from PySide6.QtCore import Qt

    from smartdoc.presentation.sidebar import UNCLASSIFIED_ID
    from smartdoc.presentation.sidebar_style import SECTION_ITEM_ID

    lst = sidebar.collections_list
    return [lst.item(i) for i in range(lst.count())
            if lst.item(i).data(Qt.UserRole + 1) not in (UNCLASSIFIED_ID, SECTION_ITEM_ID)]


def _item(sidebar, index):
    return _items(sidebar)[index]


def _current(sidebar):
    return _items(sidebar).index(sidebar.collections_list.currentItem())


def _seed(app_context):
    for i in range(3):
        app_context.db.add_or_update_document(
            f"d{i}", {"title": f"Book {i}", "author": "A", "file_path": f"b{i}.pdf", "extension": "pdf", "created_at": float(i)}
        )


def test_toggle_creates_the_reading_list_and_flips_membership(app_context):
    _seed(app_context)
    db = app_context.db

    assert db.toggle_reading_list("d1") is True
    assert db.get_collection(READING_LIST_ID)["name"] == READING_LIST_NAME
    assert db.reading_list_ids() == {"d1"}

    assert db.toggle_reading_list("d1") is False
    assert db.reading_list_ids() == set()


def test_reading_list_survives_a_rename(app_context):
    """Found by its fixed id, not its name -- renaming it (or creating an
    unrelated collection called "Sẽ đọc") must not redirect the stars."""
    _seed(app_context)
    db = app_context.db
    db.ensure_reading_list()
    db.rename_collection(READING_LIST_ID, "Đọc cuối tuần")

    db.toggle_reading_list("d2")

    assert db.list_collection_document_ids(READING_LIST_ID) == ["d2"]
    assert len(db.list_collections()) == 1


def test_star_toggle_in_the_library_updates_stars_and_publishes(qapp, app_context):
    _seed(app_context)
    widget = LibraryListWidget(app_context)
    events = []
    app_context.event_bus.subscribe(LibraryUpdatedEvent, lambda e: events.append(e))

    widget.toggle_reading_list("d0")

    assert widget._is_starred("d0")
    assert events  # sidebar count refreshes off this

    widget.reload()
    assert widget._is_starred("d0")  # reloaded from the database, not just local state


def test_clicking_the_star_on_a_shelf_cover_toggles_it_without_selecting(qapp, app_context):
    from PySide6.QtTest import QTest

    _seed(app_context)
    widget = LibraryListWidget(app_context)
    widget.resize(700, 500)
    widget.show()
    qapp.processEvents()

    view = widget.list_view
    doc_id = widget.model.document_at(0)["id"]
    star = view._star_rect(0)
    QTest.mouseClick(view.viewport(), Qt.LeftButton, Qt.NoModifier, star.center())

    assert widget._is_starred(doc_id)
    assert not view.selectionModel().hasSelection()  # clicking the star must not also select/open the book


def test_clicking_the_cover_outside_the_star_selects_but_does_not_toggle(qapp, app_context):
    from PySide6.QtTest import QTest

    _seed(app_context)
    widget = LibraryListWidget(app_context)
    widget.resize(700, 500)
    widget.show()
    qapp.processEvents()

    view = widget.list_view
    rect = view.visualRect(widget.model.index(0, 0))
    QTest.mouseClick(view.viewport(), Qt.LeftButton, Qt.NoModifier, rect.center())

    assert not widget._is_starred(widget.model.document_at(0)["id"])
    assert view.selectionModel().hasSelection()


def test_reading_list_is_pinned_under_all_documents_in_the_sidebar(qapp, app_context):
    from smartdoc.domain.smart_collections import VirtualCollection

    older = VirtualCollection(name="Aaa cũ", created_at=0.0)
    app_context.db.save_collection(older.id, older.name, older.to_json(), older.logic, older.created_at)
    app_context.db.ensure_reading_list()

    sidebar = LibrarySidebar(app_context)

    assert "Sẽ đọc" in _item(sidebar, 1).text()
    assert _item(sidebar, 1).text().startswith("Sẽ đọc")  # the pill draws its own filled-star icon
