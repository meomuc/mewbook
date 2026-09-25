"""Tests for the Document Detail Side Panel."""
import time

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
    assert "3,8" in panel.rating_label.text() and "5 đánh giá" in panel.rating_label.text()


def test_panel_shows_format_and_size(qapp, app_context):
    panel = DocumentDetailPanel(app_context)
    panel.set_document(_sample_doc(extension="epub", file_size=2_000_000))
    text = panel.format_size_label.text()
    assert "EPUB" in text
    assert "MB" in text


def test_panel_shows_tags_as_removable_chips(qapp, app_context):
    panel = DocumentDetailPanel(app_context)
    panel.set_document(_sample_doc(tags="AI,ML,Deep Learning"))
    assert panel.tag_editor.tags() == ["AI", "ML", "Deep Learning"]
    assert len(panel.tag_editor._chips) == 3
    assert [chip.label.text() for chip in panel.tag_editor._chips] == ["#AI", "#ML", "#Deep Learning"]


def test_tags_section_header_is_hashtag(qapp, app_context):
    panel = DocumentDetailPanel(app_context)
    assert panel.tags_title_label.text() == "Hashtag"


def test_title_and_author_use_content_font_settings_not_app_font(qapp, app_context):
    app_context.config.config.content_font_size = 24
    app_context.config.config.content_text_color = "#00ff00"

    panel = DocumentDetailPanel(app_context)

    assert panel.title_edit.font().pixelSize() == 27  # the heading: content size + _TITLE_STEP_PX
    assert panel.author_edit.font().pixelSize() == 24
    assert "#00ff00" in panel.title_edit.styleSheet() and "#00ff00" in panel.author_edit.styleSheet()


def test_clicking_a_hashtag_replaces_the_whole_filter_with_that_tag(qapp, app_context):
    from smartdoc.domain.library_filter import LibraryFilter

    panel = DocumentDetailPanel(app_context)
    panel.set_document(_sample_doc(tags="Python,AI"))
    app_context.filters.set(LibraryFilter(collections=("c1",), authors=("Ai đó",), formats=("pdf",), query="abc"))

    panel._on_tag_clicked("Python")

    assert app_context.filters.current == LibraryFilter(tags=("Python",))


def test_a_book_without_hashtags_shows_only_the_add_control(qapp, app_context):
    panel = DocumentDetailPanel(app_context)
    panel.set_document(_sample_doc(tags=""))
    assert panel.tag_editor.tags() == [] and not panel.tag_editor.add_button.isHidden()


def test_hashtags_are_added_and_removed_in_place_and_saved(qapp, app_context):
    app_context.db.add_or_update_document(
        "d1", {"title": "A", "author": "B", "file_path": "a.pdf", "tags": "x", "created_at": 1.0})
    panel = DocumentDetailPanel(app_context)
    panel.set_document(dict(app_context.db.get_document("d1")))

    panel.tag_editor.add_button.click()
    panel.tags_edit.setText("#Python, AI, x")  # "x" is already there: not added twice
    panel.tags_edit.returnPressed.emit()
    assert app_context.db.get_document("d1")["tags"] == "x,Python,AI"

    panel.tag_editor._chips[0].remove_button.click()
    assert app_context.db.get_document("d1")["tags"] == "Python,AI"


def test_panel_shows_generate_link_when_no_summary_yet(qapp, app_context):
    panel = DocumentDetailPanel(app_context)
    panel.set_document(_sample_doc(ai_summary=None))
    # The section header + "generate" link stay visible even with no summary
    # yet -- that link is how the user creates one in the first place.
    assert not panel.summary_title_label.isHidden()
    assert panel.summary_label.isHidden()
    assert "Tạo tóm tắt" in panel.ai_summary_action_label.text()


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


def test_refresh_button_reloads_current_document(qapp, app_context):
    app_context.db.add_or_update_document(
        "d1", {"title": "Old Title", "author": "A", "file_path": "a.pdf", "created_at": 1.0}
    )
    panel = DocumentDetailPanel(app_context)
    panel.set_document(app_context.db.get_document("d1"))
    assert "Old Title" in panel.title_edit.text()

    # Change the DB directly (no event published) -- only the refresh
    # button, not automatic sync, should pick this up.
    app_context.db.update_document_fields("d1", {"title": "Manually Refreshed"})
    panel.refresh_label.clicked.emit()

    assert "Manually Refreshed" in panel.title_edit.text()


def test_refresh_button_does_nothing_without_a_selected_document(qapp, app_context):
    panel = DocumentDetailPanel(app_context)
    panel.refresh_label.clicked.emit()  # must not raise
    assert panel._empty_label.isHidden() is False


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
    monkeypatch.setattr(
        "smartdoc.presentation.detail_panel.open_reader",
        lambda context, doc, parent=None: opened_docs.append(doc),
    )
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


