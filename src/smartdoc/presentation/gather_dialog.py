# SPDX-License-Identifier: AGPL-3.0-or-later
"""Gom sách về một thư mục: choose the target folder, choose copy or move, read what would happen, then do it.

The work is application/gather_service.py. Nothing is written until "Bắt đầu"; choosing a folder or a mode only redraws
the preview (how many books, how much space, how many are left out and why). "Di chuyển" says plainly that the files
leave their current folders and that the library's paths follow them, and asks once more before starting. The run goes
on a worker thread (a big library is gigabytes) that reports through a WorkerRelay and can be cancelled between files.
"""
from __future__ import annotations

import logging
import threading
import time

from PySide6.QtCore import Signal
from PySide6.QtWidgets import (
    QCheckBox,
    QFileDialog,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QMessageBox,
    QProgressBar,
    QPushButton,
    QRadioButton,
)

from smartdoc.application.gather_service import (
    MODE_COPY,
    MODE_MOVE,
    STATUS_MISSING,
    STATUS_THERE,
    GatherError,
    GatherPlan,
    GatherResult,
)
from smartdoc.core.perf_log import log_perf
from smartdoc.presentation.design_dialog import DesignDialog
from smartdoc.presentation.format_utils import human_size
from smartdoc.presentation.theme_manager import theme_manager
from smartdoc.presentation.worker_relay import WorkerRelay, post

logger = logging.getLogger(__name__)


