import io
import time

from PIL import Image

from smartdoc.application.cover_search import CoverSearchResult
from smartdoc.core.event_bus import LibraryUpdatedEvent
from smartdoc.presentation.cover_search_dialog import CoverSearchDialog


def _pump_until(qapp, predicate, timeout: float = 3.0) -> bool:
    deadline = time.time() + timeout
    while time.time() < deadline:
        qapp.processEvents()
        if predicate():
            return True
        time.sleep(0.02)
    qapp.processEvents()
    return predicate()


def _fake_png_bytes() -> bytes:
    buf = io.BytesIO()
    Image.new("RGB", (10, 15), color=(20, 40, 60)).save(buf, format="PNG")
    return buf.getvalue()


def _doc():
    return {"id": "d1", "title": "The Hobbit", "author": "J.R.R. Tolkien"}


def test_search_populates_results_with_thumbnails(qapp, app_context, monkeypatch):
    candidates = [
        CoverSearchResult(
            image_url="https://example.com/cover.jpg", title="The Hobbit", author="Tolkien", year=1937, source="Open Library"
        )
    ]
    monkeypatch.setattr("smartdoc.presentation.cover_search_dialog.search_covers", lambda t, a: candidates)
    monkeypatch.setattr(
        "smartdoc.presentation.cover_search_dialog.download_cover_image", lambda result: _fake_png_bytes()
    )

    dialog = CoverSearchDialog(app_context, _doc())

    assert _pump_until(qapp, lambda: dialog.results_list.count() > 0)
    assert "The Hobbit" in dialog.results_list.item(0).text()
    assert "1937" in dialog.results_list.item(0).text()


def test_no_results_shows_status_message(qapp, app_context, monkeypatch):
    monkeypatch.setattr("smartdoc.presentation.cover_search_dialog.search_covers", lambda t, a: [])

    dialog = CoverSearchDialog(app_context, _doc())

    assert _pump_until(qapp, lambda: "Không tìm thấy" in dialog.status_label.text())


def test_selecting_a_result_enables_use_button(qapp, app_context, monkeypatch):
    candidates = [
        CoverSearchResult(
            image_url="https://example.com/cover.jpg", title="The Hobbit", author="Tolkien", year=1937, source="Open Library"
        )
    ]
    monkeypatch.setattr("smartdoc.presentation.cover_search_dialog.search_covers", lambda t, a: candidates)
    monkeypatch.setattr(
        "smartdoc.presentation.cover_search_dialog.download_cover_image", lambda result: _fake_png_bytes()
    )

    dialog = CoverSearchDialog(app_context, _doc())
    assert _pump_until(qapp, lambda: dialog.results_list.count() > 0)
    assert not dialog.use_button.isEnabled()

    dialog.results_list.setCurrentRow(0)
    assert dialog.use_button.isEnabled()


def test_using_selected_cover_saves_it_and_publishes_event(qapp, app_context, monkeypatch, tmp_path):
    app_context.config.config.cover_cache_dir = str(tmp_path)
    app_context.db.add_or_update_document(
        "d1", {"title": "The Hobbit", "author": "Tolkien", "file_path": "hobbit.pdf", "created_at": 0.0}
    )
    candidates = [
        CoverSearchResult(
            image_url="https://example.com/cover.jpg", title="The Hobbit", author="Tolkien", year=1937, source="Open Library"
        )
    ]
    monkeypatch.setattr("smartdoc.presentation.cover_search_dialog.search_covers", lambda t, a: candidates)
    monkeypatch.setattr(
        "smartdoc.presentation.cover_search_dialog.download_cover_image", lambda result: _fake_png_bytes()
    )

    events = []
    app_context.event_bus.subscribe(LibraryUpdatedEvent, lambda e: events.append(e))

    dialog = CoverSearchDialog(app_context, app_context.db.get_document("d1"))
    assert _pump_until(qapp, lambda: dialog.results_list.count() > 0)
    dialog.results_list.setCurrentRow(0)

    dialog._on_use_selected()

    assert len(events) == 1
    doc = app_context.db.get_document("d1")
    assert doc["cover_path"] is not None
    from pathlib import Path

    assert Path(doc["cover_path"]).exists()
