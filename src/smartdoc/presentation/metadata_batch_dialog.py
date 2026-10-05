# SPDX-License-Identifier: AGPL-3.0-or-later
"""Cập nhật thông tin sách -- the merged tool: what used to be two separate menu items ("Cập nhật thông tin sách
ngay…", a file-facts-only rescan, and "Cập nhật thông tin sách hàng loạt…", a bibliographic lookup) is now one
dialog over `MetadataBatchUpdateService`, which does both in a single pass per document (see that module's
docstring for why the merge is also the main speed win: one bulk-fetched row per book instead of two separate
scans opening the same file twice).

Three mutually-exclusive scope choices (radio buttons), not just "whatever the library view is currently showing":
- "Chỉ sách chưa có thông tin" (default): the whole library, but only books still missing basic bibliographic
  fields -- skips a lookup entirely for a book that already has everything, which is the other real speed win.
- "Sách đang được lọc": exactly what `current_scope()` resolves to right now, regardless of completeness.
- "Toàn bộ thư viện": every book, regardless of completeness.
`current_scope` is a callable (library_view.classification_scope) asked fresh each time it is needed rather than
snapshotted once, so a filter change before running is respected -- but it is only ever consulted for the
"Sách đang được lọc" choice; the other two ignore it on purpose (see metadata_batch_update.SCOPE_*).

Two ways to start, per the task's own wording: "Thực hiện" runs it and keeps this window as it is (visible,
showing live progress); "Chạy nền" runs the very same job but also minimizes this window right away, so the
person can use the rest of MewBook while it works -- reopening the same menu action (main_window.py already
reuses one open instance) un-minimizes and raises it again. Not modal (`.show()`, not `.exec()`): the library
stays usable while it runs, on a background thread, same as InfoRefreshDialog used to be on its own. Progress is
also published as a BackgroundTaskEvent, so the status bar's left zone shows it even while minimized.
"""
from __future__ import annotations

import logging
import threading

from PySide6.QtCore import Qt, Signal
from PySide6.QtWidgets import QButtonGroup, QCheckBox, QHBoxLayout, QLabel, QRadioButton, QStackedWidget, QVBoxLayout, QWidget

from smartdoc.application.metadata_batch_update import (
    SCOPE_ALL,
    SCOPE_FILTERED,
    SCOPE_MISSING_INFO,
    SOURCE_COMMUNITY,
    BatchUpdateOptions,
    BatchUpdateResult,
    MetadataBatchUpdateService,
)
from smartdoc.application.metadata_lookup import SOURCE_APPLE_BOOKS, SOURCE_FILE, SOURCE_GOOGLE_BOOKS, SOURCE_LIBRARY, SOURCE_OPEN_LIBRARY
from smartdoc.application.smart_classifier import ClassifyScope
from smartdoc.core.event_bus import BackgroundTaskEvent
from smartdoc.presentation.busy_indicator import BusyIndicator
from smartdoc.presentation.design_dialog import DesignDialog
from smartdoc.presentation.hint_label import HintLabel
from smartdoc.presentation.settings_widgets import soon_badge
from smartdoc.presentation.theme import ROLE_RESULT, role_css
from smartdoc.presentation.theme_manager import theme_manager
from smartdoc.presentation.worker_relay import WorkerRelay, post

logger = logging.getLogger(__name__)

# Shown when "Nguồn Internet" is ticked -- name (as a heading, via the checkbox itself), what it covers,
# accuracy (measured or "Chưa đo", never invented) and its limits, straight from docs/legal/DATA_SOURCES.md
# (§2.1-2.4) so nothing here is guessed. Apple Books is left out unless Settings already re-enabled it (§2.4: off
# by default, terms unclear) -- the same rule DATA_SOURCES.md states for cover search applies to this lookup too.
_INTERNET_SOURCE_NOTES = {
    SOURCE_OPEN_LIBRARY: ("Tên, tác giả, NXB, năm, ngôn ngữ, ISBN. Độ chính xác: Chưa đo. "
                          "Giới hạn: không giới hạn theo lượt tìm thường."),
    SOURCE_GOOGLE_BOOKS: ("Tên, tác giả, NXB, năm, ngôn ngữ, ISBN, mô tả. Độ chính xác: Chưa đo. "
                          "Giới hạn: có hạn mức miễn phí mỗi ngày, có thể hết giữa chừng (báo lỗi 429)."),
    SOURCE_APPLE_BOOKS: ("Tên, tác giả. Độ chính xác: Chưa đo. "
                         "Giới hạn: khoảng 20 lượt/phút; điều khoản dùng cho việc này chưa rõ."),
}

