"""TDD-021 UI: Duplicate Finder dialog.

Two tabs (exact / fuzzy matches), each a sortable checkbox table. Checking a
row and pressing "Xóa file" removes it from the library, optionally also
deleting the physical file -- never silently: the user always picks one of
the two explicitly (or cancels).

The exact tab is one indexed SQL query and fills in immediately. The fuzzy
tab's scan runs on a background thread with a progress bar: even with the
indexed search in application/duplicate_finder.py it takes a few seconds on
a large library, and it used to run inside this dialog's constructor on the
GUI thread -- which is what froze the whole app. Closing the dialog cancels
a scan still in progress.
"""
from __future__ import annotations

import threading
from datetime import datetime

from PySide6.QtCore import QPoint, Qt, QTimer
from PySide6.QtGui import QBrush, QColor
from PySide6.QtWidgets import (
    QDialog,
    QDialogButtonBox,
    QHBoxLayout,
    QLabel,
    QMenu,
    QMessageBox,
    QProgressBar,
    QPushButton,
    QTableWidget,
    QTableWidgetItem,
    QTabWidget,
    QVBoxLayout,
)

from smartdoc.application.duplicate_finder import DuplicateEngine, DuplicateSearchCancelled
from smartdoc.presentation.file_actions import FileActionEngine

_DOC_ROLE = Qt.UserRole + 1
_FUZZY_TAB_TITLE = "Có thể trùng (tiêu đề/tác giả gần giống)"
_MARKED_BRUSH = QBrush(QColor("#f5c2c7"))
_CLEAR_BRUSH = QBrush()  # resets to the table's default background


def _format_datetime(value) -> str:
    if not value:
        return "—"
    try:
        return datetime.fromtimestamp(value).strftime("%d/%m/%Y %H:%M")
    except (TypeError, ValueError, OSError):
        return "—"


class _DateTableWidgetItem(QTableWidgetItem):
    """Sorts by the raw timestamp, not the formatted display string."""

    def __init__(self, timestamp) -> None:
        super().__init__(_format_datetime(timestamp))
        self._timestamp = timestamp or 0.0

    def __lt__(self, other) -> bool:
        if isinstance(other, _DateTableWidgetItem):
            return self._timestamp < other._timestamp
        return super().__lt__(other)


