from PySide6.QtWidgets import QDialog, QInputDialog, QMessageBox

from smartdoc.core.event_bus import FilterChangedEvent, LibraryUpdatedEvent
from smartdoc.domain.library_filter import LibraryFilter
from smartdoc.domain.smart_collections import SmartRule, VirtualCollection
from smartdoc.presentation import collection_dialog as cd_module
from smartdoc.presentation.sidebar import LibrarySidebar


def _pick_action_containing(text_substring: str):
    def fake_exec_menu(self, menu, _position):
        for action in menu.actions():
            if text_substring in action.text():
                return action
        return None

    return fake_exec_menu


def test_reload_collections_always_includes_all_documents_first(qapp, app_context):
    sidebar = LibrarySidebar(app_context)
    assert sidebar.collections_list.count() == 1
    assert sidebar.collections_list.item(0).text() == "Tất cả tài liệu (0)"


def test_reload_collections_lists_saved_collections(qapp, app_context):
    collection = VirtualCollection(name="Sach AI", rules=[SmartRule(field="tags", operator="contains", value="AI")])
    app_context.db.save_collection(
        collection.id, collection.name, collection.to_json(), collection.logic, collection.created_at
    )

    sidebar = LibrarySidebar(app_context)
    assert sidebar.collections_list.count() == 2
    assert sidebar.collections_list.item(1).text() == "Sach AI (0)"


def test_reload_collections_shows_document_count_per_collection(qapp, app_context):
    app_context.db.add_or_update_document(
        "d1", {"title": "A", "author": "X", "file_path": "a.pdf", "extension": "pdf", "created_at": 1.0}
    )
    app_context.db.add_or_update_document(
        "d2", {"title": "B", "author": "Y", "file_path": "b.epub", "extension": "epub", "created_at": 2.0}
    )
    collection = VirtualCollection(name="PDFs", rules=[SmartRule(field="extension", operator="eq", value="pdf")])
    app_context.db.save_collection(
        collection.id, collection.name, collection.to_json(), collection.logic, collection.created_at
    )

    sidebar = LibrarySidebar(app_context)

    assert sidebar.collections_list.item(0).text() == "Tất cả tài liệu (2)"
    assert sidebar.collections_list.item(1).text() == "PDFs (1)"


def test_clicking_a_collection_filters_by_it_and_all_documents_clears(qapp, app_context):
    collection = VirtualCollection(name="Sach AI", rules=[SmartRule(field="tags", operator="contains", value="AI")])
    app_context.db.save_collection(
        collection.id, collection.name, collection.to_json(), collection.logic, collection.created_at
    )
    sidebar = LibrarySidebar(app_context)

    received = []
    app_context.event_bus.subscribe(FilterChangedEvent, lambda e: received.append(e))

    sidebar._on_collection_clicked(sidebar.collections_list.item(1))
    assert received[-1].filter.collections == (collection.id,)

    sidebar._on_collection_clicked(sidebar.collections_list.item(0))
    assert received[-1].filter.collections == ()


def test_add_collection_via_dialog_saves_and_reloads_list(qapp, app_context, monkeypatch):
    monkeypatch.setattr(cd_module.NewCollectionDialog, "exec", lambda self: QDialog.Accepted)
    fake_collection = VirtualCollection(
        name="Test Collection", rules=[SmartRule(field="extension", operator="eq", value="pdf")]
    )
    monkeypatch.setattr(cd_module.NewCollectionDialog, "build_collection", lambda self: fake_collection)

    sidebar = LibrarySidebar(app_context)
    assert sidebar.collections_list.count() == 1

    sidebar._on_add_collection()

    assert sidebar.collections_list.count() == 2
    assert sidebar.collections_list.item(1).text() == "Test Collection (0)"
    assert app_context.db.get_collection(fake_collection.id) is not None


def test_add_collection_cancelled_dialog_does_not_save(qapp, app_context, monkeypatch):
    monkeypatch.setattr(cd_module.NewCollectionDialog, "exec", lambda self: QDialog.Rejected)

    sidebar = LibrarySidebar(app_context)
    sidebar._on_add_collection()

    assert sidebar.collections_list.count() == 1
    assert app_context.db.list_collections() == []


