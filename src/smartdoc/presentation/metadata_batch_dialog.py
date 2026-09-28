# SPDX-License-Identifier: AGPL-3.0-or-later
"""Task B3: "Cập nhật thông tin sách hàng loạt" -- the batch counterpart of "Tìm thêm thông tin"
(metadata_suggest_dialog.py), scoped to the list currently being viewed. `current_scope` is a callable returning
that scope (library_view.classification_scope -- the same "what am I looking at" smart-classify already reuses),
asked fresh each time the dialog needs it rather than snapshotted once, so a filter change before "Chạy nền" is
pressed is respected.

Two pages: a source picker (what to use, and "Sẽ cập nhật N tài liệu") and a running/result page with a
BusyIndicator, a live count, and "Hoàn tác" for the whole run once it ends. Not modal (`.show()`, not `.exec()`):
the library stays usable while it runs, on a background thread, same as InfoRefreshDialog. Progress is also
published as a BackgroundTaskEvent, so the status bar's left zone shows it even if this window is minimized.
"""
from __future__ import annotations

import logging
import threading

from PySide6.QtCore import Signal
from PySide6.QtWidgets import QCheckBox, QHBoxLayout, QLabel, QStackedWidget, QVBoxLayout, QWidget

from smartdoc.application.metadata_batch_update import (
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

# Shown when "Nguồn Internet" is ticked -- task B3: name (as a heading, via the checkbox itself), what it covers,
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


class MetadataBatchUpdateDialog(DesignDialog):
    _progress = Signal(int, int)
    _finished = Signal(object)  # BatchUpdateResult

    def __init__(self, context, current_scope, parent=None, *, service: MetadataBatchUpdateService | None = None) -> None:
        super().__init__(parent, title="Cập nhật thông tin sách hàng loạt",
                         subtitle="Tìm và điền thông tin còn thiếu cho danh sách đang xem", icon="search", width=620)
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
        self.run_button = self.add_footer_button("Chạy nền", "primary", on_click=self._on_run)

        self._progress.connect(self._on_progress)
        self._finished.connect(self._on_finished)
        self._refresh_preview()

    # -- page 1: source picker --------------------------------------------------------------------------------

    def _build_picker_page(self) -> QWidget:
        page = QWidget(self)
        layout = QVBoxLayout(page)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(12)
        tm = theme_manager()

        layout.addWidget(HintLabel(
            "Mỗi thông tin (tên, tác giả, nhà xuất bản...) lấy từ nguồn đầu tiên bên dưới có dữ liệu, theo đúng "
            "thứ tự. Thông tin bạn đã tự sửa tay không bao giờ bị ghi đè. Chỉ ghi vào thư viện MewBook, không "
            "đụng tới file sách gốc.", page))

        self.file_check = QCheckBox(f"{SOURCE_FILE} -- thông tin nhúng sẵn trong từng file sách", page)
        self.file_check.setChecked(True)
        self.file_check.setEnabled(False)  # đọc file là miễn phí và không rời khỏi máy -- không có lý do để tắt
        layout.addWidget(self.file_check)

        self.library_check = QCheckBox(f"{SOURCE_LIBRARY} -- những cuốn khác đã có sẵn thông tin đầy đủ", page)
        self.library_check.setChecked(True)
        self.library_check.setEnabled(False)
        layout.addWidget(self.library_check)

        self.community_check = QCheckBox(SOURCE_COMMUNITY, page)
        self.community_check.setChecked(False)
        self.community_check.setEnabled(False)
        community_row = QHBoxLayout()
        community_row.setContentsMargins(0, 0, 0, 0)
        community_row.setSpacing(8)
        community_row.addWidget(self.community_check)
        community_row.addWidget(soon_badge(page), 0)
        community_row.addStretch(1)
        layout.addLayout(community_row)

        self.internet_check = QCheckBox("Nguồn Internet -- Open Library, Google Books...", page)
        self.internet_check.setChecked(False)  # task B3 AC: mặc định KHÔNG tick
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

    def _refresh_preview(self) -> None:
        count = self._service.preview_count(self._current_scope())
        self.preview_label.setText(f"Sẽ cập nhật {count} tài liệu" if count else "Không có tài liệu nào trong danh sách đang xem")
        self.run_button.setEnabled(count > 0)

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

    def _on_run(self) -> None:
        if self._running:
            return
        scope = self._current_scope()
        options = BatchUpdateOptions(use_internet=self.internet_check.isChecked())
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
        prefix = "Đã dừng. " if result.cancelled else ""
        self.status_label.setText(
            f"{prefix}Đã cập nhật {result.updated}, bỏ qua {result.skipped}, lỗi {result.error_count}.")
        if result.errors or result.source_errors:
            lines = [f"{name}: {message}" for name, message in result.errors] + list(result.source_errors)
            self.source_error_label.set_text(" ".join(lines))
            self.source_error_label.setVisible(True)
        self.undo_button.setVisible(bool(result.run_ids))

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