class DuplicateFinderDialog(QDialog):
    def __init__(self, context, parent=None) -> None:
        super().__init__(parent)
        self.context = context
        self.engine = DuplicateEngine(context)
        self.file_actions = FileActionEngine(context)
        self._exact_groups: list[list[dict]] = []
        self._fuzzy_groups: list[list[dict]] = []
        # Each scan gets a new generation number; results/progress from an
        # older (superseded or cancelled) scan are ignored on arrival.
        self._scan_generation = 0
        self._cancel_scan = threading.Event()
        # The worker thread never touches a Qt object (emitting a signal on a
        # dialog destroyed mid-scan is a hard crash, not an exception): it
        # only writes plain Python values into this dict, and a timer owned
        # by the dialog -- so it dies with it -- picks them up on the GUI
        # thread.
        self._scan_state: dict = {}
        self._scan_poll = QTimer(self)
        self._scan_poll.setInterval(50)
        self._scan_poll.timeout.connect(self._poll_fuzzy_scan)

        self.setWindowTitle("Dọn dẹp trùng lặp")
        self.resize(760, 480)
        self.setMaximumSize(1100, 800)  # a long duplicate list shouldn't be able to balloon the window

        self.exact_table = self._build_table()
        self.fuzzy_table = self._build_table()
        self.tabs = QTabWidget(self)
        self.tabs.addTab(self.exact_table, "Trùng hoàn toàn (nội dung giống hệt)")
        self.tabs.addTab(self.fuzzy_table, _FUZZY_TAB_TITLE)

        self.scan_status_label = QLabel(self)
        self.scan_progress = QProgressBar(self)
        self.scan_progress.setTextVisible(True)
        self.scan_progress.setMaximumHeight(14)

        refresh_button = QPushButton("🔄 Quét lại")
        refresh_button.clicked.connect(self.refresh)

        self.select_duplicates_button = QPushButton("✅ Chọn file trùng ▾")
        self.select_duplicates_button.clicked.connect(self._on_select_duplicates)

        self.delete_button = QPushButton("🗑️ Xóa file ▾")
        self.delete_button.clicked.connect(self._on_delete_selected)

        action_row = QHBoxLayout()
        action_row.addWidget(refresh_button)
        action_row.addWidget(self.select_duplicates_button)
        action_row.addStretch(1)
        action_row.addWidget(self.delete_button)

        close_buttons = QDialogButtonBox(QDialogButtonBox.Close)
        close_buttons.rejected.connect(self.accept)

        layout = QVBoxLayout(self)
        layout.addWidget(self.tabs)
        layout.addWidget(self.scan_status_label)
        layout.addWidget(self.scan_progress)
        layout.addLayout(action_row)
        layout.addWidget(close_buttons)

        self.refresh()

    @staticmethod
    def _build_table() -> QTableWidget:
        table = QTableWidget(0, 4)
        table.setHorizontalHeaderLabels(["Tiêu đề", "Tác giả", "Ngày thêm", "Đường dẫn file"])
        table.horizontalHeader().setStretchLastSection(True)
        table.horizontalHeader().setSortIndicatorShown(True)
        table.setSortingEnabled(True)
        table.verticalHeader().setVisible(False)
        return table

    def _exec_menu(self, menu: QMenu, global_position):
        """Thin seam so tests can patch this instead of QMenu.exec, which
        opens a real modal loop that hangs forever under an offscreen Qt
        platform (see library_view.LibraryListWidget._exec_menu)."""
        return menu.exec(global_position)

    def refresh(self) -> None:
        self._exact_groups = self.engine.find_exact_duplicates()
        self._populate(self.exact_table, self._exact_groups)
        self._start_fuzzy_scan()

    # -- Fuzzy scan on a background thread ---------------------------------

    def _start_fuzzy_scan(self) -> None:
        self._cancel_scan.set()  # stop any scan still running from before
        self._cancel_scan = threading.Event()
        self._scan_generation += 1
        generation, cancel = self._scan_generation, self._cancel_scan

        self._fuzzy_groups = []
        self._populate(self.fuzzy_table, [])
        self.tabs.setTabText(1, f"{_FUZZY_TAB_TITLE} -- đang quét...")
        self.scan_status_label.setText("Đang tìm các tài liệu có tiêu đề/tác giả gần giống nhau...")
        self.scan_progress.setRange(0, 0)  # indeterminate until the first progress report
        self.scan_progress.show()

        # Read here, on the GUI thread (one quick query); the worker only
        # does the comparison. A worker holding the shared database
        # connection could otherwise still be mid-query when the app closes
        # that connection on exit -- a hard crash, not an exception.
        docs = self.context.db.list_documents_for_dedup()

        # A fresh dict per scan: a superseded worker keeps writing into its
        # own, which nobody reads any more.
        state: dict = {"generation": generation}
        self._scan_state = state
        engine = self.engine

        def worker() -> None:
            def progress(done: int, total: int) -> None:
                state["progress"] = (done, total)

            try:
                groups = engine.find_fuzzy_duplicates(progress=progress, should_cancel=cancel.is_set, docs=docs)
            except DuplicateSearchCancelled:
                return
            except Exception as exc:  # a scan failure must not take the dialog down with it
                state["result"] = ([], str(exc))
                return
            state["result"] = (groups, "")

        threading.Thread(target=worker, daemon=True).start()
        self._scan_poll.start()

    def _poll_fuzzy_scan(self) -> None:
        state = self._scan_state
        generation = state.get("generation", -1)
        if "result" in state:
            self._scan_poll.stop()
            groups, error = state["result"]
            self._on_fuzzy_finished(generation, groups, error)
        elif "progress" in state:
            self._on_fuzzy_progress(generation, *state["progress"])

    def _on_fuzzy_progress(self, generation: int, done: int, total: int) -> None:
        if generation != self._scan_generation or total <= 0:
            return
        self.scan_progress.setRange(0, total)
        self.scan_progress.setValue(done)
        self.scan_progress.setFormat(f"%p%  ({done}/{total} tài liệu)")

    def _on_fuzzy_finished(self, generation: int, groups: list, error: str) -> None:
        if generation != self._scan_generation:
            return
        self.scan_progress.hide()
        if error:
            self.tabs.setTabText(1, _FUZZY_TAB_TITLE)
            self.scan_status_label.setText(f"Không quét được tài liệu gần giống: {error}")
            return
        self._fuzzy_groups = groups
        self._populate(self.fuzzy_table, groups)
        self.tabs.setTabText(1, f"{_FUZZY_TAB_TITLE} ({len(groups)} nhóm)")
        self.scan_status_label.setText(
            f"Trùng hoàn toàn: {len(self._exact_groups)} nhóm  ·  Có thể trùng: {len(groups)} nhóm"
        )

    def wait_for_scan(self, timeout: float = 10.0) -> bool:
        """For tests: pump events until the current fuzzy scan reports back."""
        import time

        from PySide6.QtWidgets import QApplication

        deadline = time.time() + timeout
        while time.time() < deadline:
            QApplication.processEvents()
            if self.scan_progress.isHidden():
                return True
            time.sleep(0.01)
        return False

    def done(self, result: int) -> None:  # noqa: D401 -- Qt override
        # Closing (any way: Close button, Esc, [x]) stops a scan in progress
        # rather than leaving it churning in the background.
        self._cancel_scan.set()
        self._scan_poll.stop()
        super().done(result)

    def _populate(self, table: QTableWidget, groups: list[list[dict]]) -> None:
        table.setSortingEnabled(False)
        table.setRowCount(0)
        table.setRowCount(sum(len(group) for group in groups))
        row = 0
        for group in groups:
            for doc in group:

                title_item = QTableWidgetItem(doc.get("title", ""))
                title_item.setFlags(title_item.flags() | Qt.ItemIsUserCheckable)
                title_item.setCheckState(Qt.Unchecked)
                title_item.setData(_DOC_ROLE, doc)
                table.setItem(row, 0, title_item)
                table.setItem(row, 1, QTableWidgetItem(doc.get("author", "")))
                table.setItem(row, 2, _DateTableWidgetItem(doc.get("created_at")))
                table.setItem(row, 3, QTableWidgetItem(doc.get("file_path", "")))
                row += 1
        table.setSortingEnabled(True)
        # Sorted by the first column by default, same as the user would get
        # by clicking its header once.
        table.sortItems(0, Qt.AscendingOrder)

    def _current_groups(self) -> list[list[dict]]:
        return self._exact_groups if self.tabs.currentWidget() is self.exact_table else self._fuzzy_groups

    def _on_select_duplicates(self) -> None:
        menu = QMenu(self)
        newest_action = menu.addAction("Ưu tiên giữ file thêm mới nhất (mặc định)")
        oldest_action = menu.addAction("Ưu tiên giữ file thêm lâu nhất")
        chosen = self._exec_menu(
            menu, self.select_duplicates_button.mapToGlobal(QPoint(0, self.select_duplicates_button.height()))
        )
        if chosen == oldest_action:
            self._apply_duplicate_selection(keep_newest=False)
        elif chosen == newest_action:
            self._apply_duplicate_selection(keep_newest=True)

    def _apply_duplicate_selection(self, keep_newest: bool) -> None:
        """Marks every document in a duplicate group for deletion except the
        one to keep (newest-added by default, or oldest-added), and colors
        the marked rows so they're visually distinct from the kept one."""
        table = self.tabs.currentWidget()
        groups = self._current_groups()

        keep_ids: set[str] = set()
        for group in groups:
            kept = max(group, key=lambda d: d.get("created_at") or 0) if keep_newest else min(
                group, key=lambda d: d.get("created_at") or 0
            )
            keep_ids.add(kept["id"])

        for row in range(table.rowCount()):
            title_item = table.item(row, 0)
            doc = title_item.data(_DOC_ROLE)
            mark_for_deletion = doc["id"] not in keep_ids
            title_item.setCheckState(Qt.Checked if mark_for_deletion else Qt.Unchecked)
            brush = _MARKED_BRUSH if mark_for_deletion else _CLEAR_BRUSH
            for col in range(table.columnCount()):
                cell = table.item(row, col)
                if cell:
                    cell.setBackground(brush)

    def _on_delete_selected(self) -> None:
        current_table = self.tabs.currentWidget()
        selected_docs = []
        for row in range(current_table.rowCount()):
            item = current_table.item(row, 0)
            if item.checkState() == Qt.Checked:
                selected_docs.append(item.data(_DOC_ROLE))

        if not selected_docs:
            return

        menu = QMenu(self)
        library_only_action = menu.addAction("Xóa khỏi thư viện")
        library_and_disk_action = menu.addAction("Xóa khỏi thư viện và thư mục gốc")
        menu.addSeparator()
        menu.addAction("Hủy bỏ")
        chosen = self._exec_menu(menu, self.delete_button.mapToGlobal(QPoint(0, self.delete_button.height())))
        if chosen not in (library_only_action, library_and_disk_action):
            return

        delete_physical = chosen == library_and_disk_action
        confirm_text = (
            f"Xóa {len(selected_docs)} tài liệu đã chọn khỏi thư viện VÀ xóa file gốc trên đĩa? "
            "Hành động này không thể hoàn tác."
            if delete_physical
            else f"Xóa {len(selected_docs)} tài liệu đã chọn khỏi thư viện? (File gốc trên đĩa sẽ không bị xóa.)"
        )
        confirm = QMessageBox.question(self, "Xóa file", confirm_text)
        if confirm == QMessageBox.Yes:
            self.file_actions.delete_documents(
                [(doc["id"], doc.get("file_path")) for doc in selected_docs], delete_physical_file=delete_physical
            )
            # Deleting can only *remove* duplicates, never create new ones,
            # so drop the deleted documents from the groups already found
            # rather than re-running the whole scan.
            deleted_ids = {doc["id"] for doc in selected_docs}
            self._exact_groups = self._without(self._exact_groups, deleted_ids)
            self._fuzzy_groups = self._without(self._fuzzy_groups, deleted_ids)
            self._populate(self.exact_table, self._exact_groups)
            self._populate(self.fuzzy_table, self._fuzzy_groups)

    @staticmethod
    def _without(groups: list[list[dict]], deleted_ids: set[str]) -> list[list[dict]]:
        remaining = [[doc for doc in group if doc["id"] not in deleted_ids] for group in groups]
        return [group for group in remaining if len(group) > 1]


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
