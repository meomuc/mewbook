"""Tests for the Document Detail Side Panel."""
import time

from PySide6.QtCore import QSize

from smartdoc.core.event_bus import DocumentSelectedEvent, LibraryUpdatedEvent
from smartdoc.presentation.detail_panel import (
    DocumentDetailPanel,
    _format_datetime,
    _human_size,
    _rating_text,
)


def _pump_until(qapp, predicate, timeout: float = 3.0) -> bool:
    deadline = time.time() + timeout
    while time.time() < deadline:
        qapp.processEvents()
        if predicate():
            return True
        time.sleep(0.02)
    qapp.processEvents()
    return predicate()


def _sample_doc(**overrides) -> dict:
    base = {
        "id": "d1",
        "title": "Python Cơ Bản",
        "author": "Nguyễn Văn A",
        "file_path": "C:/Books/python.pdf",
        "file_size": 15_500_000,
        "extension": "pdf",
        "tags": "Python,Lập trình",
        "created_at": 1700000000.0,
        "updated_at": 1700003600.0,
        "avg_rating": 4.5,
        "review_count": 12,
        "cover_path": None,
        "ai_summary": None,
    }
    base.update(overrides)
    return base


# ── Pure formatting helpers ──────────────────────────────────────────


def test_human_size_formats_megabytes():
    assert _human_size(15_500_000) == "14.8 MB"


def test_human_size_formats_kilobytes():
    assert _human_size(1024) == "1.0 KB"


def test_human_size_formats_zero():
    assert _human_size(0) == "0 B"


def test_format_datetime_returns_dash_for_none():
    assert _format_datetime(None) == "—"


def test_format_datetime_formats_a_timestamp():
    result = _format_datetime(1700000000.0)
    assert "/" in result  # date formatted with slashes


def test_rating_text_shows_stars_when_rated():
    doc = _sample_doc(avg_rating=4.5, review_count=12)
    text = _rating_text(doc)
    assert "4.5" in text and "★" in text and "12" in text


def test_rating_text_shows_placeholder_when_unrated():
    doc = _sample_doc(avg_rating=None, review_count=0)
    assert "Chưa" in _rating_text(doc)


# ── Widget tests ─────────────────────────────────────────────────────
# Qt's isVisible() returns False for widgets whose top-level parent
# window has never been shown (even if .show() was called on the child).
# In headless tests we use isHidden() or isVisibleTo(parent) instead,
# which reflect the widget's *own* visibility state regardless of the
# parent chain.


def test_panel_starts_in_empty_state(qapp, app_context):
    panel = DocumentDetailPanel(app_context)
    # Empty label should NOT be hidden; scroll area SHOULD be hidden
    assert not panel._empty_label.isHidden()
    assert panel._scroll.isHidden()


def test_set_document_shows_content(qapp, app_context):
    panel = DocumentDetailPanel(app_context)
    panel.set_document(_sample_doc())

    assert not panel._scroll.isHidden()
    assert panel._empty_label.isHidden()
    assert "Python Cơ Bản" in panel.title_edit.text()
    assert "Nguyễn Văn A" in panel.author_edit.text()


def test_set_document_none_returns_to_empty(qapp, app_context):
    panel = DocumentDetailPanel(app_context)
    panel.set_document(_sample_doc())
    assert not panel._scroll.isHidden()

    panel.set_document(None)
    assert not panel._empty_label.isHidden()
    assert panel._scroll.isHidden()


def test_panel_shows_rating_info(qapp, app_context):
    panel = DocumentDetailPanel(app_context)
    panel.set_document(_sample_doc(avg_rating=3.8, review_count=5))
    assert "3.8" in panel.rating_label.text()


def test_panel_shows_format_and_size(qapp, app_context):
    panel = DocumentDetailPanel(app_context)
    panel.set_document(_sample_doc(extension="epub", file_size=2_000_000))
    text = panel.format_size_label.text()
    assert "EPUB" in text
    assert "MB" in text