def test_add_collection_with_duplicate_name_is_rejected(qapp, app_context, monkeypatch):
    existing = VirtualCollection(name="Sach AI", rules=[SmartRule(field="tags", operator="contains", value="AI")])
    app_context.db.save_collection(
        existing.id, existing.name, existing.to_json(), existing.logic, existing.created_at
    )

    monkeypatch.setattr(cd_module.NewCollectionDialog, "exec", lambda self: QDialog.Accepted)
    duplicate = VirtualCollection(name="Sach AI", rules=[SmartRule(field="extension", operator="eq", value="pdf")])
    monkeypatch.setattr(cd_module.NewCollectionDialog, "build_collection", lambda self: duplicate)
    warnings = []
    monkeypatch.setattr(QMessageBox, "warning", staticmethod(lambda *a, **k: warnings.append(1) or QMessageBox.Ok))

    sidebar = LibrarySidebar(app_context)
    sidebar._on_add_collection()

    assert len(warnings) == 1
    assert len(app_context.db.list_collections()) == 1  # the duplicate was not saved
    assert app_context.db.get_collection(duplicate.id) is None


def test_add_collection_with_duplicate_name_case_insensitive(qapp, app_context, monkeypatch):
    existing = VirtualCollection(name="Sach AI", rules=[SmartRule(field="tags", operator="contains", value="AI")])
    app_context.db.save_collection(
        existing.id, existing.name, existing.to_json(), existing.logic, existing.created_at
    )

    monkeypatch.setattr(cd_module.NewCollectionDialog, "exec", lambda self: QDialog.Accepted)
    duplicate = VirtualCollection(name="  sach ai  ", rules=[SmartRule(field="extension", operator="eq", value="pdf")])
    monkeypatch.setattr(cd_module.NewCollectionDialog, "build_collection", lambda self: duplicate)
    monkeypatch.setattr(QMessageBox, "warning", staticmethod(lambda *a, **k: QMessageBox.Ok))

    sidebar = LibrarySidebar(app_context)
    sidebar._on_add_collection()

    assert len(app_context.db.list_collections()) == 1


def test_reload_collections_preserves_current_selection(qapp, app_context):
    collection = _seed_collection(app_context)
    sidebar = LibrarySidebar(app_context)
    sidebar._on_collection_clicked(sidebar.collections_list.item(1))
    assert sidebar.collections_list.currentRow() == 1

    # A background import (or any other document change) must not silently
    # snap the selection back to "Tất cả tài liệu".
    app_context.event_bus.publish(LibraryUpdatedEvent())

    assert sidebar.collections_list.currentRow() == 1
    assert sidebar._current_collection_id() == collection.id


def test_external_filter_change_updates_highlighted_row(qapp, app_context):
    """A selection change made elsewhere (e.g. clicking a hashtag in the
    Document Detail Panel replaces the whole filter) must be reflected here too."""
    _seed_collection(app_context)
    sidebar = LibrarySidebar(app_context)
    sidebar._on_collection_clicked(sidebar.collections_list.item(1))
    assert sidebar.collections_list.currentRow() == 1

    app_context.filters.set(LibraryFilter(tags=("AI",)))

    assert sidebar.collections_list.currentRow() == 0


def _seed_collection(app_context) -> VirtualCollection:
    collection = VirtualCollection(name="Sach AI", rules=[SmartRule(field="tags", operator="contains", value="AI")])
    app_context.db.save_collection(
        collection.id, collection.name, collection.to_json(), collection.logic, collection.created_at
    )
    return collection


def _position_of_row(sidebar: LibrarySidebar, row: int):
    return sidebar.collections_list.visualItemRect(sidebar.collections_list.item(row)).center()


def test_right_click_on_all_documents_pseudo_item_shows_no_menu(qapp, app_context, monkeypatch):
    sidebar = LibrarySidebar(app_context)
    called = []
    monkeypatch.setattr(LibrarySidebar, "_exec_menu", lambda self, menu, position: called.append(1))

    sidebar._show_collection_context_menu(_position_of_row(sidebar, 0))

    assert called == []  # "Tất cả tài liệu" is a pseudo-entry, not a real collection


