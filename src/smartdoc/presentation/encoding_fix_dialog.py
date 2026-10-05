# SPDX-License-Identifier: AGPL-3.0-or-later
"""Dialog: Sửa mã hóa cũ trong tên sách (TCVN3/VNI → Unicode) — Task 4 (Tuần 3-4).

Scans all document titles and authors in the database, detects strings that were
originally encoded in a legacy Vietnamese encoding (TCVN3, VNI, CP1258) and were
mis-decoded as Latin-1, then presents a list so the user can confirm before applying
the fix.
"""
from __future__ import annotations

import logging

from PySide6.QtCore import QThread, Signal
from PySide6.QtWidgets import (
    QDialog,
    QHBoxLayout,
    QHeaderView,
    QLabel,
    QMessageBox,
    QPushButton,
    QTableWidget,
    QTableWidgetItem,
    QVBoxLayout,
)

from smartdoc.core.event_bus import LibraryUpdatedEvent
from smartdoc.domain.encoding_fix import EncFinding, apply_fixes, batch_scan_db

logger = logging.getLogger(__name__)

_COL_CHECK = 0
_COL_FIELD = 1
_COL_ORIG  = 2
_COL_FIXED = 3
_COL_CONF  = 4


class _ScanWorker(QThread):
    finished: Signal = Signal(object)
    failed: Signal = Signal(str)

    def __init__(self, db, parent=None) -> None:
        super().__init__(parent)
        self._db = db

    def run(self) -> None:
        try:
            self.finished.emit(batch_scan_db(self._db))
        except Exception as exc:  # noqa: BLE001
            logger.exception("Scan error: %s", exc)
            self.failed.emit(str(exc))


class EncodingFixDialog(QDialog):
    """Scan → confirm → apply legacy encoding fixes for titles and authors."""

    def __init__(self, context, parent=None) -> None:
        super().__init__(parent)
        self.context = context
        self._findings: list[EncFinding] = []
        self._worker: _ScanWorker | None = None

        self.setWindowTitle("Sửa mã hóa cũ trong tên sách")
        self.setMinimumWidth(700)
        self.setMinimumHeight(450)
        self._build_ui()
        self._start_scan()

    def _build_ui(self) -> None:
        layout = QVBoxLayout(self)
        layout.setSpacing(8)

        self.status_label = QLabel("Đang quét thư viện…", self)
        layout.addWidget(self.status_label)

        self.table = QTableWidget(0, 5, self)
        self.table.setHorizontalHeaderLabels(["✔", "Trường", "Hiện tại", "Sau sửa", "Chắc chắn"])
        self.table.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeToContents)
        self.table.horizontalHeader().setSectionResizeMode(_COL_ORIG, QHeaderView.Stretch)
        self.table.horizontalHeader().setSectionResizeMode(_COL_FIXED, QHeaderView.Stretch)
        self.table.setEditTriggers(QTableWidget.NoEditTriggers)
        layout.addWidget(self.table)

        sel_row = QHBoxLayout()
        select_all_btn = QPushButton("Chọn tất cả", self)
        select_all_btn.clicked.connect(self._select_all)
        deselect_btn = QPushButton("Bỏ chọn tất cả", self)
        deselect_btn.clicked.connect(self._deselect_all)
        sel_row.addWidget(select_all_btn)
        sel_row.addWidget(deselect_btn)
        sel_row.addStretch()
        layout.addLayout(sel_row)

        btn_row = QHBoxLayout()
        self.apply_button = QPushButton("Áp dụng sửa đã chọn", self)
        self.apply_button.setEnabled(False)
        self.apply_button.clicked.connect(self._on_apply)
        close_btn = QPushButton("Đóng", self)
        close_btn.clicked.connect(self.close)
        btn_row.addStretch()
        btn_row.addWidget(self.apply_button)
        btn_row.addWidget(close_btn)
        layout.addLayout(btn_row)

    def _start_scan(self) -> None:
        self.status_label.setText("Đang quét thư viện…")
        self.table.setRowCount(0)
        self._worker = _ScanWorker(self.context.db, self)
        self._worker.finished.connect(self._on_scan_done)
        self._worker.failed.connect(self._on_scan_error)
        self._worker.finished.connect(self._worker.deleteLater)
        self._worker.failed.connect(self._worker.deleteLater)
        self._worker.start()

    def _on_scan_done(self, findings: list[EncFinding]) -> None:
        self._findings = findings
        self.table.setRowCount(len(findings))
        for row, f in enumerate(findings):
            chk = QTableWidgetItem()
            chk.setCheckState(2)   # Qt.Checked
            self.table.setItem(row, _COL_CHECK, chk)
            field_label = "Tiêu đề" if f.field == "title" else "Tác giả"
            self.table.setItem(row, _COL_FIELD, QTableWidgetItem(field_label))
            self.table.setItem(row, _COL_ORIG, QTableWidgetItem(f.original))
            self.table.setItem(row, _COL_FIXED, QTableWidgetItem(f.suggested))
            self.table.setItem(row, _COL_CONF, QTableWidgetItem(f"{int(f.confidence * 100)}%"))
        if findings:
            self.status_label.setText(
                f"Tìm thấy {len(findings)} tên có thể bị lỗi mã hóa. "
                "Chọn những cái cần sửa rồi bấm 'Áp dụng'."
            )
            self.apply_button.setEnabled(True)
        else:
            self.status_label.setText(
                "Không tìm thấy tên sách nào có dấu hiệu lỗi mã hóa cũ."
            )

    def _on_scan_error(self, msg: str) -> None:
        self.status_label.setText(f"Lỗi khi quét: {msg}")

    def _select_all(self) -> None:
        for row in range(self.table.rowCount()):
            item = self.table.item(row, _COL_CHECK)
            if item:
                item.setCheckState(2)

    def _deselect_all(self) -> None:
        for row in range(self.table.rowCount()):
            item = self.table.item(row, _COL_CHECK)
            if item:
                item.setCheckState(0)

    def _on_apply(self) -> None:
        selected = [
            self._findings[row]
            for row in range(self.table.rowCount())
            if (item := self.table.item(row, _COL_CHECK)) and item.checkState() == 2
        ]
        if not selected:
            QMessageBox.information(self, "Chưa chọn", "Chưa chọn mục nào để sửa.")
            return
        try:
            count = apply_fixes(self.context.db, selected)
        except Exception as exc:  # noqa: BLE001
            QMessageBox.critical(self, "Lỗi", f"Không sửa được: {exc}")
            return

        self.context.event_bus.publish(LibraryUpdatedEvent())
        QMessageBox.information(self, "Hoàn thành", f"Đã sửa {count} trường. Thư viện sẽ tự làm mới.")
        self.apply_button.setEnabled(False)
        self._start_scan()
