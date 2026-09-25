"""Metadata suggestions: look a book up, review the differences, apply what you accept.

Nothing is changed until "Áp dụng" is pressed. The table lists, for the chosen
candidate, every field whose suggested value differs from the current one --
ticked by default only where the current value is empty or a placeholder
(an untitled scan, "Unknown"); a field that already has a different value is
shown but left unticked, and a field the user typed by hand is not offered at
all. A separate box decides whether the update is also written into the book
file (backed up first, see application/metadata_writer.py).

The lookup runs on a background thread (application/metadata_lookup.py) and
reports back through a signal, like the cover search dialog.
"""
from __future__ import annotations

import logging
import threading
from pathlib import Path

from PySide6.QtCore import Qt, Signal
from PySide6.QtWidgets import (
    QAbstractItemView,
    QApplication,
    QCheckBox,
    QDialog,
    QHBoxLayout,
    QHeaderView,
    QLabel,
    QLineEdit,
    QListWidget,
    QListWidgetItem,
    QMessageBox,
    QPushButton,
    QSpinBox,
    QTableWidget,
    QTableWidgetItem,
    QVBoxLayout,
    QWidget,
)

from smartdoc.application.metadata_applier import MetadataApplier, MetadataApplyError
from smartdoc.application.metadata_lookup import LookupResult, MetadataLookupService
from smartdoc.application.metadata_writer import MetadataWriter

logger = logging.getLogger(__name__)

FIELD_LABELS = {
    "title": "Tiêu đề",
    "author": "Tác giả",
    "publisher": "Nhà xuất bản",
    "pub_year": "Năm xuất bản",
    "language": "Ngôn ngữ",
    "isbn": "ISBN",
    "series": "Bộ sách",
    "description": "Mô tả",
}
_FIELD_ORDER = tuple(FIELD_LABELS)

# Said whenever the choice to write into the book file is offered: this is the one action here that changes the
# user's own file, so it is stated plainly and in the first line.
_WRITE_WARNING = (
    "Khi chọn, thông tin mới sẽ được ghi đè trực tiếp lên file sách. "
    "Nếu không chọn, chỉ thư viện thay đổi và file sách giữ nguyên."
)
_MAX_CELL_CHARS = 90

_COL_CHECK, _COL_FIELD, _COL_CURRENT, _COL_SUGGESTED = range(4)


def is_placeholder(field: str, value, doc: dict) -> bool:
    """A current value that says "nothing here yet": blank, an untitled scan
    (the file name used as title), or an unknown author."""
    text = " ".join(str(value or "").split())
    if not text:
        return True
    if field == "title":
        return text.lower() == "untitled" or text == " ".join(Path(doc.get("file_path") or "").stem.split())
    if field == "author":
        return text.lower() == "unknown"
    return False


def _shorten(text: str) -> str:
    text = " ".join(str(text).split())
    return text if len(text) <= _MAX_CELL_CHARS else text[: _MAX_CELL_CHARS - 1].rstrip() + "…"


