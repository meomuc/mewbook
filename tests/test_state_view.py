# SPDX-License-Identifier: AGPL-3.0-or-later
"""The empty / nothing-found states in the middle of the library, and the yellow "missing files" strip (stage G11)."""
from PySide6.QtWidgets import QPushButton

from smartdoc.core.event_bus import LibraryFilesMissingEvent
from smartdoc.presentation.library_view import LibraryListWidget
from smartdoc.presentation.missing_files_strip import MissingFilesStrip
from smartdoc.presentation.state_view import StateView


def _texts(view: StateView) -> list[str]:
    return [b.text() for b in view.buttons]


def test_a_state_has_a_picture_a_title_a_sentence_and_at_most_two_buttons(qapp):
    view = StateView()
    calls = []
    view.set_state("thinking", "Không có sách nào khớp", "Thử bỏ bớt bộ lọc.",
                   [("Một", lambda: calls.append(1), True), ("Hai", lambda: calls.append(2), False), ("Ba", lambda: calls.append(3), False)])
    assert view.title_label.text() == "Không có sách nào khớp" and view.text_label.text() == "Thử bỏ bớt bộ lọc."
    assert _texts(view) == ["Một", "Hai"]  # never more than two
    view.buttons[0].click()
    assert calls == [1] and not view.mascot_label.isHidden()
    view.deleteLater()


def test_each_situation_uses_its_own_mascot_role(qapp):
    view = StateView()
    for method, role in (("show_searching", "searching"), ("show_waiting", "waiting"), ("show_ai_writing", "dev")):
        getattr(view, method)()
        assert view.role == role
    view.show_error("Chưa mở được", "File bị khóa.", [("Tìm lại file", lambda: None, True)])
    assert view.role == "sad" and _texts(view) == ["Tìm lại file"]
    view.show_done("Xong", "Đã thêm 12 sách.")
    assert view.role == "done"
    view.deleteLater()


def test_an_empty_library_says_so_in_the_middle_and_offers_adding(qapp, app_context):
    widget = LibraryListWidget(app_context)
    widget.show()
    qapp.processEvents()
    assert widget.state_view.isVisible() and not widget.view_stack.isVisible() and not widget.pagination_bar.isVisible()
    assert widget.state_view.title_label.text() == "Thư viện đang trống" and widget.state_view.role == "logo"
    asked = []
    widget.add_files_requested.connect(lambda: asked.append("files"))
    widget.add_folder_requested.connect(lambda: asked.append("folder"))
    widget.state_view.buttons[0].click()
    widget.state_view.buttons[1].click()
    assert asked == ["files", "folder"]
    widget.deleteLater()


def test_a_filter_with_no_match_offers_to_clear_it(qapp, app_context):
    app_context.db.add_or_update_document("a", {"title": "A", "author": "X", "file_path": "a.pdf", "extension": "pdf", "created_at": 1.0})
    widget = LibraryListWidget(app_context)
    widget.show()
    assert widget.view_stack.isVisible() and not widget.state_view.isVisible()

    app_context.filters.select("formats", "epub")
    qapp.processEvents()

    assert widget.state_view.isVisible() and widget.state_view.role == "thinking"
    assert _texts(widget.state_view) == ["Xóa bộ lọc"]
    widget.state_view.buttons[0].click()
    qapp.processEvents()
    assert widget.view_stack.isVisible() and not widget.state_view.isVisible()
    widget.deleteLater()


def test_the_missing_files_strip_follows_the_count(qapp, app_context):
    strip = MissingFilesStrip(app_context)
    assert strip.isHidden()  # nothing is missing
    strip._on_event(LibraryFilesMissingEvent(count=12))
    assert strip.isVisible() and strip.text_label.text() == "12 sách không tìm thấy file."
    asked = []
    strip.relink_requested.connect(lambda: asked.append(1))
    strip.findChild(QPushButton).click()
    assert asked == [1]
    strip._on_event(LibraryFilesMissingEvent(count=0))
    assert not strip.isVisible()
    strip.deleteLater()
