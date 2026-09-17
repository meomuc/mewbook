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


def test_request_content_is_prefilled_with_title_and_author(qapp, app_context):
    dialog = AISummaryDialog(app_context, _doc(title="The Hobbit", author="Tolkien"))
    text = dialog.request_content_edit.toPlainText()
    assert "The Hobbit" in text
    assert "Tolkien" in text


def test_request_content_includes_full_extracted_text_uncapped(qapp, app_context):
    long_content = "word " * 5000
    dialog = AISummaryDialog(app_context, _doc(content=long_content))
    assert long_content.strip() in dialog.request_content_edit.toPlainText()


def test_generate_success_populates_text_and_enables_save(qapp, app_context, monkeypatch):
    app_context.config.config.ai_provider = "gemini"
    app_context.config.config.ai_api_key = "fake-key"
    monkeypatch.setattr(
        "smartdoc.presentation.ai_summary_dialog.generate_summary_from_content",
        lambda provider, key, content: "A cozy fantasy adventure.",
    )

    dialog = AISummaryDialog(app_context, _doc())
    dialog._on_generate()

    assert _pump_until(qapp, lambda: dialog.summary_edit.toPlainText() != "")
    assert dialog.summary_edit.toPlainText() == "A cozy fantasy adventure."
    assert dialog.save_button.isEnabled()
    assert dialog.generate_button.isEnabled()


def test_generate_sends_the_edited_request_content(qapp, app_context, monkeypatch):
    app_context.config.config.ai_provider = "gemini"
    app_context.config.config.ai_api_key = "fake-key"
    captured = {}

    def fake_generate(provider, key, content):
        captured["content"] = content
        return "summary"

    monkeypatch.setattr("smartdoc.presentation.ai_summary_dialog.generate_summary_from_content", fake_generate)

    dialog = AISummaryDialog(app_context, _doc())
    dialog.request_content_edit.setPlainText("My custom edited request")
    dialog._on_generate()

    assert _pump_until(qapp, lambda: "content" in captured)
    assert captured["content"] == "My custom edited request"


def test_generate_error_shown_in_status_label(qapp, app_context, monkeypatch):
    app_context.config.config.ai_provider = "gemini"
    app_context.config.config.ai_api_key = "fake-key"

    def raise_error(provider, key, content):
        raise AISummaryError("boom")

    monkeypatch.setattr("smartdoc.presentation.ai_summary_dialog.generate_summary_from_content", raise_error)

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
