"""TDD-021 UI: Duplicate Finder dialog.

Two tabs (exact / fuzzy matches), each a checkbox table. Checking a row and
pressing delete removes it from the library only -- never the file on disk
(the app's Single Source of Truth rule) -- exactly like the single/bulk
delete actions in library_view.py.
"""
from __future__ import annotations

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QDialog,
    QDialogButtonBox,
    QHBoxLayout,
    QMessageBox,
    QPushButton,
    QTableWidget,
    QTableWidgetItem,
    QTabWidget,
    QVBoxLayout,
)

from smartdoc.application.duplicate_finder import DuplicateEngine
from smartdoc.presentation.file_actions import FileActionEngine

_DOC_ROLE = Qt.UserRole + 1


class DuplicateFinderDialog(QDialog):
    def __init__(self, context, parent=None) -> None:
        super().__init__(parent)
        self.context = context
        self.engine = DuplicateEngine(context)
        self.file_actions = FileActionEngine(context)

        self.setWindowTitle("Dọn dẹp trùng lặp")
        self.resize(720, 480)

        self.exact_table = self._build_table()
        self.fuzzy_table = self._build_table()
        self.tabs = QTabWidget(self)
        self.tabs.addTab(self.exact_table, "Trùng hoàn toàn (nội dung giống hệt)")
        self.tabs.addTab(self.fuzzy_table, "Có thể trùng (tiêu đề/tác giả gần giống)")

        refresh_button = QPushButton("Quét lại")
        refresh_button.clicked.connect(self.refresh)
        delete_button = QPushButton("Xóa các mục đã chọn khỏi thư viện")
        delete_button.clicked.connect(self._on_delete_selected)

        action_row = QHBoxLayout()
        action_row.addWidget(refresh_button)
        action_row.addStretch(1)
        action_row.addWidget(delete_button)

        close_buttons = QDialogButtonBox(QDialogButtonBox.Close)
        close_buttons.rejected.connect(self.accept)

        layout = QVBoxLayout(self)
        layout.addWidget(self.tabs)
        layout.addLayout(action_row)
        layout.addWidget(close_buttons)

        self.refresh()

    @staticmethod
    def _build_table() -> QTableWidget:
        table = QTableWidget(0, 3)
        table.setHorizontalHeaderLabels(["Tiêu đề", "Tác giả", "Đường dẫn file"])
        table.horizontalHeader().setStretchLastSection(True)
        table.verticalHeader().setVisible(False)
        return table

    def refresh(self) -> None:
        self._populate(self.exact_table, self.engine.find_exact_duplicates())
        self._populate(self.fuzzy_table, self.engine.find_fuzzy_duplicates())

    def _populate(self, table: QTableWidget, groups: list[list[dict]]) -> None:
        table.setRowCount(0)
        row = 0
        for group in groups:
            for doc in group:
                table.insertRow(row)

                title_item = QTableWidgetItem(doc.get("title", ""))
                title_item.setFlags(title_item.flags() | Qt.ItemIsUserCheckable)
                title_item.setCheckState(Qt.Unchecked)
                title_item.setData(_DOC_ROLE, doc)
                table.setItem(row, 0, title_item)
                table.setItem(row, 1, QTableWidgetItem(doc.get("author", "")))
                table.setItem(row, 2, QTableWidgetItem(doc.get("file_path", "")))
                row += 1

    def _on_delete_selected(self) -> None:
        current_table = self.tabs.currentWidget()
        selected_docs = []
        for row in range(current_table.rowCount()):
            item = current_table.item(row, 0)
            if item.checkState() == Qt.Checked:
                selected_docs.append(item.data(_DOC_ROLE))

        if not selected_docs:
            return

        confirm = QMessageBox.question(
            self,
            "Xóa khỏi thư viện",
            f"Xóa {len(selected_docs)} tài liệu đã chọn khỏi thư viện? (File gốc trên đĩa sẽ không bị xóa.)",
        )
        if confirm == QMessageBox.Yes:
            self.file_actions.delete_documents(
                [(doc["id"], doc.get("file_path")) for doc in selected_docs], delete_physical_file=False
            )
            self.refresh()


if __name__ == "__main__":
    import sys
    import tempfile
    from pathlib import Path

    from PySide6.QtWidgets import QApplication

    from smartdoc.core.app_context import AppContext
    from smartdoc.presentation.theme import apply_light_theme

    with tempfile.TemporaryDirectory() as tmp:
        context = AppContext.create_in_memory(Path(tmp))
        context.db.add_or_update_document(
            "d1", {"title": "Sach A", "author": "X", "file_path": "a.pdf", "content_hash": "h1", "created_at": 1.0}
        )
        context.db.add_or_update_document(
            "d2", {"title": "Sach A (copy)", "author": "X", "file_path": "a2.pdf", "content_hash": "h1", "created_at": 2.0}
        )

        app = QApplication(sys.argv)
        apply_light_theme(app)
        DuplicateFinderDialog(context).exec()
