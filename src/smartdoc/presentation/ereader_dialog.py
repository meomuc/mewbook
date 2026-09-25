# SPDX-License-Identifier: AGPL-3.0-or-later
"""Gửi sang máy đọc sách (stage G9): a device card (folder, drive, free space, "Đổi thư mục"), the score
("Đã gửi 4 / 5 sách · 1 lỗi") and one row per book with a tick or the reason it failed; "Gửi lại cuốn lỗi" tries the
failed ones again.

An e-reader plugged in by USB is just a folder, so sending is a real copy of the book file into it
(`FileActionEngine.copy_to_ereader`); the library itself never copies or moves anything. Nothing here touches the
originals.
"""
from __future__ import annotations

import shutil
from pathlib import Path

from PySide6.QtCore import QSize, Qt, QTimer
from PySide6.QtGui import QPixmap
from PySide6.QtWidgets import QApplication, QFileDialog, QFrame, QHBoxLayout, QLabel, QListWidget, QListWidgetItem, QPushButton

from smartdoc.presentation.design_dialog import DesignDialog
from smartdoc.presentation.line_icons import icon_pixmap, line_icon
from smartdoc.presentation.theme_manager import theme_manager

_THUMB = (32, 44)


def _free_space_text(folder: str) -> str:
    try:
        free = shutil.disk_usage(folder).free
    except OSError:
        return ""
    return f"còn trống {free / (1024 ** 3):.1f} GB".replace(".", ",")


class EreaderSendDialog(DesignDialog):
    def __init__(self, context, docs: list[dict], file_actions, target_folder: str, parent=None) -> None:
        super().__init__(parent, title="Gửi sang máy đọc sách", subtitle=f"{len(docs)} sách đã chọn", icon="send", width=640)
        self.context = context
        self.docs = docs
        self.file_actions = file_actions
        self.target = target_folder
        self._results: dict[str, str] = {}  # doc id -> "" (sent) | the reason it failed
        tm = theme_manager()

        self.device_frame = QFrame(self)
        self.device_frame.setObjectName("DeviceCard")
        self.device_frame.setStyleSheet(f"#DeviceCard {{ background: {tm.token('surface')}; border: 1px solid {tm.token('line')};"
                                        f" border-radius: 8px; }}")
        self.device_label = QLabel(self.device_frame)
        self.device_label.setTextFormat(Qt.RichText)
        self.device_label.setStyleSheet("background: transparent;")
        mark = QLabel(self.device_frame)
        mark.setPixmap(icon_pixmap("send", tm.token("ink"), 18))
        self.change_button = QPushButton("Đổi thư mục", self.device_frame)
        self.change_button.clicked.connect(self._on_change_folder)
        row = QHBoxLayout(self.device_frame)
        row.setContentsMargins(14, 12, 14, 12)
        row.addWidget(mark)
        row.addWidget(self.device_label, 1)
        row.addWidget(self.change_button)
        self.body.addWidget(self.device_frame)

        self.score_label = QLabel("", self)
        self.score_label.setTextFormat(Qt.RichText)
        self.body.addWidget(self.score_label)
        self.book_list = QListWidget(self)
        self.book_list.setMinimumHeight(220)
        self.book_list.setIconSize(self._thumb_size())
        self.body.addWidget(self.book_list, 1)
        for doc in docs:
            item = QListWidgetItem(doc.get("title") or "(không có tên)")
            item.setData(Qt.UserRole, doc.get("id"))
            cover = QPixmap(doc.get("cover_path") or "") if doc.get("cover_path") else QPixmap()
            if not cover.isNull():
                item.setIcon(cover.scaled(*_THUMB, Qt.KeepAspectRatio, Qt.SmoothTransformation))
            self.book_list.addItem(item)

        self.retry_button = self.add_footer_button("Gửi lại cuốn lỗi", on_click=self.retry_failed, left=True)
        self.retry_button.setEnabled(False)
        self.done_button = self.add_footer_button("Xong", "primary", on_click=self.accept)
        self._refresh_device()
        self._refresh_score()

    @staticmethod
    def _thumb_size() -> QSize:
        return QSize(*_THUMB)

    def exec(self) -> int:  # noqa: A003 -- Qt name
        """Sends as soon as the dialog is on screen (the list fills in while it copies)."""
        QTimer.singleShot(0, self.send_all)
        return super().exec()

    # -- the device card ---------------------------------------------------------------------------------------------
    def _refresh_device(self) -> None:
        free = _free_space_text(self.target)
        drive = Path(self.target).anchor.rstrip("\\/") or self.target
        self.device_label.setText(f"<b>{drive}</b><br><span style='color:{theme_manager().token('ink2')}'>"
                                  f"Thư mục: {self.target}{' · ' + free if free else ''}</span>")

    def _on_change_folder(self) -> None:
        folder = QFileDialog.getExistingDirectory(self, "Chọn thư mục sách trên máy đọc sách", self.target)
        if folder:
            self.target = folder
            self.context.config.config.ereader_folder_path = folder
            self.context.config.save()
            self._refresh_device()

    # -- sending ---------------------------------------------------------------------------------------------------
    def send_all(self) -> None:
        """Copies every book that has not been sent yet, updating the list as it goes."""
        QApplication.setOverrideCursor(Qt.WaitCursor)
        try:
            for row, doc in enumerate(self.docs):
                if self._results.get(doc.get("id")) == "":
                    continue
                path = doc.get("file_path") or ""
                reason = self.file_actions.copy_to_ereader(path, self.target) if path else "Không tìm thấy file trên máy"
                self._results[doc.get("id")] = reason
                self._paint_row(row, reason)
                QApplication.processEvents()
        finally:
            QApplication.restoreOverrideCursor()
        self._refresh_score()

    def retry_failed(self) -> None:
        for doc in self.docs:
            if self._results.get(doc.get("id")):
                self._results.pop(doc.get("id"))
        self.send_all()

    def _paint_row(self, row: int, reason: str) -> None:
        tm = theme_manager()
        item = self.book_list.item(row)
        title = self.docs[row].get("title") or "(không có tên)"
        if reason:
            item.setText(f"{title}\nLỗi: {reason}")
            if item.icon().isNull():
                item.setIcon(line_icon("close", tm.token("err"), 16))
            item.setForeground(tm.color("err"))
        else:
            item.setText(f"{title}\nĐã gửi")
            item.setForeground(tm.color("ink"))

    def sent_count(self) -> int:
        return sum(1 for reason in self._results.values() if reason == "")

    def failed_count(self) -> int:
        return sum(1 for reason in self._results.values() if reason)

    def _refresh_score(self) -> None:
        tm = theme_manager()
        sent, failed, total = self.sent_count(), self.failed_count(), len(self.docs)
        text = f"<b>Đã gửi {sent} / {total} sách</b>" if self._results else f"<b>{total} sách sẵn sàng để gửi</b>"
        if failed:
            text += f" &nbsp;<span style='color:{tm.token('err')}'>{failed} lỗi</span>"
        self.score_label.setText(text)
        self.retry_button.setEnabled(failed > 0)
