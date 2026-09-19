from PySide6.QtCore import QEvent, QPointF, Qt
from PySide6.QtGui import QMouseEvent

from smartdoc.core.event_bus import LibraryUpdatedEvent
from smartdoc.infrastructure.database import READING_LIST_ID, READING_LIST_NAME
from smartdoc.presentation.library_view import LibraryListWidget
from smartdoc.presentation.sidebar import LibrarySidebar


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


def test_clicking_the_star_on_a_grid_cover_toggles_it(qapp, app_context):
    _seed(app_context)
    widget = LibraryListWidget(app_context)
    widget.resize(700, 500)
    widget.show()
    qapp.processEvents()

    view = widget.list_view
    delegate = view.itemDelegate()
    index = widget.model.index(0, 0)
    doc_id = widget.model.document_at(0)["id"]

    from PySide6.QtWidgets import QStyleOptionViewItem

    option = QStyleOptionViewItem()
    view.initViewItemOption(option)
    option.rect = view.visualRect(index)
    star = delegate._star_rect(option, index)
    assert star is not None

    click_at = QPointF(star.center())
    release = QMouseEvent(QEvent.MouseButtonRelease, click_at, click_at, Qt.LeftButton, Qt.NoButton, Qt.NoModifier)
    consumed = delegate.editorEvent(release, widget.model, option, index)

    assert consumed  # clicking the star must not also select/open the book
    assert widget._is_starred(doc_id)


def test_clicking_the_cover_outside_the_star_does_not_toggle(qapp, app_context):
    _seed(app_context)
    widget = LibraryListWidget(app_context)
    widget.resize(700, 500)
    widget.show()
    qapp.processEvents()

    from PySide6.QtWidgets import QStyleOptionViewItem

    view = widget.list_view
    index = widget.model.index(0, 0)
    option = QStyleOptionViewItem()
    view.initViewItemOption(option)
    option.rect = view.visualRect(index)

    elsewhere = QPointF(option.rect.bottomLeft()) + QPointF(5, -5)
    release = QMouseEvent(QEvent.MouseButtonRelease, elsewhere, elsewhere, Qt.LeftButton, Qt.NoButton, Qt.NoModifier)
    view.itemDelegate().editorEvent(release, widget.model, option, index)

    assert not widget._is_starred(widget.model.document_at(0)["id"])


def test_reading_list_is_pinned_under_all_documents_in_the_sidebar(qapp, app_context):
    from smartdoc.domain.smart_collections import VirtualCollection

    older = VirtualCollection(name="Aaa cũ", created_at=0.0)
    app_context.db.save_collection(older.id, older.name, older.to_json(), older.logic, older.created_at)
    app_context.db.ensure_reading_list()

    sidebar = LibrarySidebar(app_context)

    assert "Sẽ đọc" in sidebar.collections_list.item(1).text()
    assert sidebar.collections_list.item(1).text().startswith("★")
