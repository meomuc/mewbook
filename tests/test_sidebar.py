from PySide6.QtWidgets import QDialog

from smartdoc.core.event_bus import CollectionSelectedEvent
from smartdoc.domain.smart_collections import SmartRule, VirtualCollection
from smartdoc.presentation import collection_dialog as cd_module
from smartdoc.presentation.sidebar import LibrarySidebar


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