def test_rename_collection_via_context_menu(qapp, app_context, monkeypatch):
    collection = _seed_collection(app_context)
    sidebar = LibrarySidebar(app_context)
    monkeypatch.setattr(LibrarySidebar, "_exec_menu", _pick_action_containing("Đổi tên"))
    monkeypatch.setattr(QInputDialog, "getText", staticmethod(lambda *a, **k: ("New Name", True)))

    sidebar._show_collection_context_menu(_position_of_row(sidebar, 1))

    assert app_context.db.get_collection(collection.id)["name"] == "New Name"
    assert sidebar.collections_list.item(1).text() == "New Name (0)"


def test_delete_collection_via_context_menu(qapp, app_context, monkeypatch):
    collection = _seed_collection(app_context)
    sidebar = LibrarySidebar(app_context)
    monkeypatch.setattr(LibrarySidebar, "_exec_menu", _pick_action_containing("Xóa bộ sưu tập"))
    monkeypatch.setattr(QMessageBox, "question", staticmethod(lambda *a, **k: QMessageBox.Yes))

    sidebar._show_collection_context_menu(_position_of_row(sidebar, 1))

    assert app_context.db.get_collection(collection.id) is None
    assert sidebar.collections_list.count() == 1


def test_edit_collection_rule_via_context_menu(qapp, app_context, monkeypatch):
    collection = _seed_collection(app_context)
    sidebar = LibrarySidebar(app_context)
    monkeypatch.setattr(LibrarySidebar, "_exec_menu", _pick_action_containing("Chỉnh sửa điều kiện"))
    monkeypatch.setattr(cd_module.NewCollectionDialog, "exec", lambda self: QDialog.Accepted)

    sidebar._show_collection_context_menu(_position_of_row(sidebar, 1))

    # Same id (upsert), rule value unchanged in this test (dialog wasn't
    # actually filled with new input) -- proves the edit path round-trips
    # through save_collection rather than creating a second row.
    assert len(app_context.db.list_collections()) == 1
    updated = app_context.db.get_collection(collection.id)
    assert updated is not None
    assert VirtualCollection.from_row(updated).rules[0].value == "AI"


def test_clicking_all_documents_clears_every_filter_including_the_search(qapp, app_context):
    """"Tất cả tài liệu" must mean all documents: previously it cleared only the
    collection and facets, so a search text silently kept the list filtered."""
    sidebar = LibrarySidebar(app_context)
    app_context.filters.set(LibraryFilter(tags=("AI",), authors=("A",), formats=("pdf",), query="abc"))

    sidebar._on_collection_clicked(sidebar.collections_list.item(0))  # "Tất cả tài liệu"

    assert app_context.filters.current == LibraryFilter()


def test_clicking_a_real_collection_keeps_the_other_filters(qapp, app_context):
    """Only "All" resets things -- selecting a collection narrows further with
    whatever hashtag/author/format filters are already active."""
    collection = _seed_collection(app_context)
    sidebar = LibrarySidebar(app_context)
    app_context.filters.set(LibraryFilter(tags=("AI",), formats=("pdf",)))

    sidebar._on_collection_clicked(sidebar.collections_list.item(1))  # the real collection

    assert app_context.filters.current == LibraryFilter(tags=("AI",), formats=("pdf",), collections=(collection.id,))


def _two_collections_with_members(app_context):
    from smartdoc.domain.smart_collections import VirtualCollection

    for i in range(3):
        app_context.db.add_or_update_document(
            f"d{i}", {"title": f"B{i}", "author": "A", "file_path": f"b{i}.pdf", "extension": "pdf", "created_at": float(i)}
        )
    first = VirtualCollection(name="Một", created_at=1.0)
    second = VirtualCollection(name="Hai", created_at=2.0)
    for collection in (first, second):
        app_context.db.save_collection(collection.id, collection.name, collection.to_json(), collection.logic, collection.created_at)
    app_context.db.add_documents_to_collection(first.id, ["d0"])
    app_context.db.add_documents_to_collection(second.id, ["d1"])
    return first, second


def test_a_plain_click_switches_to_that_collection(qapp, app_context):
    first, second = _two_collections_with_members(app_context)
    sidebar = LibrarySidebar(app_context)

    sidebar._on_collection_clicked(sidebar.collections_list.item(1))
    sidebar._on_collection_clicked(sidebar.collections_list.item(2))

    assert sidebar._selected_ids == (second.id,)
    assert not sidebar.collections_list.item(1).isSelected()
    assert sidebar.collections_list.item(2).isSelected()