def test_author_link_lists_own_and_coauthored_works(qapp, app_context):
    from smartdoc.core.event_bus import FilterChangedEvent
    from smartdoc.presentation.library_view import LibraryListWidget

    rows = [
        ("d1", "Nguyễn Nhật Ánh"),
        ("d2", "Nguyễn Nhật Ánh, Trần A"),
        ("d3", "Trần A & Lê B"),
        ("d4", "Nguyễn Nhật Ánh Hai"),  # a different person whose name merely starts the same
    ]
    for doc_id, author in rows:
        app_context.db.add_or_update_document(
            doc_id, {"title": doc_id, "author": author, "file_path": f"{doc_id}.pdf", "created_at": 1.0}
        )
    panel = DocumentDetailPanel(app_context)
    library = LibraryListWidget(app_context)
    events = []
    app_context.event_bus.subscribe(FilterChangedEvent, lambda e: events.append(e))

    panel.set_document(app_context.db.get_document("d1"))
    assert panel.author_works_label.text() == "Còn 1 tài liệu cùng tác giả"  # d2; not d1 itself

    panel.author_works_label.clicked.emit()
    qapp.processEvents()
    library.reload()

    assert events[-1].filter.authors == ("Nguyễn Nhật Ánh",)
    shown = sorted(library.model.document_at(r)["id"] for r in range(library.model.rowCount()))
    assert shown == ["d1", "d2"]


def test_author_link_for_a_coauthored_book_covers_every_author(qapp, app_context):
    for doc_id, author in (("d1", "Trần A, Lê B"), ("d2", "Lê B"), ("d3", "Người khác")):
        app_context.db.add_or_update_document(
            doc_id, {"title": doc_id, "author": author, "file_path": f"{doc_id}.pdf", "created_at": 1.0}
        )
    panel = DocumentDetailPanel(app_context)
    panel.set_document(app_context.db.get_document("d1"))

    assert panel.author_works_label.text() == "Còn 1 tài liệu cùng tác giả"  # d2 shares Lê B; d1 is this book


def test_author_link_hidden_for_unknown_author(qapp, app_context):
    app_context.db.add_or_update_document(
        "d1", {"title": "t", "author": "Unknown", "file_path": "a.pdf", "created_at": 1.0}
    )
    panel = DocumentDetailPanel(app_context)
    panel.set_document(app_context.db.get_document("d1"))

    assert panel.author_works_label.isHidden()


# ── Bibliographic fields and hand-typed locks ────────────────────────


def test_bibliography_rows_show_the_values_or_a_dash(qapp, app_context):
    panel = DocumentDetailPanel(app_context)

    panel.set_document(_sample_doc())
    assert (panel.publisher_label.text(), panel.year_label.text(), panel.isbn_label.text()) == ("—", "—", "—")

    panel.set_document(_sample_doc(publisher="NXB Trẻ", pub_year=2006, language="vi", isbn="9786040123456"))
    assert panel.publisher_label.text() == "NXB Trẻ"
    assert panel.year_label.text() == "2006, Tiếng Việt"
    assert panel.isbn_label.text() == "9786040123456"


def test_editing_a_field_inline_locks_it_against_metadata_suggestions(qapp, app_context):
    app_context.db.add_or_update_document(
        "d1", {"title": "Old Title", "author": "A", "file_path": "a.pdf", "created_at": 1.0}
    )
    panel = DocumentDetailPanel(app_context)
    panel.set_document(app_context.db.get_document("d1"))

    panel.title_edit.setText("Typed By Hand")
    panel.title_edit.editingFinished.emit()

    assert app_context.db.locked_fields("d1") == {"title"}


# -- dates on one row, page count ------------------------------------------------------------


def test_added_and_modified_dates_share_one_row_with_the_exact_time_in_the_tooltip(qapp, app_context):
    panel = DocumentDetailPanel(app_context)
    panel.set_document(_sample_doc(created_at=1700000000.0, updated_at=1700003600.0))

    text = panel.dates_label.text()
    assert text.count("/") == 4 and " · " in text and chr(10) not in text  # two dd/mm/yyyy dates, no time
    added_line = panel.dates_label.toolTip().splitlines()[0]
    assert ":" in added_line.split("Thêm:")[1]  # the full date + time is one hover away


def test_a_stored_page_count_is_shown_in_the_format_line(qapp, app_context):
    panel = DocumentDetailPanel(app_context)
    panel.set_document(_sample_doc(page_count=320))
    assert "PDF" in panel.format_size_label.text() and "320 trang" in panel.format_size_label.text()


def test_an_epub_page_count_is_marked_as_an_estimate(qapp, app_context):
    panel = DocumentDetailPanel(app_context)
    panel.set_document(_sample_doc(extension="epub", page_count=412))
    assert "~412 trang" in panel.format_size_label.text()


def test_no_page_count_leaves_the_format_line_as_before(qapp, app_context):
    panel = DocumentDetailPanel(app_context)
    panel.set_document(_sample_doc(page_count=0, extension="mobi"))
    assert "trang" not in panel.format_size_label.text()


