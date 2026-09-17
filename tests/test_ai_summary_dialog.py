import time

from smartdoc.application.ai_summary import AISummaryError
from smartdoc.core.event_bus import LibraryUpdatedEvent
from smartdoc.presentation.ai_summary_dialog import AISummaryDialog


def _pump_until(qapp, predicate, timeout: float = 3.0) -> bool:
    deadline = time.time() + timeout
    while time.time() < deadline:
        qapp.processEvents()
        if predicate():
            return True
        time.sleep(0.02)
    qapp.processEvents()
    return predicate()


def _doc(**overrides) -> dict:
    base = {"id": "d1", "title": "The Hobbit", "author": "Tolkien"}
    base.update(overrides)
    return base


def test_not_configured_disables_generate_button_and_shows_message(qapp, app_context):
    app_context.config.config.ai_provider = None
    app_context.config.config.ai_api_key = None

    dialog = AISummaryDialog(app_context, _doc())

    assert not dialog.generate_button.isEnabled()
    assert "Chưa cấu hình" in dialog.status_label.text()


def test_existing_summary_is_preloaded_and_save_enabled(qapp, app_context):
    dialog = AISummaryDialog(app_context, _doc(ai_summary="An existing summary."))
    assert dialog.summary_edit.toPlainText() == "An existing summary."
    assert dialog.save_button.isEnabled()


def test_no_existing_summary_disables_save_initially(qapp, app_context):
    dialog = AISummaryDialog(app_context, _doc())
    assert not dialog.save_button.isEnabled()


def test_generate_success_populates_text_and_enables_save(qapp, app_context, monkeypatch):
    app_context.config.config.ai_provider = "gemini"
    app_context.config.config.ai_api_key = "fake-key"
    monkeypatch.setattr(
        "smartdoc.presentation.ai_summary_dialog.generate_summary",
        lambda provider, key, doc: "A cozy fantasy adventure.",
    )

    dialog = AISummaryDialog(app_context, _doc())
    dialog._on_generate()

    assert _pump_until(qapp, lambda: dialog.summary_edit.toPlainText() != "")
    assert dialog.summary_edit.toPlainText() == "A cozy fantasy adventure."
    assert dialog.save_button.isEnabled()
    assert dialog.generate_button.isEnabled()


def test_generate_error_shown_in_status_label(qapp, app_context, monkeypatch):
    app_context.config.config.ai_provider = "gemini"
    app_context.config.config.ai_api_key = "fake-key"

    def raise_error(provider, key, doc):
        raise AISummaryError("boom")

    monkeypatch.setattr("smartdoc.presentation.ai_summary_dialog.generate_summary", raise_error)

    dialog = AISummaryDialog(app_context, _doc())
    dialog._on_generate()

    assert _pump_until(qapp, lambda: "boom" in dialog.status_label.text())
    assert not dialog.save_button.isEnabled()


def test_save_persists_to_db_and_publishes_event(qapp, app_context):
    app_context.db.add_or_update_document(
        "d1", {"title": "The Hobbit", "author": "Tolkien", "file_path": "a.pdf", "created_at": 0.0}
    )
    events = []
    app_context.event_bus.subscribe(LibraryUpdatedEvent, lambda e: events.append(e))

    dialog = AISummaryDialog(app_context, _doc())
    dialog.summary_edit.setPlainText("A generated summary.")
    dialog._on_save()

    assert app_context.db.get_document("d1")["ai_summary"] == "A generated summary."
    assert len(events) == 1
    assert "Đã lưu" in dialog.status_label.text()


def test_save_with_empty_text_does_nothing(qapp, app_context):
    app_context.db.add_or_update_document(
        "d1", {"title": "The Hobbit", "author": "Tolkien", "file_path": "a.pdf", "created_at": 0.0}
    )
    events = []
    app_context.event_bus.subscribe(LibraryUpdatedEvent, lambda e: events.append(e))

    dialog = AISummaryDialog(app_context, _doc())
    dialog._on_save()

    assert app_context.db.get_document("d1")["ai_summary"] is None
    assert events == []
