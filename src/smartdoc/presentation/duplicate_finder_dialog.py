# SPDX-License-Identifier: AGPL-3.0-or-later
"""Tìm file trùng: groups of the same book on the left, the files of the chosen group on the right, and one clear
choice -- which copy to keep.

Exact matches compare the *content* of the files (a hash), so a renamed copy is found and two different books with the
same title are not. "Gợi ý" is only a hint: books whose title/author look alike (run on a background thread; closing the
dialog cancels it), with a matching file size mentioned as a further hint -- name and size never prove that two files are
the same book.

MewBook never picks what to remove. Every group starts with *no* copy chosen: the person looks at the group and picks
the one to keep, and only then do the buttons come alive. (The copy that knows most about the book is pointed out as a
suggestion, nothing more.) The two actions are kept apart on purpose:
  * "Bỏ N bản kia khỏi thư viện" only removes the other copies from the MewBook library; the files stay on the disk.
  * "Chuyển N file vào Thùng rác" moves them into MewBook's trash (application/trash_service.py), from where they can
    be restored until the period the person set is over; a file that cannot be moved stays where it is.
The book that is kept is never touched by either.

Two views of the same result: "Theo nhóm" (above: one group at a time) and "Danh sách" (presentation/duplicate_list_pane.py: every
file of every group in one searchable, sortable table, ticked and handled in bulk -- with the one rule that every group
keeps a copy). Both go through the same two actions below.
"""
from __future__ import annotations

import threading
from datetime import datetime
from pathlib import Path

from PySide6.QtCore import QSize, Qt, QTimer
from PySide6.QtWidgets import (
    QAbstractItemView,
    QButtonGroup,
    QFrame,
    QHBoxLayout,
    QHeaderView,
    QLabel,
    QListWidget,
    QListWidgetItem,
    QMessageBox,
    QProgressBar,
    QPushButton,
    QRadioButton,
    QStackedWidget,
    QTableWidget,
    QTableWidgetItem,
    QVBoxLayout,
    QWidget,
)

from smartdoc.application.duplicate_finder import DuplicateEngine, DuplicateSearchCancelled
from smartdoc.presentation.design_dialog import DesignDialog
from smartdoc.presentation.task_progress_dialog import run_with_progress
from smartdoc.presentation.duplicate_list_pane import DuplicateListPane
from smartdoc.presentation.file_actions import FileActionEngine
from smartdoc.presentation.format_utils import human_size
from smartdoc.presentation.theme_manager import theme_manager

_DOC_ROLE = Qt.UserRole + 1
_GROUP_ROLE = Qt.UserRole + 2
_COL_KEEP, _COL_PATH, _COL_SIZE, _COL_DATE, _COL_NOTE = range(5)
MODE_EXACT, MODE_FUZZY = "exact", "fuzzy"


def _format_date(value) -> str:
    if not value:
        return "—"
    try:
        return datetime.fromtimestamp(value).strftime("%d/%m/%Y")
    except (TypeError, ValueError, OSError):
        return "—"


def _size(value) -> str:
    return human_size(value or 0).replace(".", ",")


def completeness_score(doc: dict) -> tuple:
    """How much a copy knows about the book (cover, author, publisher, year, pages); the richest copy is the one
    offered as "giữ" first, and the oldest wins a tie."""
    score = (2 if doc.get("cover_path") else 0) + (1 if (doc.get("author") or "") not in ("", "Unknown") else 0) \
        + (1 if doc.get("publisher") else 0) + (1 if doc.get("pub_year") else 0) + (1 if doc.get("page_count") else 0)
    return score, -(doc.get("created_at") or 0)


def suggested_keeper(group: list[dict]) -> dict:
    """The copy that knows most about the book -- pointed out to the person, never chosen for them."""
    return max(group, key=completeness_score)


default_keeper = suggested_keeper  # the group list still names a group after its richest copy