def test_a_book_without_a_stored_count_gets_it_counted_in_the_background(qapp, app_context, tmp_path):
    from tests._metadata_helpers import make_pdf

    pdf = make_pdf(tmp_path / "a.pdf", pages=7)
    app_context.db.add_or_update_document(
        "d1", {"title": "A", "author": "B", "file_path": str(pdf), "extension": "pdf", "created_at": 1.0}
    )
    panel = DocumentDetailPanel(app_context)
    panel.set_document(dict(app_context.db.get_document("d1")))

    assert _pump_until(qapp, lambda: "7 trang" in panel.format_size_label.text())
    assert app_context.db.get_document("d1")["page_count"] == 7  # stored: not counted again next time


def test_a_result_for_a_book_no_longer_shown_does_not_touch_the_panel(qapp, app_context):
    panel = DocumentDetailPanel(app_context)
    panel.set_document(_sample_doc(id="d1", page_count=10))
    panel._on_page_count_ready("other", 99)
    assert "99" not in panel.format_size_label.text()


def test_a_cloud_only_file_is_not_opened_to_count_pages(qapp, app_context, monkeypatch):
    from smartdoc.presentation import detail_panel

    monkeypatch.setattr(detail_panel, "is_cloud_only", lambda path: True)
    started = []
    monkeypatch.setattr(detail_panel.threading, "Thread", lambda *a, **k: started.append(k) or None)
    panel = DocumentDetailPanel(app_context)
    panel.set_document(_sample_doc(page_count=None))
    assert started == []


def test_a_book_with_no_other_books_by_its_author_shows_no_link(qapp, app_context):
    app_context.db.add_or_update_document(
        "d1", {"title": "t", "author": "Chỉ Một Cuốn", "file_path": "a.pdf", "created_at": 1.0}
    )
    panel = DocumentDetailPanel(app_context)
    panel.set_document(app_context.db.get_document("d1"))
    assert panel.author_works_label.isHidden()


# --- editable vs. read-only fields look different, without relying on colour ---


def test_editable_fields_are_dashed_frames_with_a_pen_and_read_only_rows_are_plain(qapp, app_context):
    from PySide6.QtWidgets import QLabel

    from smartdoc.presentation.editable_field import EditableField

    panel = DocumentDetailPanel(app_context)
    for field in (panel.title_field, panel.author_field):
        assert isinstance(field, EditableField) and field.property("editable") is True
        assert len(field.edit.actions()) == 1 and not field.edit.actions()[0].icon().isNull()  # the pen
        assert "sửa" in field.edit.actions()[0].toolTip()
    assert panel.tag_editor.property("editable") is True
    for label in (panel.format_size_label, panel.publisher_label, panel.year_label, panel.isbn_label, panel.dates_label):
        assert type(label) is QLabel and label.property("editable") is False
        assert "không sửa được" in label.toolTip()


def test_editable_field_paints_differently_at_rest_and_while_editing(qapp, app_context):
    from PySide6.QtGui import QImage

    panel = DocumentDetailPanel(app_context)
    panel.resize(340, 700)
    panel.show()
    panel.set_document(_sample_doc())
    qapp.processEvents()
    field = panel.title_field

    def outline():
        image = QImage(field.size(), QImage.Format_ARGB32)
        image.fill(0)
        field.render(image)
        y = field.height() // 2
        return [image.pixel(x, y) for x in range(field.width())]

    at_rest = outline()
    panel.title_edit.setFocus()
    qapp.processEvents()
    assert at_rest != outline()


def test_the_four_actions_and_the_close_button_exist(qapp, app_context):
    panel = DocumentDetailPanel(app_context)
    names = [b.text() for b in (panel.star_button, panel.cover_search_label, panel.metadata_button, panel.ereader_button)]
    assert names == ["Sẽ đọc", "Đổi bìa", "Tìm thông tin", "Gửi máy đọc"]
    closed, sent = [], []
    panel.close_requested.connect(lambda: closed.append(1))
    panel.ereader_requested.connect(lambda: sent.append(1))
    panel.close_label.clicked.emit()
    panel.ereader_button.click()
    assert closed == [1] and sent == [1]


def test_the_star_button_files_the_book_into_the_reading_list_and_back(qapp, app_context):
    app_context.db.add_or_update_document("d1", {"title": "A", "author": "B", "file_path": "a.pdf", "created_at": 1.0})
    panel = DocumentDetailPanel(app_context)
    panel.set_document(dict(app_context.db.get_document("d1")))
    assert panel.star_button.text() == "Sẽ đọc"

    panel.star_button.click()
    assert "d1" in app_context.db.reading_list_ids() and panel.star_button.text() == "Đã trong Sẽ đọc"

    panel.star_button.click()
    assert "d1" not in app_context.db.reading_list_ids()


def test_the_find_information_button_opens_the_metadata_dialog(qapp, app_context, monkeypatch):
    opened = []

    class _FakeDialog:
        def __init__(self, context, doc, parent=None):
            opened.append(doc["id"])

        def exec(self):
            return 0

    monkeypatch.setattr("smartdoc.presentation.detail_panel.MetadataSuggestDialog", _FakeDialog)
    panel = DocumentDetailPanel(app_context)
    panel.set_document(_sample_doc())
    panel.metadata_button.click()
    assert opened == ["d1"]
