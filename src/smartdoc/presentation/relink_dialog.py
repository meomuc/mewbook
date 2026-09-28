# SPDX-License-Identifier: AGPL-3.0-or-later
"""Tools -> "Tìm lại file thiếu...": point books whose file has moved at its new location (S1-04).

The user picks the folder where the files are now; the app lists what it found (matched by content, else by
name and size) and **changes nothing until the user confirms**. Only the library's stored paths are updated; the
book files themselves are never touched (application/relink_service.py).
"""
from __future__ import annotations

import logging
import threading

from PySide6.QtCore import Qt, Signal
from PySide6.QtWidgets import QFileDialog, QHBoxLayout, QHeaderView, QLabel, QMessageBox, QPushButton, QTableWidget, QTableWidgetItem

from smartdoc.application.relink_service import METHOD_FINGERPRINT, METHOD_HASH, METHOD_NAME_SIZE, RelinkProposal
from smartdoc.presentation.design_dialog import DesignDialog
from smartdoc.presentation.line_icons import line_icon
from smartdoc.presentation.theme_manager import theme_manager
from smartdoc.presentation.worker_relay import WorkerRelay, post

logger = logging.getLogger(__name__)

_METHOD_LABELS = {
    METHOD_HASH: "Trùng nội dung",
    METHOD_NAME_SIZE: "Trùng tên và dung lượng",
    METHOD_FINGERPRINT: "Trùng dấu vân tay (file đã đổi metadata)",
}
_COLUMNS = ("", "Sách", "Đường dẫn cũ", "Đường dẫn mới", "Cách khớp")


def method_label(method: str) -> str:
    return _METHOD_LABELS.get(method, method)