def test_panel_shows_tags_as_badges(qapp, app_context):
    panel = DocumentDetailPanel(app_context)
    panel.set_document(_sample_doc(tags="AI,ML,Deep Learning"))
    assert not panel._tags_container.isHidden()
    # Count the tag badges in the flow layout
    assert panel._tags_layout.count() == 3


def test_panel_shows_tags_hashtag_styled(qapp, app_context):
    from PySide6.QtWidgets import QLabel

    panel = DocumentDetailPanel(app_context)
    panel.set_document(_sample_doc(tags="Python,AI"))

    labels = panel._tags_container.findChildren(QLabel)
    texts = {label.text() for label in labels}
    assert "#Python" in texts
    assert "#AI" in texts


def test_tags_section_header_is_hashtag_not_the_loai(qapp, app_context):
    panel = DocumentDetailPanel(app_context)
    assert panel.tags_title_label.text() == "Hashtag"


def test_clicking_a_hashtag_resets_collection_and_filters_by_tag(qapp, app_context):
    from smartdoc.core.event_bus import CollectionSelectedEvent, FacetFilterChangedEvent

    panel = DocumentDetailPanel(app_context)
    panel.set_document(_sample_doc(tags="Python,AI"))

    collection_events = []
    facet_events = []
    app_context.event_bus.subscribe(CollectionSelectedEvent, lambda e: collection_events.append(e))
    app_context.event_bus.subscribe(FacetFilterChangedEvent, lambda e: facet_events.append(e))

    panel._on_tag_clicked("Python")

    assert collection_events[-1].collection_id is None
    assert facet_events[-1].tags == ("Python",)


def test_panel_hides_tags_when_none(qapp, app_context):
    panel = DocumentDetailPanel(app_context)
    panel.set_document(_sample_doc(tags=""))
    assert panel._tags_container.isHidden()


def test_panel_shows_generate_link_when_no_summary_yet(qapp, app_context):
    panel = DocumentDetailPanel(app_context)
    panel.set_document(_sample_doc(ai_summary=None))
    # The section header + "generate" link stay visible even with no summary
    # yet -- that link is how the user creates one in the first place.
    assert not panel.summary_title_label.isHidden()
    assert panel.summary_label.isHidden()
    assert "Tạo tóm tắt AI" in panel.ai_summary_action_label.text()


def test_panel_shows_ai_summary_when_present(qapp, app_context):
    panel = DocumentDetailPanel(app_context)
    panel.set_document(_sample_doc(ai_summary="A great book about Python."))
    assert not panel.summary_title_label.isHidden()
    assert "great book" in panel.summary_label.text()
    assert "Tạo lại" in panel.ai_summary_action_label.text()


def test_clicking_ai_summary_link_opens_ai_summary_dialog(qapp, app_context, monkeypatch):
    opened_docs = []

    class _FakeDialog:
        def __init__(self, context, doc, parent=None):
            opened_docs.append(doc)

        def exec(self):
            return 1

    monkeypatch.setattr("smartdoc.presentation.detail_panel.AISummaryDialog", _FakeDialog)
    panel = DocumentDetailPanel(app_context)
    panel.set_document(_sample_doc())

    panel.ai_summary_action_label.clicked.emit()

    assert len(opened_docs) == 1
    assert opened_docs[0]["id"] == "d1"


def test_document_selected_event_updates_panel(qapp, app_context):
    panel = DocumentDetailPanel(app_context)
    doc = _sample_doc()
    app_context.event_bus.publish(DocumentSelectedEvent(doc=doc))
    assert _pump_until(qapp, lambda: not panel._scroll.isHidden(), timeout=3.0)
    assert "Python Cơ Bản" in panel.title_edit.text()


def test_document_selected_event_none_clears_panel(qapp, app_context):
    panel = DocumentDetailPanel(app_context)
    panel.set_document(_sample_doc())
    assert not panel._scroll.isHidden()

    app_context.event_bus.publish(DocumentSelectedEvent(doc=None))
    assert _pump_until(qapp, lambda: panel._scroll.isHidden(), timeout=3.0)


