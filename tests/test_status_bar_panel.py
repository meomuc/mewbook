from smartdoc.core.event_bus import CollectionSelectedEvent, LibraryUpdatedEvent
from smartdoc.domain.smart_collections import SmartRule, VirtualCollection
from smartdoc.presentation.status_bar_panel import StatusBarPanel


def _pump_until(qapp, predicate, timeout: float = 3.0) -> bool:
    import time

    deadline = time.time() + timeout
    while time.time() < deadline:
        qapp.processEvents()
        if predicate():
            return True
        time.sleep(0.02)
    return predicate()


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


def test_cloud_label_colors_function_name_and_status_differently(qapp, app_context):
    panel = StatusBarPanel(app_context)

    not_connected_html = panel.cloud_label.text()
    assert "color:crimson" in not_connected_html
    assert "Review" in not_connected_html  # the function name, styled separately

    app_context.config.config.supabase_url = "https://fake.supabase.co"
    app_context.config.config.supabase_anon_key = "fake-key"
    panel.refresh()

    assert "color:green" in panel.cloud_label.text()


def test_status_bar_has_a_top_border_separating_it_from_the_panel_above(qapp, app_context):
    panel = StatusBarPanel(app_context)
    assert "border-top" in panel.styleSheet()


def test_author_credit_is_always_shown(qapp, app_context):
    panel = StatusBarPanel(app_context)
    assert panel.author_label.text() == "Dev:AnhTienSinh"


def test_donate_ticker_is_shown_and_scrolls(qapp, app_context):
    panel = StatusBarPanel(app_context)
    first_frame = panel.donate_ticker.text()
    assert first_frame  # some text is already showing, not blank until the timer first fires

    panel.donate_ticker._tick()
    assert panel.donate_ticker.text() != first_frame  # ticker actually advances


def test_clicking_donate_ticker_opens_donate_dialog(qapp, app_context, monkeypatch):
    opened = []
    monkeypatch.setattr(
        "smartdoc.presentation.status_bar_panel.DonateDialog",
        lambda parent=None: type("_Fake", (), {"exec": lambda self: opened.append(True)})(),
    )
    panel = StatusBarPanel(app_context)

    panel.donate_ticker.clicked.emit()

    assert opened == [True]


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

    assert _pump_until(qapp, lambda: "1 tài liệu" in panel.files_label.text())


def test_a_burst_of_library_updates_refreshes_only_once(qapp, app_context, monkeypatch):
    """A bulk import publishes one LibraryUpdatedEvent per file -- the status
    bar must coalesce them rather than recount the library each time."""
    panel = StatusBarPanel(app_context)
    calls = []
    original_refresh = panel.refresh
    monkeypatch.setattr(panel, "refresh", lambda: (calls.append(1), original_refresh()))
    panel._refresh_timer.timeout.disconnect()
    panel._refresh_timer.timeout.connect(panel.refresh)

    for _ in range(40):
        app_context.event_bus.publish(LibraryUpdatedEvent())

    assert _pump_until(qapp, lambda: len(calls) >= 1)
    assert len(calls) == 1