def test_ctrl_click_combines_several_collections(qapp, app_context, monkeypatch):
    from smartdoc.presentation.library_view import LibraryListWidget

    first, second = _two_collections_with_members(app_context)
    sidebar = LibrarySidebar(app_context)
    library = LibraryListWidget(app_context)
    monkeypatch.setattr(LibrarySidebar, "_additive_click", lambda self: True)
    events = []
    app_context.event_bus.subscribe(FilterChangedEvent, lambda e: events.append(e))

    sidebar._on_collection_clicked(sidebar.collections_list.item(1))
    sidebar._on_collection_clicked(sidebar.collections_list.item(2))
    qapp.processEvents()

    assert set(events[-1].filter.collections) == {first.id, second.id}
    shown = sorted(library.model.document_at(r)["id"] for r in range(library.model.rowCount()))
    assert shown == ["d0", "d1"]  # union of both collections
    assert sidebar.collections_list.item(1).isSelected() and sidebar.collections_list.item(2).isSelected()


def test_clicking_the_only_selected_collection_again_deselects_it(qapp, app_context):
    _two_collections_with_members(app_context)
    sidebar = LibrarySidebar(app_context)

    sidebar._on_collection_clicked(sidebar.collections_list.item(1))
    sidebar._on_collection_clicked(sidebar.collections_list.item(1))

    assert sidebar._selected_ids == ()
    assert sidebar.collections_list.item(0).isSelected()  # nothing selected -> "Tất cả" is highlighted


def test_ctrl_click_on_a_selected_collection_removes_just_that_one(qapp, app_context, monkeypatch):
    first, second = _two_collections_with_members(app_context)
    sidebar = LibrarySidebar(app_context)
    monkeypatch.setattr(LibrarySidebar, "_additive_click", lambda self: True)

    sidebar._on_collection_clicked(sidebar.collections_list.item(1))
    sidebar._on_collection_clicked(sidebar.collections_list.item(2))
    sidebar._on_collection_clicked(sidebar.collections_list.item(1))

    assert sidebar._selected_ids == (second.id,)


def test_collection_counts_follow_the_other_filters(qapp, app_context):
    """A collection's number is "how many if I pick it" under the other filters."""
    _two_collections_with_members(app_context)
    app_context.db.update_document_fields("d0", {"tags": "AI"})
    sidebar = LibrarySidebar(app_context)
    assert sidebar.collections_list.item(1).text() == "Một (1)"

    app_context.filters.set(LibraryFilter(tags=("AI",)))

    assert sidebar.collections_list.item(1).text() == "Một (1)"  # d0 has the tag
    assert sidebar.collections_list.item(2).text() == "Hai (0)"  # d1 does not


def test_deleting_the_selected_collection_drops_it_from_the_filter(qapp, app_context, monkeypatch):
    _seed_collection(app_context)
    sidebar = LibrarySidebar(app_context)
    sidebar._on_collection_clicked(sidebar.collections_list.item(1))
    monkeypatch.setattr(LibrarySidebar, "_exec_menu", _pick_action_containing("Xóa bộ sưu tập"))
    monkeypatch.setattr(QMessageBox, "question", staticmethod(lambda *a, **k: QMessageBox.Yes))

    sidebar._show_collection_context_menu(_position_of_row(sidebar, 1))

    assert app_context.filters.current.collections == ()


def test_a_collection_made_from_a_filter_cannot_be_edited_in_the_one_rule_dialog(qapp, app_context, monkeypatch):
    collection = VirtualCollection(
        name="Nhiều điều kiện",
        rules=[
            SmartRule(field="author", operator="has_author", value="A"),
            SmartRule(field="tags", operator="has_tag", value="AI"),
        ],
    )
    app_context.db.save_collection(
        collection.id, collection.name, collection.to_json(), collection.logic, collection.created_at
    )
    sidebar = LibrarySidebar(app_context)
    seen = []

    def fake_exec_menu(self, menu, _position):
        seen.extend((a.text(), a.isEnabled()) for a in menu.actions())

    monkeypatch.setattr(LibrarySidebar, "_exec_menu", fake_exec_menu)
    sidebar._show_collection_context_menu(_position_of_row(sidebar, 1))

    assert ("Chỉnh sửa điều kiện", False) in seen
    assert ("Đổi tên", True) in seen