# The scope radio group's own labels -- kept next to SCOPE_* so a reviewer can match one to the other at a glance.
_SCOPE_LABELS = {
    SCOPE_MISSING_INFO: "Chỉ sách chưa có thông tin (toàn bộ thư viện)",
    SCOPE_FILTERED: "Sách đang được lọc",
    SCOPE_ALL: "Toàn bộ thư viện",
}


class MetadataBatchUpdateDialog(DesignDialog):
    _progress = Signal(int, int)
    _finished = Signal(object)  # BatchUpdateResult

    def __init__(self, context, current_scope, parent=None, *, service: MetadataBatchUpdateService | None = None) -> None:
        super().__init__(parent, title="Cập nhật thông tin sách",
                         subtitle="Làm mới thông tin file và tìm thông tin sách còn thiếu", icon="search", width=640)
        # A minimize button so "Chạy nền" has a real titlebar affordance too, not just the programmatic
        # showMinimized() call -- QDialog does not offer one by default.
        self.setWindowFlags(self.windowFlags() | Qt.WindowMinimizeButtonHint)
        self.context = context
        self._current_scope = current_scope
        self._service = service or MetadataBatchUpdateService(context)
        self._cancel = threading.Event()
        self._running = False
        self._last_result: BatchUpdateResult | None = None
        self._relay = WorkerRelay(self)

        self.pages = QStackedWidget(self)
        self.body.addWidget(self.pages, 1)
        self.pages.addWidget(self._build_picker_page())
        self.pages.addWidget(self._build_running_page())

        self.cancel_button = self.add_footer_button("Hủy", on_click=self.reject)
        self.undo_button = self.add_footer_link("Hoàn tác lượt này", "refresh", self._on_undo)
        self.undo_button.hide()
        self.background_button = self.add_footer_button("Chạy nền", on_click=self._on_run_background)
        self.run_button = self.add_footer_button("Thực hiện", "primary", on_click=self._on_run_foreground)

        self._progress.connect(self._on_progress)
        self._finished.connect(self._on_finished)
        self._refresh_preview()

    # -- page 1: scope + source picker --------------------------------------------------------------------------

    def _build_picker_page(self) -> QWidget:
        page = QWidget(self)
        layout = QVBoxLayout(page)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(12)
        tm = theme_manager()

        layout.addWidget(HintLabel(
            "Một lượt vừa làm mới thông tin file (dung lượng, mã nội dung, số trang) vừa tìm và điền tên sách, "
            "tác giả, nhà xuất bản... còn thiếu. Mỗi thông tin lấy từ nguồn đầu tiên bên dưới có dữ liệu, theo "
            "đúng thứ tự. Thông tin bạn đã tự sửa tay không bao giờ bị ghi đè. Chỉ ghi vào thư viện MewBook, "
            "không đụng tới file sách gốc.", page))

        layout.addWidget(QLabel("Phạm vi:", page))
        self._scope_group = QButtonGroup(page)
        self._scope_buttons: dict[str, QRadioButton] = {}
        for scope in (SCOPE_MISSING_INFO, SCOPE_FILTERED, SCOPE_ALL):
            button = QRadioButton(_SCOPE_LABELS[scope], page)
            button.toggled.connect(self._on_scope_changed)
            self._scope_group.addButton(button)
            self._scope_buttons[scope] = button
            layout.addWidget(button)
        # blockSignals: preview_label doesn't exist yet at this point in _build_picker_page() -- toggled would
        # otherwise fire _on_scope_changed -> _refresh_preview() into a not-yet-built widget. The explicit
        # _refresh_preview() call at the end of __init__ (once everything exists) is what actually sets the text.
        default_button = self._scope_buttons[SCOPE_MISSING_INFO]  # task default: "mặc định tick"
        default_button.blockSignals(True)
        default_button.setChecked(True)
        default_button.blockSignals(False)

        self.file_check = QCheckBox(f"{SOURCE_FILE} -- thông tin nhúng sẵn trong từng file sách", page)
        self.file_check.setChecked(True)
        self.file_check.setEnabled(False)  # đọc file là miễn phí và không rời khỏi máy -- không có lý do để tắt
        layout.addWidget(self.file_check)

        self.library_check = QCheckBox(f"{SOURCE_LIBRARY} -- những cuốn khác đã có sẵn thông tin đầy đủ", page)
        self.library_check.setChecked(True)
        self.library_check.setEnabled(False)
        layout.addWidget(self.library_check)

        self.community_check = QCheckBox(SOURCE_COMMUNITY, page)
        community_enabled = bool(getattr(self.context.config.config, "community_metadata_enabled", False))
        self.community_check.setChecked(community_enabled)
        self.community_check.setEnabled(community_enabled)
        community_row = QHBoxLayout()
        community_row.setContentsMargins(0, 0, 0, 0)
        community_row.setSpacing(8)
        community_row.addWidget(self.community_check)
        if not community_enabled:
            community_row.addWidget(soon_badge(page), 0)
        community_row.addStretch(1)
        layout.addLayout(community_row)

        self.internet_check = QCheckBox("Nguồn Internet -- Open Library, Google Books...", page)
        self.internet_check.setChecked(False)  # mặc định KHÔNG tick
        self.internet_check.toggled.connect(self._on_internet_toggled)
        layout.addWidget(self.internet_check)
        self.internet_notes = HintLabel("", page, color_token="ink2")
        self.internet_notes.setVisible(False)
        layout.addWidget(self.internet_notes)
        self._set_internet_notes()

        self.preview_label = QLabel(page)
        self.preview_label.setStyleSheet(role_css(ROLE_RESULT, tm.token("ink")))
        layout.addWidget(self.preview_label)
        layout.addStretch(1)
        return page

    def _enabled_internet_sources(self) -> list[str]:
        disabled = set(getattr(self.context.config.config, "disabled_cover_sources", ()) or ())
        return [name for name in (SOURCE_OPEN_LIBRARY, SOURCE_GOOGLE_BOOKS, SOURCE_APPLE_BOOKS) if name not in disabled]

    def _set_internet_notes(self) -> None:
        lines = [f"{name}: {_INTERNET_SOURCE_NOTES[name]}" for name in self._enabled_internet_sources()]
        self.internet_notes.set_text(
            " ".join(lines) if lines else
            "Mọi nguồn Internet đang tắt ở Cài đặt → Ảnh bìa -- bật lại ở đó trước, hoặc bỏ tích ở đây.")

    def _on_internet_toggled(self, checked: bool) -> None:
        self.internet_notes.setVisible(checked)

    def _current_scope_choice(self) -> str:
        for scope, button in self._scope_buttons.items():
            if button.isChecked():
                return scope
        return SCOPE_MISSING_INFO

    def _on_scope_changed(self, checked: bool) -> None:
        if checked:  # QButtonGroup toggles the old button off and the new one on -- react only to the "on" half
            self._refresh_preview()

    def _refresh_preview(self) -> None:
        count = self._service.preview_count(self._current_scope(), self._current_scope_choice())
        self.preview_label.setText(f"Sẽ cập nhật {count} tài liệu" if count else "Không có tài liệu nào trong phạm vi đã chọn")
        self.run_button.setEnabled(count > 0)
        self.background_button.setEnabled(count > 0)

    # -- page 2: running / result -------------------------------------------------------------------------------

    def _build_running_page(self) -> QWidget:
        page = QWidget(self)
        layout = QVBoxLayout(page)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(12)
        tm = theme_manager()

        self.busy = BusyIndicator(page, message="Đang chuẩn bị…", mascot_role="thinking")
        layout.addWidget(self.busy)
        self.status_label = QLabel(page)
        self.status_label.setWordWrap(True)
        self.status_label.setStyleSheet(role_css(ROLE_RESULT, tm.token("ink")))
        layout.addWidget(self.status_label)
        self.source_error_label = HintLabel("", page, color_token="warn")
        self.source_error_label.setVisible(False)
        layout.addWidget(self.source_error_label)
        layout.addStretch(1)
        return page

    # -- running --------------------------------------------------------------------------------------------

    def _on_run_foreground(self) -> None:
        """"Thực hiện": starts the run and leaves the window exactly as it is."""
        self._on_run()

    def _on_run_background(self) -> None:
        """"Chạy nền": the same run as "Thực hiện", plus minimizing the window so the rest of MewBook is free to
        use right away. Also works mid-run (the person started with "Thực hiện" and changed their mind) -- it
        only starts a new run if one is not already going."""
        if not self._running:
            self._on_run()
        self.showMinimized()

    def _on_run(self) -> None:
        if self._running:
            return
        scope_choice = self._current_scope_choice()
        options = BatchUpdateOptions(
            use_internet=self.internet_check.isChecked(),
            use_community=self.community_check.isChecked(),
            scope=scope_choice,
        )
        self._running = True
        self._cancel.clear()
        self.pages.setCurrentIndex(1)
        self.cancel_button.setText("Dừng")
        self.run_button.hide()
        self.undo_button.hide()
        self.busy.set_message("Đang chuẩn bị…")
        self.busy.set_busy(True)
        self.status_label.setText("")
        self.source_error_label.setVisible(False)

        service, relay, cancel = self._service, self._relay, self._cancel
        bus = self.context.event_bus
        # Resolved here, on the GUI thread, not inside work() -- classification_scope() reads Qt widget state
        # (the library view's current filter) and touches the database, neither of which is safe to call from
        # the background thread the actual lookup runs on.
        scope = self._current_scope()

        def on_progress(done: int, total: int) -> None:
            post(relay, "_progress", done, total)
            bus.publish(BackgroundTaskEvent(task="metadata-batch-update", done=done, total=total))

        def work() -> None:
            try:
                result = service.run(scope, options, progress=on_progress, should_cancel=cancel.is_set)
            except Exception:  # noqa: BLE001 -- the dialog must always get a report back, never hang "running"
                logger.exception("Batch metadata update crashed")
                result = BatchUpdateResult(cancelled=True)
            bus.publish(BackgroundTaskEvent(task="metadata-batch-update", done=1, total=1, finished=True))
            post(relay, "_finished", result)

        threading.Thread(target=work, name="metadata-batch-update", daemon=True).start()

    def _on_progress(self, done: int, total: int) -> None:
        self.busy.set_message(f"Đang kiểm tra {done} / {total} sách…" if total else "Đang chuẩn bị…")
        self.status_label.setText(f"Đã kiểm tra {done} / {total}")

    def _on_finished(self, result: BatchUpdateResult) -> None:
        self._running = False
        self._last_result = result
        self.busy.set_busy(False)
        self.cancel_button.setText("Đóng")
        self.run_button.hide()
        self.background_button.hide()  # nothing left running to send to the background
        prefix = "Đã dừng. " if result.cancelled else ""
        parts = [f"Đã cập nhật thông tin cho {result.updated} sách", f"làm mới file cho {result.files_refreshed} sách",
                f"bỏ qua {result.skipped}"]
        if result.missing_files:
            parts.append(f"{result.missing_files} không thấy file")
        if result.skipped_cloud:
            parts.append(f"{result.skipped_cloud} file chỉ có trên đám mây được bỏ qua")
        parts.append(f"lỗi {result.error_count}")
        self.status_label.setText(prefix + ", ".join(parts) + ".")
        if result.errors or result.source_errors:
            lines = [f"{name}: {message}" for name, message in result.errors] + list(result.source_errors)
            self.source_error_label.set_text(" ".join(lines))
            self.source_error_label.setVisible(True)
        self.undo_button.setVisible(bool(result.run_ids))
        # Deliberately does not un-minimize itself here even if "Chạy nền" sent it there -- the whole point of
        # backgrounding it was to not be interrupted; the status bar's BackgroundTaskEvent already said it
        # finished, and reopening the same menu action (main_window.py) restores this same window on demand.

    def _on_undo(self) -> None:
        if self._last_result is None or not self._last_result.run_ids:
            return
        restored = self._service.undo(self._last_result)
        self.status_label.setText(f"Đã hoàn tác {restored} tài liệu.")
        self.undo_button.hide()
        self._last_result = None

    def done(self, result: int) -> None:  # noqa: D401 -- Qt override
        self._cancel.set()
        super().done(result)


if __name__ == "__main__":
    import sys
    import tempfile
    from pathlib import Path

    from PySide6.QtWidgets import QApplication

    from smartdoc.core.app_context import AppContext

    app = QApplication(sys.argv)
    theme_manager().apply(app, "broadsheet")
    with tempfile.TemporaryDirectory() as tmp:
        ctx = AppContext.create_in_memory(Path(tmp))
        ctx.db.add_or_update_document("d1", {"title": "Demo", "author": "X", "file_path": "d1.pdf", "created_at": 1.0})
        dialog = MetadataBatchUpdateDialog(ctx, lambda: ClassifyScope())
        dialog.show()
        app.exec()
