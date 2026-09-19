# SPDX-License-Identifier: AGPL-3.0-or-later
"""Settings -> "Sao lưu" tab: back up the library now, see the backups, restore one (S1-03).

The work is application/backup_service.py; this only asks, runs it off the GUI thread and reports. Restoring
always asks first and says that the current library is backed up before it is replaced.
"""
from __future__ import annotations

import logging
import threading
from datetime import datetime

from PySide6.QtCore import Qt, QUrl, Signal
from PySide6.QtGui import QDesktopServices
from PySide6.QtWidgets import (
    QFormLayout,
    QHBoxLayout,
    QLabel,
    QListWidget,
    QListWidgetItem,
    QMessageBox,
    QPushButton,
    QSpinBox,
    QVBoxLayout,
    QWidget,
)

from smartdoc.application.backup_service import (
    BackupError,
    BackupInfo,
    MAX_RETENTION,
    MIN_RETENTION,
    REASON_MANUAL,
    REASON_PRE_RESTORE,
    REASON_PRE_UPGRADE,
)
from smartdoc.core.event_bus import LibraryUpdatedEvent
from smartdoc.infrastructure.schema_migrations import SchemaError

logger = logging.getLogger(__name__)

_REASON_LABELS = {
    REASON_MANUAL: "Thủ công",
    REASON_PRE_RESTORE: "Trước khi khôi phục",
}


def reason_label(reason: str) -> str:
    if reason.startswith(REASON_PRE_UPGRADE):
        return "Trước khi nâng cấp"
    return _REASON_LABELS.get(reason, reason)


def describe(info: BackupInfo) -> str:
    when = datetime.fromtimestamp(info.created_at).strftime("%d/%m/%Y %H:%M")
    return f"{when}  ·  {reason_label(info.reason)}  ·  {info.size / (1024 * 1024):.1f} MB"


class BackupPanel(QWidget):
    _done = Signal(str, object, str)  # (what, BackupInfo | None, error message) -- crosses back to the GUI thread

    def __init__(self, context, parent=None) -> None:
        super().__init__(parent)
        self.context = context
        self._busy = False
        self._available = False  # set by refresh(); read as soon as the list's selection signal fires

        layout = QVBoxLayout(self)
        note = QLabel(
            "Bản sao lưu chứa cơ sở dữ liệu thư viện: thông tin sách, thẻ, bộ sưu tập, đánh giá đã lưu và chỉ mục tìm kiếm. "
            "File sách của bạn không nằm trong đó và không bao giờ bị thay đổi. MewBook tự sao lưu trước mỗi lần nâng cấp thư viện.",
            self,
        )
        note.setWordWrap(True)
        layout.addWidget(note)

        form = QFormLayout()
        self.retention_spin = QSpinBox(self)
        self.retention_spin.setRange(MIN_RETENTION, MAX_RETENTION)
        self.retention_spin.setValue(context.config.config.backup_retention)
        form.addRow("Số bản sao lưu giữ lại:", self.retention_spin)
        layout.addLayout(form)

        self.backup_list = QListWidget(self)
        layout.addWidget(self.backup_list, stretch=1)

        row = QHBoxLayout()
        self.backup_button = QPushButton("💾 Sao lưu ngay", self)
        self.backup_button.clicked.connect(self._on_backup_now)
        self.restore_button = QPushButton("♻️ Khôi phục bản đã chọn...", self)
        self.restore_button.clicked.connect(self._on_restore)
        self.folder_button = QPushButton("📂 Mở thư mục", self)
        self.folder_button.clicked.connect(self._on_open_folder)
        for button in (self.backup_button, self.restore_button, self.folder_button):
            row.addWidget(button)
        layout.addLayout(row)

        self.status_label = QLabel(self)
        self.status_label.setWordWrap(True)
        layout.addWidget(self.status_label)

        self.backup_list.itemSelectionChanged.connect(self._update_buttons)
        self._done.connect(self._on_done)
        self.refresh()

    # -- state -----------------------------------------------------------------------------------------------

    def _service(self):
        return self.context.backups

    def refresh(self) -> None:
        self.backup_list.clear()
        try:
            backups = self._service().list_backups()
            available = True
        except BackupError as exc:  # an in-memory library
            backups, available = [], False
            self.status_label.setText(str(exc))
        for info in backups:
            item = QListWidgetItem(describe(info))
            item.setData(Qt.UserRole, info)
            self.backup_list.addItem(item)
        if backups:
            self.backup_list.setCurrentRow(0)
        self._available = available
        self._update_buttons()

    def _update_buttons(self) -> None:
        idle = not self._busy and self._available
        self.backup_button.setEnabled(idle)
        self.restore_button.setEnabled(idle and self.backup_list.currentItem() is not None)
        self.folder_button.setEnabled(self._available)

    def _selected(self) -> BackupInfo | None:
        item = self.backup_list.currentItem()
        return item.data(Qt.UserRole) if item is not None else None

    def _run(self, what: str, work) -> None:
        """Run `work` on a worker thread; its result (or error) comes back through `_done`."""
        self._busy = True
        self._update_buttons()
        self.status_label.setText("Đang sao lưu..." if what == "backup" else "Đang khôi phục...")

        def target() -> None:
            try:
                info, error = work(), ""
            except (BackupError, SchemaError) as exc:
                info, error = None, str(exc)
            except Exception as exc:  # noqa: BLE001 -- a worker must always report back, or the buttons stay disabled
                logger.exception("Backup task %s failed", what)
                info, error = None, f"Lỗi không mong đợi: {exc}"
            self._done.emit(what, info, error)

        threading.Thread(target=target, name=f"backup-{what}", daemon=True).start()

    def _on_done(self, what: str, info, error: str) -> None:
        self._busy = False
        if error:
            self.status_label.setText(f"⚠️ {error}")
        elif what == "backup":
            self.status_label.setText(f"✅ Đã sao lưu ({describe(info)}).")
        else:
            self.context.event_bus.publish(LibraryUpdatedEvent())
            self.status_label.setText(
                "✅ Đã khôi phục thư viện. Thư viện trước đó được giữ lại trong danh sách "
                f"({describe(info)}). Nếu màn hình chính chưa cập nhật, hãy khởi động lại MewBook."
            )
        self.refresh()

    # -- actions ---------------------------------------------------------------------------------------------

    def _on_backup_now(self) -> None:
        self._run("backup", lambda: self._service().create_backup(REASON_MANUAL))

    def _confirm_restore(self, info: BackupInfo) -> bool:
        answer = QMessageBox.question(
            self,
            "Khôi phục thư viện",
            f"Khôi phục thư viện về bản:\n{describe(info)}\n\n"
            "Mọi thay đổi từ thời điểm đó (sách thêm, thẻ, bộ sưu tập, đánh giá) sẽ mất khỏi thư viện đang dùng. "
            "MewBook sẽ sao lưu thư viện hiện tại trước, nên bạn có thể quay lại. File sách không bị đụng tới.",
            QMessageBox.Yes | QMessageBox.No,
            QMessageBox.No,
        )
        return answer == QMessageBox.Yes

    def _on_restore(self) -> None:
        info = self._selected()
        if info is None or not self._confirm_restore(info):
            return
        self._run("restore", lambda: self._service().restore(info.path))

    def _on_open_folder(self) -> None:
        try:
            folder = self._service().directory
        except BackupError:
            return
        folder.mkdir(parents=True, exist_ok=True)
        QDesktopServices.openUrl(QUrl.fromLocalFile(str(folder)))

    def retention(self) -> int:
        return self.retention_spin.value()