def note_for(doc: dict, keeper: dict | None, mode: str, suggested: dict | None = None) -> str:
    """The note under one file. `keeper` is what the person chose (None: nothing yet); `suggested` the copy that is
    most complete."""
    parts = []
    if keeper is not None and doc.get("id") == keeper.get("id"):
        parts.append("Bản bạn giữ")
    elif mode == MODE_EXACT:
        parts.append("Giống hệt từng byte")
    else:
        parts.append("Chỉ là gợi ý: tên/tác giả gần giống")
        if keeper is not None and doc.get("file_size") and doc.get("file_size") == keeper.get("file_size"):
            parts.append("cùng dung lượng")
    if suggested is not None and doc.get("id") == suggested.get("id") and (keeper is None or keeper.get("id") != doc.get("id")):
        if doc.get("cover_path") and (doc.get("author") or "") not in ("", "Unknown"):
            parts.append("gợi ý giữ: đủ thông tin, có bìa")
        elif doc.get("cover_path"):
            parts.append("gợi ý giữ: có bìa")
    if doc.get("file_status") == "missing":
        parts.append("không thấy file")
    return ", ".join(parts)


class DuplicateFinderDialog(DesignDialog):
    def __init__(self, context, parent=None) -> None:
        super().__init__(parent, title="Tìm file trùng", subtitle="So sánh theo nội dung file, không chỉ theo tên",
                         icon="filter", width=860)
        self.context = context
        self.engine = DuplicateEngine(context)
        self.file_actions = FileActionEngine(context)
        self._groups = {MODE_EXACT: [], MODE_FUZZY: []}
        self._mode = MODE_EXACT
        self._current = -1  # index of the group shown on the right
        self._keepers: dict[tuple[str, int], str] = {}  # (mode, group index) -> id of the copy kept
        # The fuzzy scan: the worker thread never touches a Qt object (a signal emitted on a dialog destroyed
        # mid-scan is a hard crash); it writes plain values into this dict and a timer owned by the dialog reads them.
        self._scan_generation = 0
        self._cancel_scan = threading.Event()
        self._cancel_hash = threading.Event()
        self._hash_state: dict = {}
        self._hash_poll: QTimer | None = None
        self._scan_state: dict = {}
        self._scan_poll = QTimer(self)
        self._scan_poll.setInterval(50)
        self._scan_poll.timeout.connect(self._poll_fuzzy_scan)
        self.resize(900, 560)
        self.setMaximumSize(1200, 860)

        # -- left: the groups --
        self.exact_button = QPushButton("Giống hệt", self)
        self.fuzzy_button = QPushButton("Gợi ý", self)
        for button in (self.exact_button, self.fuzzy_button):
            button.setCheckable(True)
        self.exact_button.setChecked(True)
        self.exact_button.clicked.connect(lambda: self._set_mode(MODE_EXACT))
        self.fuzzy_button.clicked.connect(lambda: self._set_mode(MODE_FUZZY))
        modes = QHBoxLayout()
        modes.setSpacing(0)
        modes.addWidget(self.exact_button)
        modes.addWidget(self.fuzzy_button)
        # The two ways of looking at the chosen list: one group at a time, or all files in a searchable table.
        self.groups_view_button = QPushButton("Theo nhóm", self)
        self.list_view_button = QPushButton("Danh sách", self)
        for button in (self.groups_view_button, self.list_view_button):
            button.setCheckable(True)
        self.groups_view_button.setChecked(True)
        self.groups_view_button.clicked.connect(lambda: self._show_view(False))
        self.list_view_button.clicked.connect(lambda: self._show_view(True))
        views = QHBoxLayout()
        views.setSpacing(0)
        views.addWidget(self.groups_view_button)
        views.addWidget(self.list_view_button)
        top_row = QHBoxLayout()
        top_row.addLayout(modes)
        top_row.addStretch(1)
        top_row.addLayout(views)
        self.summary_label = QLabel(self)
        self.summary_label.setStyleSheet(f"color: {theme_manager().token('ink3')}; font-size: 12px;")
        self.group_list = QListWidget(self)
        self.group_list.setFrameShape(QFrame.NoFrame)
        self.group_list.setSpacing(2)
        self.group_list.currentRowChanged.connect(self._on_group_chosen)
        self.scan_status_label = QLabel(self)
        self.scan_status_label.setWordWrap(True)
        self.scan_progress = QProgressBar(self)
        self.scan_progress.setTextVisible(False)
        left = QVBoxLayout()
        left.setSpacing(8)
        left.addWidget(self.summary_label)
        left.addWidget(self.group_list, 1)
        left.addWidget(self.scan_status_label)
        left.addWidget(self.scan_progress)
        left_box = QWidget(self)
        left_box.setLayout(left)
        left_box.setFixedWidth(270)

        # -- right: the files of the chosen group --
        self.group_title = QLabel(self)
        self.group_title.setStyleSheet("font-weight: 600; font-size: 14px;")
        self.file_table = QTableWidget(0, 5, self)
        self.file_table.setHorizontalHeaderLabels(["GIỮ", "VỊ TRÍ FILE", "DUNG LƯỢNG", "NGÀY", "GHI CHÚ"])
        self.file_table.verticalHeader().setVisible(False)
        self.file_table.setEditTriggers(QAbstractItemView.NoEditTriggers)
        self.file_table.setSelectionMode(QAbstractItemView.NoSelection)
        self.file_table.setShowGrid(False)
        header = self.file_table.horizontalHeader()
        header.setSectionResizeMode(_COL_KEEP, QHeaderView.Fixed)
        self.file_table.setColumnWidth(_COL_KEEP, 48)
        header.setSectionResizeMode(_COL_PATH, QHeaderView.Stretch)
        header.setSectionResizeMode(_COL_SIZE, QHeaderView.ResizeToContents)
        header.setSectionResizeMode(_COL_DATE, QHeaderView.ResizeToContents)
        header.setSectionResizeMode(_COL_NOTE, QHeaderView.Interactive)
        self.file_table.setColumnWidth(_COL_NOTE, 170)
        self.file_table.verticalHeader().setDefaultSectionSize(44)
        self._radio_group: QButtonGroup | None = None

        self.remove_button = QPushButton(self)
        self.remove_button.clicked.connect(self._on_remove_from_library)
        self.delete_button = QPushButton(self)
        self.delete_button.setProperty("role", "danger")
        self.delete_button.clicked.connect(self._on_trash_files)
        buttons = QHBoxLayout()
        buttons.setSpacing(8)
        buttons.addWidget(self.remove_button)
        buttons.addWidget(self.delete_button)
        buttons.addStretch(1)
        self.hint_label = QLabel(
            "MewBook không tự chọn bản nào để xóa: hãy xem từng nhóm và chọn bản giữ lại. “Bỏ khỏi thư viện”: file vẫn nằm "
            "trên máy. “Chuyển vào Thùng rác”: file vào thùng rác của MewBook, khôi phục được trước hạn.", self)
        self.hint_label.setStyleSheet(f"color: {theme_manager().token('ink3')}; font-size: 12px;")
        self.hint_label.setWordWrap(True)

        self.trash_note = QLabel(self)
        self.trash_note.setWordWrap(True)
        self.trash_note.setStyleSheet(f"color: {theme_manager().token('ink3')}; font-size: 12px;")
        self.trash_button = QPushButton("Mở Thùng rác…", self)
        self.trash_button.clicked.connect(self._on_open_trash)
        trash_row = QHBoxLayout()
        trash_row.addWidget(self.trash_note, 1)
        trash_row.addWidget(self.trash_button)

        right = QVBoxLayout()
        right.setSpacing(10)
        right.addWidget(self.group_title)
        right.addWidget(self.file_table, 1)
        right.addLayout(buttons)
        right.addWidget(self.hint_label)
        right.addLayout(trash_row)
        right_box = QWidget(self)
        right_box.setLayout(right)

        columns = QHBoxLayout()
        columns.setSpacing(16)
        columns.addWidget(left_box)
        columns.addWidget(right_box, 1)
        groups_page = QWidget(self)
        groups_page.setLayout(columns)
        self.list_pane = DuplicateListPane(suggested_keeper, self)
        self.list_pane.remove_requested.connect(self._on_remove_docs)
        self.list_pane.trash_requested.connect(self._on_trash_docs)
        self.view_stack = QStackedWidget(self)
        self.view_stack.addWidget(groups_page)
        self.view_stack.addWidget(self.list_pane)
        self.body.addLayout(top_row)
        self.body.addWidget(self.view_stack, 1)

        self.position_label = self.add_footer_note("")
        self.previous_button = self.add_footer_button("Nhóm trước", on_click=lambda: self._step(-1))
        self.next_button = self.add_footer_button("Nhóm sau", on_click=lambda: self._step(1))
        self.done_button = self.add_footer_button("Xong", "primary", on_click=self.accept)

        self.refresh()

    # -- keeping the old public names used around the app and in tests ------------------------------------------------
    @property
    def _exact_groups(self) -> list[list[dict]]:
        return self._groups[MODE_EXACT]

    @property
    def _fuzzy_groups(self) -> list[list[dict]]:
        return self._groups[MODE_FUZZY]

    # -- loading ------------------------------------------------------------------------------------------------------
    def refresh(self) -> None:
        self._groups[MODE_EXACT] = self.engine.find_exact_duplicates()
        self._keepers = {key: v for key, v in self._keepers.items() if key[0] != MODE_EXACT}
        self._fill_groups()
        self._start_hashing()
        self._start_fuzzy_scan()

    # -- hashing the files that could still be duplicates, on a worker thread -------------------------------------------
    def _start_hashing(self) -> None:
        """Import does not read a file through to hash it unless another book has the same size; the books that share a
        size and have no hash yet are completed here, in the background, and the exact list is refreshed when done."""
        self._hash_state = {}
        pending = self.engine.pending_hash_count()
        if not pending:
            return
        self.scan_status_label.setText(f"Đang đọc {pending} file để so nội dung…")
        self.scan_status_label.show()
        self._cancel_hash.clear()
        state, engine, cancel = self._hash_state, self.engine, self._cancel_hash  # (not the fuzzy scan's: it is replaced)

        def worker() -> None:
            try:
                state["hashed"] = engine.hash_pending(progress=lambda d, t: state.__setitem__("progress", (d, t)), should_cancel=cancel.is_set)
            except Exception as exc:  # noqa: BLE001 -- a failed read must not take the dialog down
                state["hashed"] = 0
                state["error"] = str(exc)

        threading.Thread(target=worker, daemon=True).start()
        self._hash_poll = QTimer(self)
        self._hash_poll.setInterval(100)
        self._hash_poll.timeout.connect(self._poll_hashing)
        self._hash_poll.start()

    def _poll_hashing(self) -> None:
        state = self._hash_state
        if "hashed" not in state:
            if "progress" in state:
                done, total = state["progress"]
                self.scan_status_label.setText(f"Đang đọc file để so nội dung: {done}/{total}")
            return
        self._hash_poll.stop()
        if state["hashed"]:
            self._groups[MODE_EXACT] = self.engine.find_exact_duplicates()
            self._keepers = {key: v for key, v in self._keepers.items() if key[0] != MODE_EXACT}
            if self._mode == MODE_EXACT:
                self._fill_groups()
        self.scan_status_label.setVisible(self.scan_progress.isVisible())

    def _set_mode(self, mode: str) -> None:
        self._mode = mode
        self.exact_button.setChecked(mode == MODE_EXACT)
        self.fuzzy_button.setChecked(mode == MODE_FUZZY)
        self._fill_groups()

    def _show_view(self, as_list: bool) -> None:
        self.groups_view_button.setChecked(not as_list)
        self.list_view_button.setChecked(as_list)
        self.view_stack.setCurrentIndex(1 if as_list else 0)
        # The group-by-group buttons of the footer make no sense next to a table of everything.
        for widget in (self.previous_button, self.next_button, self.position_label):
            widget.setVisible(not as_list)
        self.list_pane.set_groups(self._groups[self._mode])

    def _fill_groups(self) -> None:
        groups = self._groups[self._mode]
        self.group_list.blockSignals(True)
        self.group_list.clear()
        for index, group in enumerate(groups):
            title = default_keeper(group).get("title") or "(không có tên)"
            total = sum(d.get("file_size") or 0 for d in group)
            chosen = (self._mode, index) in self._keepers
            sub = f"{len(group)} file · {_size(total)}" + (" · đã chọn cái giữ" if chosen else "")
            item = QListWidgetItem(f"{title}\n{sub}")
            item.setData(_GROUP_ROLE, index)
            item.setSizeHint(QSize(0, 48))
            self.group_list.addItem(item)
        self.group_list.blockSignals(False)
        if self.view_stack.currentIndex() == 1:
            self.list_pane.set_groups(groups)
        files = sum(len(g) for g in groups)
        total_size = sum(d.get("file_size") or 0 for g in groups for d in g)
        self.summary_label.setText(f"{len(groups)} nhóm · {files} file · {_size(total_size)}" if groups else "Không có nhóm nào")
        if groups:
            self.group_list.setCurrentRow(0)
            self._on_group_chosen(0)
        else:
            self._current = -1
            self._show_group(None)

    def _on_group_chosen(self, row: int) -> None:
        self._current = row
        groups = self._groups[self._mode]
        self._show_group(groups[row] if 0 <= row < len(groups) else None)

    def _keeper_of(self, group: list[dict]) -> dict | None:
        """The copy the person chose to keep in this group, or None while they have not chosen."""
        wanted = self._keepers.get((self._mode, self._current))
        return next((d for d in group if d.get("id") == wanted), None)

    @staticmethod
    def _group_heading(group: list[dict], keeper: dict | None) -> str:
        title = (keeper or suggested_keeper(group)).get("title") or "(không có tên)"
        return f"{title} — " + ("bản giữ lại đã chọn" if keeper else "chưa chọn bản giữ: hãy chọn một bản")

    def _show_group(self, group: list[dict] | None) -> None:
        self.file_table.setRowCount(0)
        self._radio_group = None
        total_groups = len(self._groups[self._mode])
        self.position_label.setText(f"Nhóm {self._current + 1} / {total_groups}" if group else "")
        self.previous_button.setEnabled(self._current > 0)
        self.next_button.setEnabled(0 <= self._current < total_groups - 1)
        if not group:
            self.group_title.setText("")
            self._update_action_buttons(None)
            return
        keeper = self._keeper_of(group)
        suggested = suggested_keeper(group)
        self.group_title.setText(self._group_heading(group, keeper))
        self.file_table.setRowCount(len(group))
        self._radio_group = QButtonGroup(self.file_table)
        tm = theme_manager()
        for row, doc in enumerate(group):
            radio = QRadioButton(self.file_table)
            radio.setChecked(keeper is not None and doc.get("id") == keeper.get("id"))
            radio.setProperty("doc_id", doc.get("id"))
            radio.toggled.connect(lambda checked, d=doc: checked and self._on_keeper_chosen(d))
            self._radio_group.addButton(radio)
            holder = QWidget(self.file_table)
            QHBoxLayout(holder).addWidget(radio, 0, Qt.AlignCenter)
            holder.layout().setContentsMargins(0, 0, 0, 0)
            self.file_table.setCellWidget(row, _COL_KEEP, holder)
            path_text = doc.get("file_path", "")
            kept = keeper is not None and doc.get("id") == keeper.get("id")
            path_item = QTableWidgetItem(path_text + ("  · giữ" if kept else ""))
            path_item.setToolTip(path_text)
            path_item.setData(_DOC_ROLE, doc)
            self.file_table.setItem(row, _COL_PATH, path_item)
            self.file_table.setItem(row, _COL_SIZE, QTableWidgetItem(_size(doc.get("file_size"))))
            self.file_table.setItem(row, _COL_DATE, QTableWidgetItem(_format_date(doc.get("created_at"))))
            note = QTableWidgetItem(note_for(doc, keeper, self._mode, suggested))
            note.setForeground(tm.color("ink3"))
            self.file_table.setItem(row, _COL_NOTE, note)
        self._update_action_buttons(group)

    def _on_keeper_chosen(self, doc: dict) -> None:
        """The radio changed: update the texts in place (the radio buttons are never rebuilt from inside their own
        signal)."""
        groups = self._groups[self._mode]
        if not 0 <= self._current < len(groups):
            return
        group = groups[self._current]
        self._keepers[(self._mode, self._current)] = doc.get("id")
        keeper = self._keeper_of(group)
        item = self.group_list.item(self._current)
        if item is not None:
            title = item.text().split("\n")[0]
            total = _size(sum(d.get("file_size") or 0 for d in group))
            item.setText(f"{title}\n{len(group)} file · {total} · đã chọn cái giữ")
        self.group_title.setText(self._group_heading(group, keeper))
        suggested = suggested_keeper(group)
        for row in range(self.file_table.rowCount()):
            path_item = self.file_table.item(row, _COL_PATH)
            row_doc = path_item.data(_DOC_ROLE)
            kept = keeper is not None and row_doc.get("id") == keeper.get("id")
            path_item.setText(row_doc.get("file_path", "") + ("  · giữ" if kept else ""))
            self.file_table.item(row, _COL_NOTE).setText(note_for(row_doc, keeper, self._mode, suggested))
        self._update_action_buttons(group)

    def _others(self) -> list[dict]:
        groups = self._groups[self._mode]
        if not 0 <= self._current < len(groups):
            return []
        group = groups[self._current]
        keeper = self._keeper_of(group)
        if keeper is None:  # nothing is offered for removal until the person has chosen what to keep
            return []
        return [d for d in group if d.get("id") != keeper.get("id")]

    def _update_action_buttons(self, group: list[dict] | None) -> None:
        count = len(self._others()) if group else 0
        self.remove_button.setText(f"Bỏ {count} bản kia khỏi thư viện")
        self.delete_button.setText(f"Chuyển {count} file vào Thùng rác…")
        days = self.context.trash.retention_days()
        self.trash_note.setText(f"Tự xóa hẳn sau {days} ngày; bạn đổi được ở cửa sổ Thùng rác." if days
                                else "Giữ trong thùng rác đến khi bạn tự xóa.")
        self.remove_button.setEnabled(count > 0)
        self.delete_button.setEnabled(count > 0)

    def _step(self, delta: int) -> None:
        target = self._current + delta
        if 0 <= target < self.group_list.count():
            self.group_list.setCurrentRow(target)

    # -- the two actions --------------------------------------------------------------------------------------------------
    def _on_remove_from_library(self) -> None:
        """Only the library entries of the other copies go; every file stays where it is."""
        self._on_remove_docs(self._others())

    def _on_remove_docs(self, others: list[dict]) -> None:
        if not others:
            return
        self.file_actions.delete_documents([(d["id"], d.get("file_path")) for d in others], delete_physical_file=False)
        self._forget({d["id"] for d in others})

    def _on_trash_files(self) -> None:
        self._on_trash_docs(self._others())

    def _on_trash_docs(self, others: list[dict]) -> None:
        """Move these files into MewBook's trash (they can come back), after one plain confirmation. Used by the group
        view (the other copies of the group) and by the list view (whatever was ticked)."""
        if not others:
            return
        count = len(others)
        days = self.context.trash.retention_days()
        answer = QMessageBox.question(
            self, f"Chuyển {count} file vào Thùng rác?",
            f"{count} file sẽ rời khỏi thư mục hiện tại và nằm trong Thùng rác của MewBook"
            + (f", tự xóa hẳn sau {days} ngày" if days else "") + ". Bạn khôi phục được bất cứ lúc nào trước hạn.\n\n"
            "Bản bạn giữ lại không bị đụng tới.", QMessageBox.Yes | QMessageBox.No, QMessageBox.No)
        if answer != QMessageBox.Yes:
            return
        items = [(d["id"], d.get("file_path")) for d in others]

        def move(progress):
            return self.context.trash.send(items, lambda done, total: progress(done, total, f"Đã chuyển {done}/{total} file"))

        result, error = run_with_progress(  # off the GUI thread: moving across drives copies the bytes
            self, title="Thùng rác", message=f"Mèo đang chuyển {count} file vào Thùng rác…", work=move, delay_ms=400,
            hint="Chép sang ổ khác có thể lâu với file lớn; bạn có thể chờ, cửa sổ vẫn đang làm việc.")
        if result is None:
            QMessageBox.warning(self, "Chưa chuyển được", f"Có lỗi khi chuyển file: {error}\nCác file đã chuyển xong vẫn nằm trong Thùng rác.")
            self.refresh()
            return
        if result.failed:
            QMessageBox.warning(
                self, "Có file chưa chuyển được",
                "Những file này vẫn nằm nguyên chỗ cũ và vẫn trong thư viện:\n\n"
                + "\n".join(f"• {next((d.get('file_path') for d in others if d['id'] == doc_id), doc_id)}: {reason}"
                            for doc_id, reason in result.failed))
        self._forget(set(result.moved) | set(result.missing))

    def _on_open_trash(self) -> None:
        from smartdoc.presentation.trash_dialog import TrashDialog

        dialog = TrashDialog(self.context, self)
        dialog.exec()
        dialog.deleteLater()
        self.refresh()  # a restored book may be a duplicate again

    def _forget(self, deleted_ids: set[str]) -> None:
        """Removing copies can only shrink groups, never create new ones: drop them from what was found."""
        for mode in (MODE_EXACT, MODE_FUZZY):
            self._groups[mode] = self._without(self._groups[mode], deleted_ids)
        self._keepers = {}
        keep_row = max(0, self._current)
        self._fill_groups()  # (also rebuilds the list view when it is the one showing)
        if self.group_list.count():
            self.group_list.setCurrentRow(min(keep_row, self.group_list.count() - 1))

    @staticmethod
    def _without(groups: list[list[dict]], deleted_ids: set[str]) -> list[list[dict]]:
        remaining = [[doc for doc in group if doc["id"] not in deleted_ids] for group in groups]
        return [group for group in remaining if len(group) > 1]

    # -- fuzzy scan on a background thread ---------------------------------------------------------------------------------
    def _start_fuzzy_scan(self) -> None:
        self._cancel_scan.set()  # stop any scan still running from before
        self._cancel_scan = threading.Event()
        self._scan_generation += 1
        generation, cancel = self._scan_generation, self._cancel_scan
        self._groups[MODE_FUZZY] = []
        self.fuzzy_button.setText("Gợi ý …")
        self.scan_status_label.setText("Đang tìm sách có tên/tác giả gần giống nhau…")
        self.scan_progress.setRange(0, 0)  # indeterminate until the first progress report
        self.scan_progress.show()
        self.scan_status_label.show()

        # Read here, on the GUI thread (one quick query); the worker only does the comparison, so it never holds the
        # shared database connection when the app closes it on exit.
        docs = self.context.db.list_documents_for_dedup()
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
            except Exception as exc:  # noqa: BLE001 -- a scan failure must not take the dialog down with it
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
        self.scan_status_label.setText(f"Đang so sánh: {done}/{total} sách")

    def _on_fuzzy_finished(self, generation: int, groups: list, error: str) -> None:
        if generation != self._scan_generation:
            return
        self.scan_progress.hide()
        if error:
            self.fuzzy_button.setText("Gợi ý")
            self.scan_status_label.setText(f"Không quét được sách gần giống: {error}")
            return
        self._groups[MODE_FUZZY] = groups
        self.fuzzy_button.setText(f"Gợi ý ({len(groups)})")
        self.scan_status_label.hide()
        if self._mode == MODE_FUZZY:
            self._fill_groups()

    def wait_for_scan(self, timeout: float = 10.0) -> bool:
        """For tests: pump events until the current fuzzy scan reports back."""
        import time

        from PySide6.QtWidgets import QApplication

        deadline = time.time() + timeout
        while time.time() < deadline:
            QApplication.processEvents()
            if not self._scan_poll.isActive():
                return True
            time.sleep(0.01)
        return False

    def done(self, result: int) -> None:  # noqa: D401 -- Qt override
        # Closing (any way: Xong, Esc, ×) stops a scan in progress rather than leaving it churning in the background.
        self._cancel_scan.set()
        self._cancel_hash.set()
        self._scan_poll.stop()
        if self._hash_poll is not None:
            self._hash_poll.stop()
        super().done(result)


if __name__ == "__main__":
    import sys
    import tempfile

    from PySide6.QtWidgets import QApplication

    from smartdoc.core.app_context import AppContext

    with tempfile.TemporaryDirectory() as tmp:
        context = AppContext.create_in_memory(Path(tmp))
        context.db.add_or_update_document(
            "d1", {"title": "Sach A", "author": "X", "file_path": "a.pdf", "content_hash": "h1", "created_at": 1.0})
        context.db.add_or_update_document(
            "d2", {"title": "Sach A (copy)", "author": "X", "file_path": "a2.pdf", "content_hash": "h1", "created_at": 2.0})

        app = QApplication(sys.argv)
        theme_manager().apply(app, "broadsheet")
        DuplicateFinderDialog(context).exec()
