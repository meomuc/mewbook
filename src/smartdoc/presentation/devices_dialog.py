# SPDX-License-Identifier: AGPL-3.0-or-later
"""Máy đọc sách: the e-readers the person has named. Rename one, or forget it (the books on it and in the library are
not touched). A device is added from "Gửi sang máy đọc sách", where it is plugged in and can be asked about, so this
screen only manages the ones already there. The work is application/device_registry.py."""
from __future__ import annotations

from collections.abc import Callable

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QAbstractItemView,
    QInputDialog,
    QLabel,
    QMessageBox,
    QTableWidget,
    QTableWidgetItem,
)

from smartdoc.application.device_registry import Device, DeviceError
from smartdoc.domain.device_profiles import load_device_profiles
from smartdoc.infrastructure.devices.transport import ConnectedDevice, DeviceTransport, FolderTransport
from smartdoc.presentation.design_dialog import DesignDialog
from smartdoc.presentation.task_progress_dialog import run_with_progress
from smartdoc.presentation.theme_manager import theme_manager

_ID_ROLE = Qt.UserRole + 1


def _default_transport_for(device: Device) -> DeviceTransport | None:
    """The way in to a registered device, or None when there is none yet: a drive or card is a folder; a phone-like device
    (MTP) has no implementation of the seam yet."""
    return FolderTransport(device.folder) if device.kind == "drive" and device.folder else None
_KIND_LABEL = {"drive": "Ổ đĩa / thẻ nhớ", "mtp": "Thiết bị di động (MTP)"}


def ask_device_name(parent, connected: ConnectedDevice) -> str | None:
    """Asks what to call a device that is plugged in; None when the person backed out."""
    name, accepted = QInputDialog.getText(parent, "Đăng ký máy đọc sách", "Đặt tên cho máy này:", text=connected.name)
    name = name.strip()
    return name if accepted and name else None


class DevicesDialog(DesignDialog):
    def __init__(self, context, parent=None, *, transport_for: Callable[[Device], DeviceTransport | None] | None = None) -> None:
        super().__init__(parent, title="Máy đọc sách", subtitle="Những máy bạn đã đặt tên", icon="send", width=680)
        self.context = context
        self._transport_for = transport_for or _default_transport_for
        self._profiles = load_device_profiles()
        self.resize(720, 400)

        self.table = QTableWidget(0, 4, self)
        self.table.setHorizontalHeaderLabels(["TÊN", "LOẠI MÁY", "THƯ MỤC TRÊN MÁY", "KẾT NỐI"])
        self.table.verticalHeader().setVisible(False)
        self.table.setEditTriggers(QAbstractItemView.NoEditTriggers)
        self.table.setSelectionBehavior(QAbstractItemView.SelectRows)
        self.table.setSelectionMode(QAbstractItemView.SingleSelection)
        self.table.setShowGrid(False)
        self.table.horizontalHeader().setStretchLastSection(True)
        self.table.itemSelectionChanged.connect(self._update_buttons)
        self.body.addWidget(self.table, 1)
        self.empty_note = QLabel(self)
        self.empty_note.setWordWrap(True)
        self.empty_note.setStyleSheet(f"color: {theme_manager().token('ink3')};")
        self.body.addWidget(self.empty_note)

        self.check_button = self.add_footer_button("Kiểm tra máy", on_click=self._on_check, left=True)
        self.rename_button = self.add_footer_button("Đổi tên…", on_click=self._on_rename, left=True)
        self.forget_button = self.add_footer_button("Bỏ đăng ký…", "danger", on_click=self._on_forget, left=True)
        self.add_footer_button("Đóng", on_click=self.accept)
        self.refresh()

    def refresh(self) -> None:
        devices = self.context.devices.list()
        self.table.setRowCount(len(devices))
        for row, device in enumerate(devices):
            profile = self._profiles.get(device.profile_id)
            cells = (device.name, profile.display_name if profile else "Chưa chọn", device.folder or "Chưa chọn",
                     _KIND_LABEL.get(device.kind, device.kind))
            for column, text in enumerate(cells):
                cell = QTableWidgetItem(text)
                if column == 0:
                    cell.setData(_ID_ROLE, device.id)
                self.table.setItem(row, column, cell)
        self.empty_note.setText("" if devices else "Chưa có máy nào. Cắm máy đọc sách, mở “Gửi sang máy đọc sách” "
                                                   "rồi bấm “Đăng ký máy này…” để đặt tên.")
        self._update_buttons()

    def _selected(self) -> Device | None:
        rows = sorted({index.row() for index in self.table.selectedIndexes()})
        if not rows:
            return None
        return self.context.devices.get(self.table.item(rows[0], 0).data(_ID_ROLE))

    def _update_buttons(self) -> None:
        picked = self._selected() is not None
        self.check_button.setEnabled(picked)
        self.rename_button.setEnabled(picked)
        self.forget_button.setEnabled(picked)

    def _on_check(self) -> None:
        """Looks at the chosen device and says how many of the books sent to it are still there. Only this device's records
        change; the library is not touched."""
        device = self._selected()
        if device is None:
            return
        transport = self._transport_for(device)
        if transport is None:
            QMessageBox.information(self, "Chưa kiểm tra được", f"MewBook chưa hỗ trợ kiểm tra loại máy của “{device.name}”.")
            return
        result, error = run_with_progress(
            self, title="Kiểm tra máy", message=f"Mèo đang xem trong “{device.name}”…", delay_ms=400,
            work=lambda progress: self.context.devices.check(device, transport))
        if result is None:
            QMessageBox.warning(self, "Chưa kiểm tra được", f"Có lỗi khi kiểm tra máy: {error}")
            return
        if not result.checked:
            QMessageBox.information(self, "Máy chưa cắm", f"“{device.name}” chưa cắm hoặc MewBook chưa thấy máy. Cắm máy rồi thử lại.")
            return
        QMessageBox.information(self, "Đã kiểm tra",
                                f"{result.present} sách còn trên máy, {result.missing} sách không còn trên máy.")

    def _on_rename(self) -> None:
        device = self._selected()
        if device is None:
            return
        name, accepted = QInputDialog.getText(self, "Đổi tên máy", "Tên mới:", text=device.name)
        if not accepted:
            return
        try:
            self.context.devices.rename(device.id, name)
        except DeviceError as exc:
            QMessageBox.warning(self, "Chưa đổi được tên", str(exc))
            return
        self.refresh()

    def _on_forget(self) -> None:
        device = self._selected()
        if device is None:
            return
        answer = QMessageBox.question(
            self, "Bỏ đăng ký máy này?",
            f"MewBook sẽ quên “{device.name}”. Sách trên máy và sách trong thư viện không bị đụng tới. "
            "Lần sau cắm máy này, MewBook sẽ hỏi lại có phải máy mới không.",
            QMessageBox.Yes | QMessageBox.No, QMessageBox.No)
        if answer != QMessageBox.Yes:
            return
        self.context.devices.unregister(device.id)
        self.refresh()
