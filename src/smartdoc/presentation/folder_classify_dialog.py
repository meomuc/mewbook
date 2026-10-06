# SPDX-License-Identifier: AGPL-3.0-or-later
"""Dialog: "Gán nhãn theo thư mục lưu trữ".

Shows every folder whose name the taxonomy can resolve, together with how many
"Chưa chắc" books live in it.  The user ticks which folders to process and
clicks "Áp dụng" — one tag_books() call per folder group.

Kept simple: a QTableWidget with one row per FolderGroup (checkbox | folder |
category | count).  No tree, no preview of titles.  The user can open the
classify wizard after to review any remaining books.
"""
from __future__ import annotations

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QAbstractItemView,
    QDialog,
    QDialogButtonBox,
    QFrame,
    QLabel,
    QPushButton,
    QTableWidget,
    QTableWidgetItem,
    QVBoxLayout,
)

from smartdoc.application.folder_classify import FolderGroup, build_folder_groups
from smartdoc.application.smart_classifier import UNSURE_TAG
from smartdoc.core.app_context import AppContext
from smartdoc.domain.library_filter import LibraryFilter


class FolderClassifyDialog(QDialog):
    """One-shot dialog for bulk-tagging "Chưa chắc" books by storage folder."""

    def __init__(self, context: AppContext, parent=None, smart_classifier=None) -> None:
        super().__init__(parent)
        self.context = context
        # SmartClassifyService lives on MainWindow, not AppContext; the caller passes it in.
        self._classifier = smart_classifier
        self.setWindowTitle("Gán nhãn theo thư mục lưu trữ")
        self.setMinimumWidth(560)
        self.setMinimumHeight(380)

        self._groups: list[FolderGroup] = []
        self._applied = 0

        root = QVBoxLayout(self)
        root.setSpacing(8)
        root.setContentsMargins(16, 12, 16, 12)

        self._info = QLabel(self)
        self._info.setWordWrap(True)
        self._info.setObjectName("FieldCaption")
        root.addWidget(self._info)

        self._table = QTableWidget(self)
        self._table.setColumnCount(4)
        self._table.setHorizontalHeaderLabels(["", "Thư mục", "Hashtag sẽ gán", "Số sách"])
        self._table.horizontalHeader().setStretchLastSection(False)
        self._table.horizontalHeader().setSectionResizeMode(1, self._table.horizontalHeader().Stretch)
        self._table.verticalHeader().hide()
        self._table.setEditTriggers(QAbstractItemView.NoEditTriggers)
        self._table.setSelectionMode(QAbstractItemView.NoSelection)
        self._table.setFrameShape(QFrame.NoFrame)
        self._table.setAlternatingRowColors(True)
        root.addWidget(self._table)

        self._status_label = QLabel("", self)
        self._status_label.setObjectName("FieldCaption")
        root.addWidget(self._status_label)

        btns = QDialogButtonBox(self)
        self._apply_btn = QPushButton("Áp dụng")
        self._apply_btn.setDefault(True)
        close_btn = QPushButton("Đóng")
        btns.addButton(self._apply_btn, QDialogButtonBox.AcceptRole)
        btns.addButton(close_btn, QDialogButtonBox.RejectRole)
        self._apply_btn.clicked.connect(self._apply)
        close_btn.clicked.connect(self.reject)
        root.addWidget(btns)

        self._load()

    # -- data ---------------------------------------------------------------------------------

    def _load(self) -> None:
        if self._classifier is None:
            self._info.setText("Không có dịch vụ phân loại.")
            self._apply_btn.setEnabled(False)
            return
        self._groups = build_folder_groups(self.context, self._classifier)
        where_sql, params = self.context.db.filter_where(LibraryFilter(tags=(UNSURE_TAG,)))
        total_unsure = len(self.context.db.query_documents(where_sql=where_sql, params=params, limit=100000))
        matched = sum(len(g.doc_ids) for g in self._groups)

        if not self._groups:
            self._info.setText(
                "Không tìm thấy thư mục nào có thể ánh xạ sang hashtag thể loại.\n"
                "Hãy đảm bảo tên thư mục lưu trữ khớp với tên thể loại trong phân loại của Mèo.")
            self._apply_btn.setEnabled(False)
            return

        matched_pct = int(matched / total_unsure * 100) if total_unsure else 0
        self._info.setText(
            f"Mèo tìm thấy {len(self._groups)} nhóm thư mục khớp với thể loại, "
            f'bao gồm {matched:,} / {total_unsure:,} sách "Chưa chắc" ({matched_pct}%). '
            "Tick các nhóm muốn gán nhãn, rồi nhấn Áp dụng.")
        self._apply_btn.setEnabled(True)

        self._table.setRowCount(len(self._groups))
        for row, group in enumerate(self._groups):
            chk = QTableWidgetItem()
            chk.setFlags(Qt.ItemIsUserCheckable | Qt.ItemIsEnabled)
            chk.setCheckState(Qt.Checked)
            self._table.setItem(row, 0, chk)
            self._table.setItem(row, 1, QTableWidgetItem(group.folder))
            self._table.setItem(row, 2, QTableWidgetItem(f"#{group.category.name}"))
            count_item = QTableWidgetItem(f"{len(group.doc_ids):,}")
            count_item.setTextAlignment(Qt.AlignRight | Qt.AlignVCenter)
            self._table.setItem(row, 3, count_item)

        self._table.resizeColumnsToContents()
        self._table.setColumnWidth(0, 30)

    # -- actions ------------------------------------------------------------------------------

    def _apply(self) -> None:
        self._apply_btn.setEnabled(False)
        self._applied = 0
        for row, group in enumerate(self._groups):
            chk = self._table.item(row, 0)
            if chk and chk.checkState() == Qt.Checked:
                _tag, count = self._classifier.tag_books(group.doc_ids, group.category.name)
                self._applied += count
                item = self._table.item(row, 2)
                if item:
                    item.setText(f"#{group.category.name} ✓")
        self._status_label.setText(f"Đã gán nhãn {self._applied:,} sách.")
        self._load()  # refresh counts after tagging
