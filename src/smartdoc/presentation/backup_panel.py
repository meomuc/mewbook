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
    QCheckBox,
    QHBoxLayout,
    QLabel,
    QListWidget,
    QListWidgetItem,
    QFileDialog,
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
from smartdoc.presentation.design_dialog import confirm_danger
from smartdoc.presentation.line_icons import line_icon
from smartdoc.presentation.settings_widgets import SettingsPage, add_note_box
from smartdoc.presentation.theme_manager import theme_manager
from smartdoc.presentation.worker_relay import WorkerRelay, post

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


class BackupPanel(SettingsPage):
    _done = Signal(str, object, str)  # (what, BackupInfo | None, error message) -- crosses back to the GUI thread

    def __init__(self, context, parent=None) -> None:
        super().__init__("Sao lưu", "Bản sao dữ liệu thư viện, để quay lại khi cần. File sách không nằm trong đó.", parent)
        self.context = context
        self._busy = False
        self._available = False  # set by refresh(); read as soon as the list's selection signal fires
        self._relay = WorkerRelay(self)
        tm = theme_manager()

        self.add_block(add_note_box(
            self, "Bản sao lưu chứa thông tin sách, thẻ, bộ sưu tập, đánh giá đã lưu và chỉ mục tìm kiếm. "
                  "MewBook tự sao lưu trước mỗi lần nâng cấp thư viện.", "ok"))

        # The three backup options of the whole app live here and nowhere else (AppConfig.backup_*).
        self.before_change_check = QCheckBox("Sao lưu trước khi thay đổi", self)
        self.before_change_check.setChecked(context.config.config.backup_before_change)
        self.before_change_check.setToolTip("Khi MewBook sửa file sách của bạn (ví dụ ghi thông tin vào EPUB/PDF), file cũ được chép "
                                            "vào thư mục sao lưu trước, để hoàn tác được.")
        self.before_change_check.toggled.connect(lambda _checked: self._show_folder())
        self.add_row("Sao lưu file trước khi thay đổi", "Mặc định tắt. Bật thì phải chọn thư mục sao lưu bên dưới.",
                     self.before_change_check)
        self.keep_spin = QSpinBox(self)
        self.keep_spin.setRange(MIN_RETENTION, MAX_RETENTION)
        self.keep_spin.setValue(context.config.config.backup_keep)
        self.add_row("Số bản sao lưu giữ lại", "Cho mỗi file sách, và cho bản sao lưu thư viện. Bản cũ nhất được xóa khi vượt số này.",
                     self.keep_spin)
        folder_box = QWidget(self)
        folder_layout = QVBoxLayout(folder_box)
        folder_layout.setContentsMargins(0, 0, 0, 0)
        folder_layout.setSpacing(6)
        self.folder_label = QLabel(folder_box)
        self.folder_label.setWordWrap(True)
        self.folder_label.setTextInteractionFlags(Qt.TextSelectableByMouse)
        self.choose_folder_button = QPushButton("Chọn thư mục…", folder_box)
        self.choose_folder_button.clicked.connect(self._on_choose_folder)
        self.default_folder_button = QPushButton("Bỏ chọn", folder_box)
        self.default_folder_button.clicked.connect(lambda: self._set_folder(""))
        folder_buttons = QHBoxLayout()
        folder_buttons.addWidget(self.choose_folder_button)
        folder_buttons.addWidget(self.default_folder_button)
        folder_buttons.addStretch(1)
        self.folder_warning = QLabel(folder_box)
        self.folder_warning.setWordWrap(True)
        self.folder_warning.setStyleSheet(f"color: {tm.token('err')};")
        folder_layout.addWidget(self.folder_label)
        folder_layout.addLayout(folder_buttons)
        folder_layout.addWidget(self.folder_warning)
        self.add_row("Thư mục lưu bản sao", "Chưa chọn thì chưa sao lưu file sách được. Có thể chọn ổ đĩa ngoài; thư mục không dùng được "
                     "thì MewBook báo rõ, không tự đổi chỗ khác.", folder_box)

        holder = QWidget(self)
        holder_layout = QVBoxLayout(holder)
        holder_layout.setContentsMargins(0, 0, 0, 0)
        self.backup_list = QListWidget(holder)
        self.backup_list.setMinimumHeight(140)
        holder_layout.addWidget(self.backup_list)
        row = QHBoxLayout()
        self.backup_button = QPushButton("Sao lưu ngay", holder)
        self.backup_button.setIcon(line_icon("archive", tm.token("ink"), 14))
        self.backup_button.clicked.connect(self._on_backup_now)
        self.restore_button = QPushButton("Khôi phục…", holder)
        self.restore_button.setIcon(line_icon("refresh", tm.token("ink"), 14))
        self.restore_button.clicked.connect(self._on_restore)
        self.folder_button = QPushButton("Mở thư mục", holder)
        self.folder_button.setIcon(line_icon("folder", tm.token("ink"), 14))
        self.folder_button.clicked.connect(self._on_open_folder)
        for button in (self.backup_button, self.restore_button, self.folder_button):
            row.addWidget(button)
        row.addStretch(1)
        holder_layout.addLayout(row)
        self.status_label = QLabel(holder)
        self.status_label.setWordWrap(True)
        holder_layout.addWidget(self.status_label)
        self.add_row("Các bản sao lưu", "Khôi phục sẽ nói rõ điều gì sẽ mất trước khi làm.", holder)

        self.backup_list.itemSelectionChanged.connect(self._update_buttons)
        self._done.connect(self._on_done)
        self.refresh()

    # -- state -----------------------------------------------------------------------------------------------

    def _service(self):
        return self.context.backups

    def _on_choose_folder(self) -> None:
        start = self._service().custom_folder or str(self._service().directory)
        chosen = QFileDialog.getExistingDirectory(self, "Chọn thư mục lưu bản sao lưu", start)
        if chosen:
            self._set_folder(chosen)

    def _set_folder(self, folder: str) -> str:
        """Use `folder` ("" = the default one) for backups. A folder that cannot be written to is refused with the reason
        (and the previous choice stays); returns that reason, "" when it was accepted."""
        service = self._service()
        problem = service.check_folder(folder) if folder else ""
        if problem:
            self.folder_warning.setText(problem)
            return problem
        self.context.config.config.backup_dir = folder or None
        self.context.config.save()
        self.status_label.setText("")
        self.refresh()
        return ""

    def folder(self) -> str:
        return self.context.config.config.backup_dir or ""

    def _show_folder(self) -> None:
        service = self._service()
        try:
            where = str(service.directory)
        except BackupError:
            self.folder_label.setText("")
            self.folder_warning.setText("")
            return
        custom = service.custom_folder
        self.folder_label.setText(where if custom else "Chưa chọn thư mục sao lưu. Bản sao lưu thư viện tạm thời nằm ở "
                                  f"{where} (cạnh thư viện).")
        self.default_folder_button.setEnabled(bool(custom))
        if custom:
            self.folder_warning.setText(service.check_folder())
        elif self.before_change_check.isChecked():
            self.folder_warning.setText("Bạn đã bật \"Sao lưu trước khi thay đổi\" nhưng chưa chọn thư mục sao lưu. "
                                        "Hãy bấm \"Chọn thư mục…\"; chưa chọn thì MewBook sẽ không ghi vào file sách.")
        else:
            self.folder_warning.setText("")

    def refresh(self) -> None:
        self.backup_list.clear()
        self._show_folder()
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
        self.backup_button.setEnabled(idle and not (self._service().custom_folder and self.folder_warning.text()))
        self.choose_folder_button.setEnabled(self._available and not self._busy)
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
        relay = self._relay

        def target() -> None:
            try:
                info, error = work(), ""
            except (BackupError, SchemaError) as exc:
                info, error = None, str(exc)
            except Exception as exc:  # noqa: BLE001 -- a worker must always report back, or the buttons stay disabled
                logger.exception("Backup task %s failed", what)
                info, error = None, f"Lỗi không mong đợi: {exc}"
            post(relay, "_done", what, info, error)

        threading.Thread(target=target, name=f"backup-{what}", daemon=True).start()

    def _on_done(self, what: str, info, error: str) -> None:
        self._busy = False
        if error:
            self.status_label.setText(error)
        elif what == "backup":
            self.status_label.setText(f"Đã sao lưu ({describe(info)}).")
        else:
            self.context.event_bus.publish(LibraryUpdatedEvent())
            self.status_label.setText(
                "Đã khôi phục thư viện. Thư viện trước đó được giữ lại trong danh sách "
                f"({describe(info)}). Nếu màn hình chính chưa cập nhật, hãy khởi động lại MewBook."
            )
        self.refresh()

    # -- actions ---------------------------------------------------------------------------------------------

    def _on_backup_now(self) -> None:
        self._run("backup", lambda: self._service().create_backup(REASON_MANUAL))

    def _lost_since(self, info: BackupInfo) -> list[str]:
        """What a restore would really lose: the books added after that backup (counted, not guessed)."""
        added = self.context.db.connection.execute(
            "SELECT COUNT(*) FROM documents WHERE created_at > ?", (info.created_at,)
        ).fetchone()[0]
        return [f"{added} sách thêm vào thư viện sau mốc này sẽ biến mất khỏi danh sách"] if added else []

    def _confirm_restore(self, info: BackupInfo) -> bool:
        lines = self._lost_since(info) + [
            "Hashtag, bộ sưu tập, đánh giá và ảnh bìa bạn sửa sau mốc này sẽ trở về như lúc đó",
        ]
        return confirm_danger(
            self, title="Khôi phục thư viện về bản cũ?", subtitle="Bước xác nhận cuối",
            message=f"Thư viện sẽ trở về bản:<br><b>{describe(info)}</b>",
            items=lines,
            safe_text="<b>Không bị đụng tới:</b> file sách trên máy. MewBook sao lưu thư viện hiện tại trước khi khôi phục, "
                      "nên bạn có thể quay lại.",
            ack_text="Tôi hiểu các thay đổi sau mốc này sẽ mất khỏi thư viện", action_text="Khôi phục thư viện",
            cancel_text="Không khôi phục",
        )

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

    def keep(self) -> int:
        return self.keep_spin.value()

    def before_change(self) -> bool:
        return self.before_change_check.isChecked()
