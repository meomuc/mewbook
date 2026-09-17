from smartdoc.core.event_bus import CollectionSelectedEvent, LibraryUpdatedEvent
from smartdoc.domain.smart_collections import SmartRule, VirtualCollection
from smartdoc.presentation.status_bar_panel import StatusBarPanel


def test_files_label_shows_total_and_completeness_counts(qapp, app_context):
    app_context.db.add_or_update_document(
        "complete",
        {"title": "A", "author": "Real Author", "file_path": "a.pdf", "cover_path": "a.webp", "created_at": 0.0},
    )
    app_context.db.add_or_update_document(
        "incomplete", {"title": "B", "author": "Unknown", "file_path": "b.pdf", "created_at": 0.0}
    )

    panel = StatusBarPanel(app_context)

    assert "2 tài liệu" in panel.files_label.text()
    assert "1 đủ thông tin" in panel.files_label.text()
    assert "1 thiếu thông tin" in panel.files_label.text()


def test_folders_label_shows_watch_folder_count(qapp, app_context):
    app_context.config.add_watch_folder(r"D:\Ebooks")
    app_context.config.add_watch_folder(r"D:\Books2")

    panel = StatusBarPanel(app_context)

    assert "2 thư mục" in panel.folders_label.text()


def test_cloud_label_reflects_supabase_configuration(qapp, app_context):
    panel = StatusBarPanel(app_context)
    assert "✗" in panel.cloud_label.text()

    app_context.config.config.supabase_url = "https://fake.supabase.co"
    app_context.config.config.supabase_anon_key = "fake-key"
    panel.refresh()
    assert "✓" in panel.cloud_label.text()


def test_ai_label_reflects_ai_configuration(qapp, app_context):
    panel = StatusBarPanel(app_context)
    assert "✗" in panel.ai_label.text()

    app_context.config.config.ai_provider = "gemini"
    app_context.config.config.ai_api_key = "fake-key"
    panel.refresh()
    assert "✓" in panel.ai_label.text()


def test_author_credit_is_always_shown(qapp, app_context):
    panel = StatusBarPanel(app_context)
    assert panel.author_label.text() == "anhtiensinh"


def test_collection_label_empty_when_no_collection_selected(qapp, app_context):
    panel = StatusBarPanel(app_context)
    assert panel.collection_label.text() == ""


def test_collection_label_updates_on_collection_selected_event(qapp, app_context):
    app_context.db.add_or_update_document(
        "d1", {"title": "A", "author": "X", "file_path": "a.pdf", "extension": "pdf", "created_at": 0.0}
    )
    collection = VirtualCollection(name="PDFs", rules=[SmartRule(field="extension", operator="eq", value="pdf")])
    app_context.db.save_collection(
        collection.id, collection.name, collection.to_json(), collection.logic, collection.created_at
    )
    panel = StatusBarPanel(app_context)

    app_context.event_bus.publish(CollectionSelectedEvent(collection_id=collection.id))

    assert "PDFs" in panel.collection_label.text()
    assert "1 tài liệu" in panel.collection_label.text()

    app_context.event_bus.publish(CollectionSelectedEvent(collection_id=None))
    assert panel.collection_label.text() == ""


def test_refreshes_on_library_updated_event(qapp, app_context):
    panel = StatusBarPanel(app_context)
    assert "0 tài liệu" in panel.files_label.text()

    app_context.db.add_or_update_document("d1", {"title": "A", "author": "X", "file_path": "a.pdf", "created_at": 0.0})
    app_context.event_bus.publish(LibraryUpdatedEvent())

    assert "1 tài liệu" in panel.files_label.text()
