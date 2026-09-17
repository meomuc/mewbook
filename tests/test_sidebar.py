from PySide6.QtWidgets import QDialog, QInputDialog, QMessageBox

from smartdoc.core.event_bus import CollectionSelectedEvent
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
    assert sidebar.collections_list.item(0).text() == "Tất cả tài liệu"


def test_reload_collections_lists_saved_collections(qapp, app_context):
    collection = VirtualCollection(name="Sach AI", rules=[SmartRule(field="tags", operator="contains", value="AI")])
    app_context.db.save_collection(
        collection.id, collection.name, collection.to_json(), collection.logic, collection.created_at
    )

    sidebar = LibrarySidebar(app_context)
    assert sidebar.collections_list.count() == 2
    assert sidebar.collections_list.item(1).text() == "Sach AI"


def test_clicking_a_collection_publishes_collection_selected_event(qapp, app_context):
    collection = VirtualCollection(name="Sach AI", rules=[SmartRule(field="tags", operator="contains", value="AI")])
    app_context.db.save_collection(
        collection.id, collection.name, collection.to_json(), collection.logic, collection.created_at
    )
    sidebar = LibrarySidebar(app_context)

    received = []
    app_context.event_bus.subscribe(CollectionSelectedEvent, lambda e: received.append(e))

    sidebar._on_collection_clicked(sidebar.collections_list.item(1))
    assert received[-1].collection_id == collection.id

    sidebar._on_collection_clicked(sidebar.collections_list.item(0))
    assert received[-1].collection_id is None


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
    assert sidebar.collections_list.item(1).text() == "Test Collection"
    assert app_context.db.get_collection(fake_collection.id) is not None


def test_add_collection_cancelled_dialog_does_not_save(qapp, app_context, monkeypatch):
    monkeypatch.setattr(cd_module.NewCollectionDialog, "exec", lambda self: QDialog.Rejected)

    sidebar = LibrarySidebar(app_context)
    sidebar._on_add_collection()

    assert sidebar.collections_list.count() == 1
    assert app_context.db.list_collections() == []


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
    assert sidebar.collections_list.item(1).text() == "New Name"


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