class MetadataSuggestDialog(QDialog):
    lookup_finished = Signal(int, object, str)  # (search number, LookupResult | None, error message)

    def __init__(self, context, doc: dict, parent=None, service=None, applier=None) -> None:
        super().__init__(parent)
        self.context = context
        self.doc = doc
        self.applied = False  # something was applied or undone: callers refresh
        self._service = service or MetadataLookupService(context)
        self._applier = applier or MetadataApplier(context)
        self._candidates: list = []
        self._search_number = 0

        self.setWindowTitle(f"Tìm thông tin sách: {doc.get('title', '')}")
        self.resize(820, 620)

        self.title_edit = QLineEdit(doc.get("title", "") or "", self)
        self.author_edit = QLineEdit(doc.get("author", "") or "", self)
        self.search_button = QPushButton("Tìm kiếm", self)
        self.search_button.clicked.connect(lambda: self._start_search(include_internet=False))
        search_row = QHBoxLayout()
        search_row.addWidget(QLabel("Tiêu đề:"))
        search_row.addWidget(self.title_edit, stretch=1)
        search_row.addWidget(QLabel("Tác giả:"))
        search_row.addWidget(self.author_edit, stretch=1)
        search_row.addWidget(self.search_button)

        self.status_label = QLabel("", self)
        self.status_label.setWordWrap(True)
        self.internet_button = QPushButton("Tìm thêm trên internet", self)
        self.internet_button.clicked.connect(lambda: self._start_search(include_internet=True))
        self.internet_button.setEnabled(False)
        status_row = QHBoxLayout()
        status_row.addWidget(self.status_label, stretch=1)
        status_row.addWidget(self.internet_button)

        self.candidate_list = QListWidget(self)
        self.candidate_list.setMaximumHeight(150)
        self.candidate_list.currentRowChanged.connect(self._show_candidate)

        self.table = QTableWidget(0, 4, self)
        self.table.setHorizontalHeaderLabels(["", "Thông tin", "Hiện tại", "Đề xuất"])
        self.table.verticalHeader().setVisible(False)
        self.table.setEditTriggers(QAbstractItemView.NoEditTriggers)
        self.table.setSelectionMode(QAbstractItemView.NoSelection)
        self.table.setWordWrap(True)
        header = self.table.horizontalHeader()
        header.setSectionResizeMode(_COL_CHECK, QHeaderView.ResizeToContents)
        header.setSectionResizeMode(_COL_FIELD, QHeaderView.ResizeToContents)
        header.setSectionResizeMode(_COL_CURRENT, QHeaderView.Stretch)
        header.setSectionResizeMode(_COL_SUGGESTED, QHeaderView.Stretch)
        self.table.itemChanged.connect(lambda _item: self._update_apply_enabled())

        self.write_check = QCheckBox("Ghi đè lên file sách gốc", self)
        self.write_hint = QLabel("", self)
        self.write_hint.setWordWrap(True)
        self.write_hint.setStyleSheet("color: palette(mid);")
        # How many copies of the old file are kept before it is changed. The same number as in Settings.
        self.backup_spin = QSpinBox(self)
        self.backup_spin.setRange(1, 20)
        self.backup_spin.setValue(max(1, int(self.context.config.config.metadata_backup_keep)))
        self.backup_spin.setToolTip("Mỗi lần ghi đè, file cũ được cất lại trước. Số này là số bản cất lại cho mỗi sách.")
        self.backup_row = QWidget(self)
        backup_layout = QHBoxLayout(self.backup_row)
        backup_layout.setContentsMargins(24, 0, 0, 0)
        backup_layout.addWidget(QLabel("Trước khi ghi đè, giữ lại tối đa"))
        backup_layout.addWidget(self.backup_spin)
        backup_layout.addWidget(QLabel("bản sao lưu file cũ cho mỗi sách."))
        backup_layout.addStretch(1)
        self.write_check.toggled.connect(lambda _checked: self._update_backup_row())
        self._setup_write_option()

        self.apply_button = QPushButton("Áp dụng", self)
        self.apply_button.setEnabled(False)
        self.apply_button.clicked.connect(self._on_apply)
        self.undo_button = QPushButton("Hoàn tác lần cập nhật gần nhất", self)
        self.undo_button.clicked.connect(self._on_undo)
        close_button = QPushButton("Đóng", self)
        close_button.clicked.connect(self.reject)
        button_row = QHBoxLayout()
        button_row.addWidget(self.undo_button)
        button_row.addStretch(1)
        button_row.addWidget(self.apply_button)
        button_row.addWidget(close_button)

        layout = QVBoxLayout(self)
        layout.addLayout(search_row)
        layout.addLayout(status_row)
        layout.addWidget(QLabel("Kết quả tìm được:"))
        layout.addWidget(self.candidate_list)
        layout.addWidget(self.table, stretch=1)
        layout.addWidget(self.write_check)
        layout.addWidget(self.write_hint)
        layout.addWidget(self.backup_row)
        layout.addLayout(button_row)

        self.lookup_finished.connect(self._on_lookup_finished)
        self._refresh_undo_button()
        if self.title_edit.text().strip():
            self._start_search(include_internet=False)

    # -- the "write into the file" option ---------------------------------------------

    def _setup_write_option(self) -> None:
        extension = (self.doc.get("extension") or "").lower()
        writable = MetadataWriter.writable_fields(extension)
        if not writable:
            self.write_check.setChecked(False)
            self.write_check.setEnabled(False)
            self.write_hint.setText(
                f"Định dạng .{extension or '?'} chưa cho ghi thông tin vào file, nên chỉ thư viện thay đổi; file sách giữ nguyên."
            )
            self._update_backup_row()
            return
        self.write_check.setChecked(bool(self.context.config.config.metadata_write_to_file_default))
        if len(writable) == len(_FIELD_ORDER):
            detail = "Ghi được tất cả thông tin."
        else:
            names = ", ".join(FIELD_LABELS[f] for f in writable)
            detail = f"Định dạng .{extension} chỉ ghi được: {names}. Phần còn lại chỉ lưu trong thư viện."
        self.write_hint.setText(f"{_WRITE_WARNING} {detail} Nếu ghi nhầm, bấm \"Hoàn tác\" để trả file về như cũ.")
        self._update_backup_row()

    def _update_backup_row(self) -> None:
        """The backup count only matters while overwriting the file is switched on."""
        self.backup_row.setEnabled(self.write_check.isEnabled() and self.write_check.isChecked())

    # -- search -----------------------------------------------------------------------

    def _start_search(self, *, include_internet: bool) -> None:
        title, author = self.title_edit.text().strip(), self.author_edit.text().strip()
        if not title:
            QMessageBox.warning(self, "Thiếu tiêu đề", "Vui lòng nhập tiêu đề để tìm thông tin sách.")
            return
        self._search_number += 1
        number = self._search_number
        self.status_label.setText("Đang tìm kiếm..." if not include_internet else "Đang tìm trên internet...")
        self.search_button.setEnabled(False)
        self.internet_button.setEnabled(False)
        self.candidate_list.clear()
        self.table.setRowCount(0)
        self._update_apply_enabled()

        def worker() -> None:
            try:
                result, error = self._service.lookup(self.doc, title=title, author=author, include_internet=include_internet), ""
            except Exception as exc:  # noqa: BLE001 -- the dialog must show a message, never crash on a lookup bug
                logger.exception("Metadata lookup failed")
                result, error = None, str(exc)
            try:
                self.lookup_finished.emit(number, result, error)
            except RuntimeError:
                pass  # the dialog was closed while searching

        threading.Thread(target=worker, daemon=True).start()

    def _on_lookup_finished(self, number: int, result: LookupResult | None, error: str) -> None:
        if number != self._search_number:
            return  # a newer search superseded this one
        self.search_button.setEnabled(True)
        if result is None:
            self.status_label.setText(f"Tìm kiếm thất bại: {error}")
            return
        self._candidates = list(result.candidates)
        self.internet_button.setEnabled(not result.searched_internet)
        for candidate in self._candidates:
            label = f"[{candidate.source}]  {candidate.title or '(không có tiêu đề)'}"
            if candidate.author:
                label += f" — {candidate.author}"
            if candidate.tier != 0:  # the file's own data is not a "match" to anything
                label += f"   · khớp {round(candidate.score * 100)}%"
            self.candidate_list.addItem(QListWidgetItem(label))

        parts = []
        if self._candidates:
            parts.append(f"Tìm thấy {len(self._candidates)} kết quả -- chọn một kết quả rồi đánh dấu những thông tin muốn cập nhật.")
        else:
            parts.append("Không tìm thấy thông tin phù hợp. Hãy sửa tiêu đề hoặc tác giả rồi tìm lại.")
        if not result.searched_internet:
            parts.append("Chưa tìm trên internet.")
        if result.errors:
            parts.append("Một số nơi tìm chưa trả lời được: " + "; ".join(result.errors))
        self.status_label.setText(" ".join(parts))
        if self._candidates:
            # Start on the best real lookup result; what the file itself says (tier 0) is
            # listed first but is often a leftover ("Microsoft Word - doc1") rather than an answer.
            self.candidate_list.setCurrentRow(next((i for i, c in enumerate(self._candidates) if c.tier != 0), 0))

    # -- the comparison table -----------------------------------------------------------

    def _current_doc(self) -> dict:
        return self.context.db.get_document(self.doc["id"]) or self.doc

    def _show_candidate(self, row: int) -> None:
        self.table.blockSignals(True)
        self.table.setRowCount(0)
        if 0 <= row < len(self._candidates):
            candidate = self._candidates[row]
            doc = self._current_doc()
            locked = self.context.db.locked_fields(self.doc["id"])
            for name in _FIELD_ORDER:
                if name not in candidate.fields or name in locked:
                    continue
                suggested, current = str(candidate.fields[name]), doc.get(name)
                current_text = "" if current is None else str(current)
                if current_text.strip().casefold() == suggested.strip().casefold():
                    continue  # nothing new
                self._add_row(name, current_text, suggested, tick=is_placeholder(name, current_text, doc))
            if self.table.rowCount() == 0:
                self.status_label.setText("Kết quả này không có gì mới so với thông tin hiện tại.")
        self.table.blockSignals(False)
        self.table.resizeRowsToContents()
        self._update_apply_enabled()

    def _add_row(self, name: str, current: str, suggested: str, *, tick: bool) -> None:
        row = self.table.rowCount()
        self.table.insertRow(row)
        check = QTableWidgetItem()
        check.setFlags(Qt.ItemIsUserCheckable | Qt.ItemIsEnabled)
        check.setCheckState(Qt.Checked if tick else Qt.Unchecked)
        check.setData(Qt.UserRole, name)
        self.table.setItem(row, _COL_CHECK, check)
        for column, text in ((_COL_FIELD, FIELD_LABELS[name]), (_COL_CURRENT, current), (_COL_SUGGESTED, suggested)):
            item = QTableWidgetItem(_shorten(text) if column != _COL_FIELD else text)
            item.setFlags(Qt.ItemIsEnabled)
            item.setToolTip(text)
            self.table.setItem(row, column, item)

    def checked_changes(self) -> dict[str, str]:
        """The field -> suggested value pairs currently ticked."""
        changes = {}
        for row in range(self.table.rowCount()):
            check = self.table.item(row, _COL_CHECK)
            if check.checkState() == Qt.Checked:
                changes[check.data(Qt.UserRole)] = self.table.item(row, _COL_SUGGESTED).toolTip()
        return changes

    def _update_apply_enabled(self) -> None:
        self.apply_button.setEnabled(bool(self.checked_changes()))

    # -- apply / undo -------------------------------------------------------------------

    def _on_apply(self) -> None:
        changes = self.checked_changes()
        row = self.candidate_list.currentRow()
        if not changes or not 0 <= row < len(self._candidates):
            return
        candidate = self._candidates[row]
        write = self.write_check.isEnabled() and self.write_check.isChecked()
        if write:
            self._remember_backup_count()
        QApplication.setOverrideCursor(Qt.WaitCursor)  # writing a large book file can take a moment
        try:
            result = self._applier.apply(
                self.doc["id"], changes, source=candidate.source, confidence=candidate.score, write_to_file=write
            )
        except MetadataApplyError as exc:
            QApplication.restoreOverrideCursor()
            QMessageBox.warning(self, "Không cập nhật được", str(exc))
            return
        except Exception:  # noqa: BLE001
            QApplication.restoreOverrideCursor()
            logger.exception("Applying metadata failed")
            QMessageBox.critical(
                self,
                "Không cập nhật được",
                "Có lỗi khi cập nhật thông tin sách. Hãy thử lại; nếu vẫn lỗi, mở Trợ giúp → Giới thiệu → "
                "Thư mục nhật ký để gửi cho tác giả.",
            )
            return
        QApplication.restoreOverrideCursor()

        lines = [f"Đã cập nhật {len(result.changed_fields)} mục thông tin trong thư viện."]
        if result.written_fields:
            lines.append(f"Đã ghi đè {len(result.written_fields)} mục thông tin lên file sách gốc (file cũ đã được sao lưu, có thể hoàn tác).")
        if result.index_only_fields:
            names = ", ".join(FIELD_LABELS[f] for f in result.index_only_fields)
            lines.append(f"Chỉ lưu trong thư viện (định dạng file không hỗ trợ): {names}.")
        if result.locked_fields:
            names = ", ".join(FIELD_LABELS[f] for f in result.locked_fields)
            lines.append(f"Giữ nguyên những mục bạn đã tự sửa: {names}.")
        if result.file_error:
            QMessageBox.warning(self, "Chưa ghi được vào file", "\n".join(lines) + "\n\nChưa ghi được vào file sách gốc: " + result.file_error)
        else:
            QMessageBox.information(self, "Đã cập nhật", "\n".join(lines))
        self.applied = True
        self.accept()

    def _remember_backup_count(self) -> None:
        """Uses the number in the box for this write and keeps it as the setting (Settings shows the same one)."""
        keep = self.backup_spin.value()
        self.context.config.config.metadata_backup_keep = keep
        writer = getattr(self._applier, "writer", None)
        if writer is not None:
            writer.keep_backups = max(1, keep)

    def _on_undo(self) -> None:
        confirm = QMessageBox.question(
            self,
            "Hoàn tác",
            "Đưa thông tin của lần cập nhật gần nhất về như cũ? Nếu lần đó đã ghi vào file gốc, file sẽ được khôi phục từ bản sao lưu.",
        )
        if confirm != QMessageBox.Yes:
            return
        try:
            result = self._applier.undo_latest(self.doc["id"])
        except MetadataApplyError as exc:
            QMessageBox.warning(self, "Không hoàn tác được", str(exc))
            return
        note = "Đã hoàn tác." + (" File gốc đã được khôi phục." if result.file_restored else "")
        QMessageBox.information(self, "Hoàn tác", note)
        self.applied = True
        self._refresh_undo_button()
        self._show_candidate(self.candidate_list.currentRow())

    def _refresh_undo_button(self) -> None:
        self.undo_button.setEnabled(self._applier.can_undo(self.doc["id"]))