class RelinkDialog(DesignDialog):
    _progress = Signal(str)
    _found = Signal(object)  # list[RelinkProposal] | Exception
    _checked = Signal(object)  # int | Exception

    def __init__(self, context, parent=None) -> None:
        super().__init__(parent, title="Tìm lại file thiếu",
                         subtitle="Chọn thư mục mới, MewBook dò lại theo tên, dung lượng và nội dung.",
                         icon="link", width=760)
        self.context = context
        self._service = context.relink
        self._proposals: list[RelinkProposal] = []
        self._busy = False
        self._cancel = threading.Event()
        self._relay = WorkerRelay(self)
        self.setMinimumHeight(480)
        tm = theme_manager()

        self.summary_label = QLabel(self)
        self.summary_label.setWordWrap(True)
        self.summary_label.setStyleSheet(f"font-weight: 600; color: {tm.token('warn')};")
        self.body.addWidget(self.summary_label)

        row = QHBoxLayout()
        self.folder_button = QPushButton("Chọn thư mục mới…", self)
        self.folder_button.setIcon(line_icon("folder", tm.token("ink"), 14))
        self.folder_button.clicked.connect(self._on_choose_folder)
        self.recheck_button = QPushButton("Dò lại", self)
        self.recheck_button.setIcon(line_icon("refresh", tm.token("ink"), 14))
        self.recheck_button.clicked.connect(self._on_recheck)
        row.addWidget(self.folder_button)
        row.addWidget(self.recheck_button)
        row.addStretch(1)
        self.body.addLayout(row)

        self.table = QTableWidget(0, len(_COLUMNS), self)
        self.table.setHorizontalHeaderLabels(list(_COLUMNS))
        self.table.verticalHeader().setVisible(False)
        self.table.setEditTriggers(QTableWidget.NoEditTriggers)
        self.table.setSelectionBehavior(QTableWidget.SelectRows)
        self.table.setTextElideMode(Qt.ElideMiddle)  # a path is only readable with both its drive and its file name
        header = self.table.horizontalHeader()
        header.setSectionResizeMode(0, QHeaderView.ResizeToContents)
        for column in (1, 2, 3):
            header.setSectionResizeMode(column, QHeaderView.Stretch)
        header.setSectionResizeMode(4, QHeaderView.ResizeToContents)
        self.body.addWidget(self.table, 1)

        self.status_label = QLabel(self)
        self.status_label.setWordWrap(True)
        self.body.addWidget(self.status_label)

        self.add_footer_note("File sách không bị di chuyển, đổi tên hay sửa.")
        self.close_button = self.add_footer_button("Hủy", on_click=self.reject)
        self.apply_button = self.add_footer_button("Cập nhật đường dẫn", "primary", on_click=self._on_apply)

        self._progress.connect(self.status_label.setText)
        self._found.connect(self._on_found)
        self._checked.connect(self._on_checked)
        self.table.itemChanged.connect(lambda _item: self._update_buttons())
        self._refresh_summary()
        self._update_buttons()

    # -- state -----------------------------------------------------------------------------------------------

    def _refresh_summary(self) -> None:
        missing = self.context.db.count_missing()
        tm = theme_manager()
        self.summary_label.setStyleSheet(f"font-weight: 600; color: {tm.token('warn' if missing else 'ink2')};")
        if missing:
            self.summary_label.setText(
                f"{missing} sách không tìm thấy file. Chọn thư mục nơi các file đang nằm; MewBook sẽ tìm và đề xuất, "
                "bạn xem lại rồi mới xác nhận."
            )
        else:
            self.summary_label.setText("Không có sách nào bị mất file. Bấm \"Kiểm tra lại file\" nếu bạn vừa di chuyển sách.")

    def _update_buttons(self) -> None:
        self.folder_button.setEnabled(not self._busy and self.context.db.count_missing() > 0)
        self.recheck_button.setEnabled(not self._busy)
        chosen = len(self.selected_proposals())
        self.apply_button.setText(f"Cập nhật {chosen} đường dẫn" if chosen else "Cập nhật đường dẫn")
        self.apply_button.setEnabled(not self._busy and chosen > 0)

    def selected_proposals(self) -> list[RelinkProposal]:
        selected = []
        for row, proposal in enumerate(self._proposals):
            item = self.table.item(row, 0)
            if item is not None and item.checkState() == Qt.Checked:
                selected.append(proposal)
        return selected

    def _fill_table(self) -> None:
        self.table.blockSignals(True)
        self.table.setRowCount(len(self._proposals))
        for row, proposal in enumerate(self._proposals):
            check = QTableWidgetItem()
            check.setFlags(Qt.ItemIsUserCheckable | Qt.ItemIsEnabled)
            check.setCheckState(Qt.Checked if proposal.selected else Qt.Unchecked)
            if proposal.note:
                check.setToolTip(proposal.note)
            self.table.setItem(row, 0, check)
            method = method_label(proposal.method) + (f" · {proposal.note}" if proposal.note else "")
            for column, text in ((1, proposal.title), (2, proposal.old_path), (3, proposal.new_path), (4, method)):
                item = QTableWidgetItem(text)
                item.setToolTip(text)
                self.table.setItem(row, column, item)
        self.table.blockSignals(False)

    # -- background work --------------------------------------------------------------------------------------

    def _run(self, work, done_signal_name: str) -> None:
        self._busy = True
        self._update_buttons()
        relay = self._relay

        def target() -> None:
            try:
                result = work()
            except Exception as exc:  # noqa: BLE001 -- the worker must always report back, or the buttons stay disabled
                logger.exception("Relink task failed")
                result = exc
            post(relay, done_signal_name, result)

        threading.Thread(target=target, name="relink", daemon=True).start()

    def _on_recheck(self) -> None:
        self.status_label.setText("Đang kiểm tra file của thư viện…")
        service = self._service
        self._run(lambda: service.check_files(), "_checked")

    def _on_checked(self, result) -> None:
        self._busy = False
        if isinstance(result, Exception):
            self.status_label.setText(f"Không kiểm tra được: {result}")
        else:
            self.status_label.setText(f"Đã kiểm tra: {result} sách không tìm thấy file.")
        self._refresh_summary()
        self._update_buttons()

    def _on_choose_folder(self) -> None:
        folder = QFileDialog.getExistingDirectory(self, "Chọn thư mục gốc mới chứa các file sách", "")
        if folder:
            self.start_search(folder)

    def start_search(self, folder: str) -> None:
        self.status_label.setText("Đang tìm file trong thư mục...")
        self._proposals = []
        self._fill_table()

        relay, service = self._relay, self._service

        def progress(stage: str, done: int, total: int) -> None:
            text = f"Đang duyệt thư mục: {done} file..." if stage == "scan" else f"Đang đối chiếu: {done}/{total} sách..."
            post(relay, "_progress", text)

        self._run(lambda: service.propose(folder, progress=progress), "_found")

    def _on_found(self, result) -> None:
        self._busy = False
        if isinstance(result, Exception):
            self.status_label.setText(f"Không tìm được: {result}")
            self._update_buttons()
            return
        self._proposals = result
        self._fill_table()
        missing = self.context.db.count_missing()
        if result:
            self.status_label.setText(
                f"Tìm thấy {len(result)} trong {missing} sách thiếu. Bỏ chọn dòng nào bạn không muốn, rồi bấm \"Cập nhật\"."
            )
        else:
            self.status_label.setText("Không tìm thấy sách nào trong thư mục này. Thử một thư mục gốc rộng hơn.")
        self._update_buttons()

    # -- apply -----------------------------------------------------------------------------------------------

    def _confirm(self, count: int) -> bool:
        answer = QMessageBox.question(
            self,
            "Cập nhật đường dẫn",
            f"Cập nhật đường dẫn của {count} sách sang vị trí mới?\nChỉ thư viện MewBook thay đổi; file sách không bị đụng tới.",
            QMessageBox.Yes | QMessageBox.No,
            QMessageBox.Yes,
        )
        return answer == QMessageBox.Yes

    def _on_apply(self) -> None:
        chosen = self.selected_proposals()
        if not chosen or not self._confirm(len(chosen)):
            return
        for proposal in self._proposals:
            proposal.selected = proposal in chosen
        result = self._service.apply(self._proposals)
        text = f"Đã cập nhật đường dẫn của {result.updated} sách."
        if result.skipped:
            text += f" Bỏ qua {len(result.skipped)}: {result.skipped[0][1]}."
        self.status_label.setText(text)
        # A chosen proposal the service could not apply after all (its target vanished, or another book claimed it
        # in the meantime) used to be dropped from the list right along with the ones that succeeded -- silently, as
        # if it had been handled. It stays now, unchecked, with its own reason, so it is not mistaken for done.
        skip_reasons = dict(result.skipped)
        remaining = []
        for proposal in self._proposals:
            if proposal in chosen and proposal.doc_id not in skip_reasons:
                continue  # applied
            if proposal.doc_id in skip_reasons:
                proposal.selected = False
                proposal.note = skip_reasons[proposal.doc_id]
            remaining.append(proposal)
        self._proposals = remaining
        self._fill_table()
        self._refresh_summary()
        self._update_buttons()