def test_library_updated_event_refreshes_panel(qapp, app_context):
    app_context.db.add_or_update_document(
        "d1",
        {"title": "Old Title", "author": "A", "file_path": "a.pdf", "created_at": 1.0},
    )
    panel = DocumentDetailPanel(app_context)
    doc = app_context.db.get_document("d1")
    panel.set_document(doc)
    assert "Old Title" in panel.title_edit.text()

    # Update the title in the DB, then fire the event
    app_context.db.update_document_fields("d1", {"title": "New Title"})
    app_context.event_bus.publish(LibraryUpdatedEvent())

    assert _pump_until(qapp, lambda: "New Title" in panel.title_edit.text(), timeout=3.0)


def test_truncated_file_path_shows_tooltip(qapp, app_context):
    long_path = "C:/Users/someone/Documents/Very/Long/Path/To/A/Book/" + "a" * 50 + ".pdf"
    panel = DocumentDetailPanel(app_context)
    panel.set_document(_sample_doc(file_path=long_path))
    # Tooltip should contain the full path
    assert long_path in panel.path_label.toolTip()


# ── Inline editing / click-through actions (replaces the old button row) ──


def test_editing_title_inline_saves_to_db_and_publishes_event(qapp, app_context):
    app_context.db.add_or_update_document(
        "d1", {"title": "Old Title", "author": "A", "file_path": "a.pdf", "created_at": 1.0}
    )
    panel = DocumentDetailPanel(app_context)
    panel.set_document(app_context.db.get_document("d1"))

    events = []
    app_context.event_bus.subscribe(LibraryUpdatedEvent, lambda e: events.append(e))

    panel.title_edit.setText("Brand New Title")
    panel.title_edit.editingFinished.emit()

    assert app_context.db.get_document("d1")["title"] == "Brand New Title"
    assert len(events) == 1


def test_editing_title_to_unchanged_value_does_not_publish_event(qapp, app_context):
    app_context.db.add_or_update_document(
        "d1", {"title": "Same Title", "author": "A", "file_path": "a.pdf", "created_at": 1.0}
    )
    panel = DocumentDetailPanel(app_context)
    panel.set_document(app_context.db.get_document("d1"))

    events = []
    app_context.event_bus.subscribe(LibraryUpdatedEvent, lambda e: events.append(e))

    panel.title_edit.editingFinished.emit()  # no change made

    assert events == []


def test_clicking_cover_opens_the_reader_window(qapp, app_context, monkeypatch):
    opened_docs = []

    class _FakeReaderWindow:
        def __init__(self, context, doc, parent=None):
            opened_docs.append(doc)

        def show(self):
            pass

    monkeypatch.setattr("smartdoc.presentation.detail_panel.ReaderWindow", _FakeReaderWindow)
    panel = DocumentDetailPanel(app_context)
    panel.set_document(_sample_doc(file_path="C:/Books/python.pdf"))

    panel.cover_label.clicked.emit()

    assert len(opened_docs) == 1
    assert opened_docs[0]["file_path"] == "C:/Books/python.pdf"


def test_clicking_path_reveals_in_file_manager(qapp, app_context, monkeypatch):
    revealed = []
    panel = DocumentDetailPanel(app_context)
    monkeypatch.setattr(panel.file_actions, "show_in_file_manager", lambda path: revealed.append(path))
    panel.set_document(_sample_doc(file_path="C:/Books/python.pdf"))

    panel.path_label.clicked.emit()

    assert revealed == ["C:/Books/python.pdf"]


def test_clicking_cover_search_link_opens_cover_search_dialog(qapp, app_context, monkeypatch):
    opened_docs = []

    class _FakeDialog:
        def __init__(self, context, doc, parent=None):
            opened_docs.append(doc)

        def exec(self):
            return 1

    monkeypatch.setattr("smartdoc.presentation.detail_panel.CoverSearchDialog", _FakeDialog)
    panel = DocumentDetailPanel(app_context)
    panel.set_document(_sample_doc())

    panel.cover_search_label.clicked.emit()

    assert len(opened_docs) == 1
    assert opened_docs[0]["id"] == "d1"
