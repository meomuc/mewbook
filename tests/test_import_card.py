# SPDX-License-Identifier: AGPL-3.0-or-later
"""The import card and drop overlay (stage G6): progress, one summary, stop, failures list, drag and drop."""
from PySide6.QtCore import QMimeData, QUrl
from PySide6.QtGui import QDragEnterEvent, QDragLeaveEvent, QDropEvent
from PySide6.QtCore import QPoint, Qt

from smartdoc.core.event_bus import ImportBatchCompletedEvent
from smartdoc.presentation.import_card import ImportStatusCard, remaining_text


def _event(success=412, duplicate=31, failed=7, ids=None, paths=()):
    return ImportBatchCompletedEvent(batch_id="b", success=success, duplicate=duplicate, failed=failed,
                                     doc_ids=tuple(ids or ()), failed_paths=tuple(paths))


def test_remaining_text_needs_some_history_and_speaks_in_plain_minutes():
    assert remaining_text(0, 100, 30) == ""
    assert remaining_text(10, 100, 1) == ""  # too early to guess
    assert remaining_text(50, 100, 100) == "còn khoảng 2 phút"
    assert remaining_text(50, 100, 25) == "còn khoảng vài chục giây"
    assert remaining_text(99, 100, 99) == "sắp xong"


def test_progress_shows_counts_and_a_stop_button_and_hides_when_done(qapp, app_context):
    card = ImportStatusCard(app_context)
    assert card.isHidden()
    card.show_progress(280, 450)
    assert not card.isHidden() and card.mode == "progress"
    assert "280 / 450" in card.detail_label.text()
    assert card.bar.maximum() == 450 and card.bar.value() == 280
    assert not card.stop_button.isHidden() and card.added_label.isHidden()

    card.show_progress(450, 450)
    assert card.isHidden()


def test_stop_button_cancels_the_waiting_files(qapp, app_context):
    calls = []

    class _Manager:
        def cancel_pending(self):
            calls.append(1)
            return 5

    card = ImportStatusCard(app_context, import_manager=_Manager())
    card.show_progress(10, 100)
    card.stop_button.click()
    assert calls == [1] and not card.stop_button.isEnabled()


def test_summary_is_one_card_with_three_counts_and_the_originals_are_safe(qapp, app_context):
    card = ImportStatusCard(app_context)
    card.show_summary(_event())
    assert card.mode == "summary"
    assert "412" in card.title_label.text()
    assert "412 thêm mới" in card.added_label.text()
    assert "31 trùng" in card.duplicate_label.text()
    assert "7 lỗi" in card.failed_label.text() and "xem danh sách" in card.failed_label.text()
    assert "nguyên chỗ cũ" in card.safe_label.text() and not card.safe_label.isHidden()


def test_a_summary_without_failures_hides_the_failure_count_and_an_empty_one_just_closes(qapp, app_context):
    card = ImportStatusCard(app_context)
    card.show_summary(_event(failed=0))
    assert card.failed_label.isHidden()
    card.show_summary(_event(success=0, duplicate=0, failed=0))
    assert card.isHidden()


def test_failures_link_opens_the_list_of_files(qapp, app_context, monkeypatch):
    shown = []

    class _Dialog:
        def __init__(self, paths, parent=None):
            shown.append(paths)

        def exec(self):
            return 0

        def deleteLater(self):
            pass

    monkeypatch.setattr("smartdoc.presentation.import_card.ImportFailuresDialog", _Dialog)
    card = ImportStatusCard(app_context)
    card.show_summary(_event(failed=2, paths=("a.txt", "b.txt")))
    card.failed_label.linkActivated.emit("#")
    assert shown == [("a.txt", "b.txt")]


def test_notice_is_a_line_in_the_card_with_a_close_button(qapp, app_context):
    card = ImportStatusCard(app_context)
    card.show_notice("Không tìm thấy sách nào.")
    assert card.title_label.text() == "Không tìm thấy sách nào."
    assert not card.close_button.isHidden() and card.classify_button.isHidden()
    card.close_button.click()
    assert card.isHidden()


def _drag_event(cls, urls):
    mime = QMimeData()
    mime.setUrls([QUrl.fromLocalFile(u) for u in urls])
    return mime, cls


def test_dragging_files_over_the_window_shows_the_overlay_and_leaving_hides_it(qapp, app_context):
    from smartdoc.presentation.main_window import MainWindow

    window = MainWindow(app_context)
    window.show()
    qapp.processEvents()
    mime = QMimeData()
    mime.setUrls([QUrl.fromLocalFile(__file__)])
    enter = QDragEnterEvent(QPoint(50, 50), Qt.CopyAction, mime, Qt.LeftButton, Qt.NoModifier)
    window.dragEnterEvent(enter)
    assert not window.drop_overlay.isHidden() and enter.isAccepted()
    assert window.drop_overlay.parentWidget() is window  # a child of the splitter would become one of its panes
    window.dragLeaveEvent(QDragLeaveEvent())
    assert window.drop_overlay.isHidden()
    window.hide()
    window.deleteLater()


def test_dropping_files_adds_them_and_hides_the_overlay(qapp, app_context, tmp_path):
    from smartdoc.presentation.main_window import MainWindow

    added = []

    class _Manager:
        def add_files(self, paths):
            added.extend(paths)

        def scan_folder(self, folder):
            added.append(("folder", folder))

        def pending_count(self):
            return 0

    book = tmp_path / "b.pdf"
    book.write_bytes(b"x")
    window = MainWindow(app_context, import_manager=_Manager())
    window.show()
    window.drop_overlay.show_over(window._splitter.geometry())
    mime = QMimeData()
    mime.setUrls([QUrl.fromLocalFile(str(book)), QUrl.fromLocalFile(str(tmp_path))])
    drop = QDropEvent(QPoint(50, 50), Qt.CopyAction, mime, Qt.LeftButton, Qt.NoModifier)
    window.dropEvent(drop)
    from pathlib import Path

    assert [Path(a) if isinstance(a, str) else Path(a[1]) for a in added] == [book, tmp_path]
    assert added[1][0] == "folder"
    assert window.drop_overlay.isHidden()
    window.hide()
    window.deleteLater()
