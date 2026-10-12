# SPDX-License-Identifier: AGPL-3.0-or-later
"""Tạo bộ sưu tập: just a name. A collection is the books the person puts in it (right-click a book, or "Lưu thành bộ
sưu tập" on a filter); it follows no rule, so there is nothing else to ask. Renaming and deleting are in the sidebar's menu.
"""
from __future__ import annotations

from PySide6.QtWidgets import QLabel, QLineEdit

from smartdoc.domain.smart_collections import VirtualCollection
from smartdoc.presentation.design_dialog import DesignDialog


class NewCollectionDialog(DesignDialog):
    def __init__(self, parent=None) -> None:
        super().__init__(parent, title="Tạo bộ sưu tập", subtitle="Bạn tự chọn những sách đưa vào; file sách không bị đụng tới.",
                         icon="folder", width=440)
        name_label = QLabel("TÊN BỘ SƯU TẬP", self)
        name_label.setObjectName("FieldHeading")
        self.name_edit = QLineEdit(self)
        self.name_edit.setPlaceholderText("Ví dụ: Sách mùa hè")
        self.body.addWidget(name_label)
        self.body.addWidget(self.name_edit)

        self.add_footer_button("Hủy", on_click=self.reject)
        self.create_button = self.add_footer_button("Tạo bộ sưu tập", "primary", on_click=self.accept)
        self.create_button.setEnabled(False)
        self.name_edit.textChanged.connect(lambda _text: self.create_button.setEnabled(self.build_collection() is not None))
        self.name_edit.returnPressed.connect(lambda: self.create_button.click() if self.create_button.isEnabled() else None)

    def build_collection(self) -> VirtualCollection | None:
        name = self.name_edit.text().strip()
        return VirtualCollection(name=name) if name else None