class GatherDialog(DesignDialog):
    _progress = Signal(int, int)
    _finished = Signal(object, str)  # (GatherResult | None, error text)

    def __init__(self, context, parent=None, doc_ids: list[str] | None = None) -> None:
        super().__init__(parent, title="Gom sách về một thư mục", subtitle="Sao chép hoặc di chuyển file sách vào cùng một nơi",
                         icon="folder", width=640)
        self.context = context
        self.doc_ids = doc_ids
        self._plan: GatherPlan | None = None
        self._busy = False
        self._cancel = threading.Event()
        self._relay = WorkerRelay(self)
        tm = theme_manager()

        self.folder_edit = QLineEdit(self)
        self.folder_edit.setPlaceholderText("Thư mục đích…")
        self.folder_edit.textChanged.connect(self._update_plan)
        self.choose_button = QPushButton("Chọn…", self)
        self.choose_button.clicked.connect(self._on_choose)
        folder_row = QHBoxLayout()
        folder_row.addWidget(self.folder_edit, 1)
        folder_row.addWidget(self.choose_button)
        self.body.addLayout(folder_row)

        self.copy_radio = QRadioButton("Sao chép — file gốc giữ nguyên, thư viện vẫn trỏ tới file gốc", self)
        self.move_radio = QRadioButton("Di chuyển — file chuyển sang thư mục mới, đường dẫn trong thư viện tự cập nhật", self)
        self.copy_radio.setChecked(True)
        self.copy_radio.toggled.connect(self._update_plan)
        self.body.addWidget(self.copy_radio)
        self.body.addWidget(self.move_radio)

        self.by_category_check = QCheckBox(
            "Tạo thư mục con theo hashtag/thể loại (như trong thư viện)", self)
        self.by_category_check.setToolTip(
            "Mỗi sách vào một thư mục con trùng tên hashtag đầu tiên của nó (sách nhiều hashtag lấy hashtag đầu). "
            "Sách chưa có hashtag vào thư mục \"Chưa phân loại\". Để trống thì mọi sách nằm chung một thư mục.")
        self.by_category_check.toggled.connect(self._update_plan)
        self.body.addWidget(self.by_category_check)

        self.summary_label = QLabel(self)
        self.summary_label.setWordWrap(True)
        self.warning_label = QLabel(self)
        self.warning_label.setWordWrap(True)
        self.warning_label.setStyleSheet(f"color: {tm.token('err')};")
        self.warning_label.hide()
        self.progress_bar = QProgressBar(self)
        self.progress_bar.setTextVisible(False)
        self.progress_bar.hide()
        self.result_label = QLabel(self)
        self.result_label.setWordWrap(True)
        for widget in (self.summary_label, self.warning_label, self.progress_bar, self.result_label):
            self.body.addWidget(widget)
        self.body.addStretch(1)

        self.start_button = self.add_footer_button("Bắt đầu", "primary", on_click=self._on_start)
        self.close_button_footer = self.add_footer_button("Đóng", on_click=self._on_close)
        self._progress.connect(self._on_progress)
        self._finished.connect(self._on_finished)
        self._update_plan()

    # -- the preview ------------------------------------------------------------------------------------------------
    def mode(self) -> str:
        return MODE_MOVE if self.move_radio.isChecked() else MODE_COPY

    def _update_plan(self, *_args) -> None:
        self._plan = None
        self.warning_label.hide()
        target = self.folder_edit.text().strip()
        if not target:
            self.summary_label.setText("Chọn thư mục đích để xem trước điều sẽ xảy ra. Chưa có gì bị thay đổi.")
            self._update_buttons()
            return
        try:
            plan = self.context.gather.plan(target, self.mode(), self.doc_ids,
                                             by_category=self.by_category_check.isChecked())
        except GatherError as exc:
            self.summary_label.setText(str(exc))
            self._update_buttons()
            return
        self._plan = plan
        left_out = [i for i in plan.items if i.status in (STATUS_MISSING, STATUS_THERE)]
        missing = sum(1 for i in left_out if i.status == STATUS_MISSING)
        there = len(left_out) - missing
        lines = [f"{len(plan.ready)} sách ({human_size(plan.total_bytes).replace('.', ',')}) sẽ được "
                 + ("chuyển" if plan.mode == MODE_MOVE else "sao chép") + f" vào {plan.target}"
                 + (f", chia vào {plan.category_count} thư mục con theo hashtag." if plan.by_category else ".")]
        if missing:
            lines.append(f"{missing} sách không thấy file nên bỏ qua.")
        if there:
            lines.append(f"{there} sách đã nằm sẵn trong thư mục này.")
        self.summary_label.setText(" ".join(lines))
        warnings = []
        if not plan.enough_space:
            warnings.append(f"Ổ đĩa đích chỉ còn {human_size(plan.free_bytes).replace('.', ',')} trống, không đủ.")
        watched = self.context.gather.watched_folder_warning(plan.target)
        if watched and plan.mode == MODE_COPY:
            warnings.append(watched)
        if warnings:
            self.warning_label.setText(" ".join(warnings))
            self.warning_label.show()
        self._update_buttons()

    def _update_buttons(self) -> None:
        ready = self._plan is not None and bool(self._plan.ready) and self._plan.enough_space
        self.start_button.setEnabled(ready and not self._busy)
        self.choose_button.setEnabled(not self._busy)
        self.folder_edit.setEnabled(not self._busy)

    def _on_choose(self) -> None:
        chosen = QFileDialog.getExistingDirectory(self, "Chọn thư mục đích", self.folder_edit.text())
        if chosen:
            self.folder_edit.setText(chosen)

    # -- the run ----------------------------------------------------------------------------------------------------
    def _confirm_move(self, plan: GatherPlan) -> bool:
        return QMessageBox.question(
            self, "Di chuyển file sách?",
            f"{len(plan.ready)} file sẽ rời khỏi thư mục hiện tại và sang {plan.target}.\n\n"
            "Thư viện cập nhật đường dẫn theo, nhưng các chương trình khác đang trỏ tới file cũ (thư mục MewBook theo dõi, "
            "máy đọc sách, phím tắt…) sẽ không thấy chúng nữa. Nếu một file lỗi giữa chừng, file đó được giữ nguyên chỗ cũ.",
            QMessageBox.Yes | QMessageBox.No, QMessageBox.No) == QMessageBox.Yes

    def _on_start(self) -> None:
        plan = self._plan
        if plan is None or self._busy or not plan.ready:
            return
        if plan.mode == MODE_MOVE and not self._confirm_move(plan):
            return
        self._busy = True
        self._perf_started_at = time.monotonic()
        self._cancel.clear()
        self.result_label.setText("")
        self.progress_bar.setRange(0, max(1, len(plan.ready)))
        self.progress_bar.setValue(0)
        self.progress_bar.show()
        self.start_button.setText("Đang làm…")
        self._update_buttons()
        relay, service, cancel = self._relay, self.context.gather, self._cancel

        def work() -> None:
            try:
                result = service.run(plan, progress=lambda done, total: post(relay, "_progress", done, total),
                                     should_cancel=cancel.is_set)
                post(relay, "_finished", result, "")
            except GatherError as exc:
                post(relay, "_finished", None, str(exc))
            except Exception as exc:  # noqa: BLE001 -- a worker must always report back, or the dialog stays busy
                logger.exception("Gathering books failed")
                post(relay, "_finished", None, f"Lỗi không mong đợi: {exc}")

        threading.Thread(target=work, name="gather-books", daemon=True).start()

    def _on_progress(self, done: int, total: int) -> None:
        self.progress_bar.setRange(0, max(1, total))
        self.progress_bar.setValue(done)

    def _on_finished(self, result: GatherResult | None, error: str) -> None:
        self._busy = False
        duration = time.monotonic() - self._perf_started_at
        if result is None:
            log_perf("gather", duration, outcome="error")
        else:
            log_perf("gather", duration, done=result.done, failed=len(result.failed), skipped=result.skipped)
        self.progress_bar.hide()
        self.start_button.setText("Bắt đầu")
        if error or result is None:
            self.result_label.setText(error)
        else:
            text = f"Xong: {result.done} sách."
            if result.failed:
                text += f" {len(result.failed)} sách chưa làm được và vẫn nguyên chỗ cũ:\n" + "\n".join(
                    f"• {title}: {reason}" for title, reason in result.failed[:8])
            self.result_label.setText(text)
        self._update_plan()

    def _on_close(self) -> None:
        self._cancel.set()
        self.accept()

    def done(self, result: int) -> None:  # noqa: D401 -- Qt override
        self._cancel.set()
        super().done(result)
