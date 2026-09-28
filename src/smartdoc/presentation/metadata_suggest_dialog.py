"""Tìm thêm thông tin (was "Tìm thông tin sách" + "Tìm ảnh bìa", and used to open a second window -- CoverSearchDialog
-- for the paste-link/browse-file cases): look a book up -- its information AND its cover -- review the differences,
and apply what you accept, the picture and the information independently or both. Three visible steps (Tìm, Chọn
kết quả, Xem khác biệt). The cover section reuses `cover_search_dialog.CoverSearchWidget` (its three tabs -- catalogue
search, pasted link, file from disk -- and its before -> after preview) embedded with `show_query_row=False`, so this
is now the one window: the shared box above drives both the information lookup and the cover search.

One search box takes the title and the author together ("Nhà giả kim - Paulo Coelho", or just the words in any order);
application/cover_search.split_query works out the readings and the search tries them, so this finds what two boxes did.
Three buttons beside it: "Tìm kiếm" (search), "Tìm thêm" (search again with the internet included -- only enabled once
the first search has not already reached it), and "Mở trình duyệt", which only opens the default browser on a web
search of that text -- the person carries on there; MewBook does not read the page that comes back.

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
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

from PySide6.QtCore import Qt, QUrl, Signal
from PySide6.QtGui import QDesktopServices
from PySide6.QtWidgets import (
    QAbstractItemView,
    QApplication,
    QCheckBox,
    QFrame,
    QHBoxLayout,
    QHeaderView,
    QLabel,
    QLineEdit,
    QListWidget,
    QListWidgetItem,
    QMessageBox,
    QPushButton,
    QTableWidget,
    QTableWidgetItem,
    QVBoxLayout,
)

from smartdoc.application.cover_search import (
    CoverSearchError,
    download_cover_image,
    search_covers_for_text,
    split_query,
)
from smartdoc.application.metadata_applier import MetadataApplier, MetadataApplyError
from smartdoc.application.metadata_lookup import LookupResult, MetadataLookupService
from smartdoc.application.metadata_writer import MetadataWriter
from smartdoc.core.event_bus import LibraryUpdatedEvent
from smartdoc.infrastructure.cover_manager import CoverCacheManager
from smartdoc.presentation.cover_search_dialog import CoverSearchWidget
from smartdoc.presentation.design_dialog import DesignDialog
from smartdoc.presentation.theme_manager import theme_manager
from smartdoc.presentation.worker_relay import WorkerRelay, post

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

_COL_CHECK, _COL_FIELD, _COL_CURRENT, _COL_SUGGESTED, _COL_SOURCE = range(5)
_STEPS = ((1, "Tìm"), (2, "Chọn kết quả"), (3, "Xem khác biệt"))


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


class MetadataSuggestDialog(DesignDialog):
    lookup_finished = Signal(int, object, str)  # (search number, LookupResult | None, error message)
    covers_finished = Signal(int, list, str)  # (search number, [(CoverSearchResult, image bytes)], error message) -- fed to cover_panel

    def __init__(self, context, doc: dict, parent=None, service=None, applier=None) -> None:
        super().__init__(parent, title="Tìm thêm thông tin", subtitle=doc.get("title", "") or "", icon="search",
                         width=960)
        self.context = context
        self.doc = doc
        self.applied = False  # something was applied or undone: callers refresh
        self._service = service or MetadataLookupService(context)
        self._applier = applier or MetadataApplier(context)
        self._candidates: list = []
        self._cover_pending = False  # the cover search of the current search number is still running
        self._info_pending = False
        self._cover_manager = CoverCacheManager(context)
        self._search_number = 0
        self._relay = WorkerRelay(self)  # what the lookup thread talks to (never the dialog itself)

        self.resize(980, 920)
        self.step_label = QLabel(self)
        self.step_label.setTextFormat(Qt.RichText)
        self.body.addWidget(self.step_label)

        # -- Frame 1: nhập thông tin tìm kiếm -----------------------------------------------
        # ONE box for title and author; a book whose author is known starts as "title - author".
        author = (doc.get("author", "") or "").strip()
        known_author = author and author.lower() != "unknown"
        start = (doc.get("title", "") or "").strip()
        self.title_edit = QLineEdit(f"{start} - {author}" if start and known_author else start, self)
        self.title_edit.setPlaceholderText("Tên sách và tác giả, ví dụ: Nhà giả kim - Paulo Coelho")
        self.title_edit.setClearButtonEnabled(True)
        self.title_edit.returnPressed.connect(lambda: self._start_search(include_internet=False))
        self.search_button = QPushButton("Tìm kiếm", self)
        self.search_button.clicked.connect(lambda: self._start_search(include_internet=False))
        self.internet_button = QPushButton("Tìm thêm", self)
        self.internet_button.setToolTip("Tìm lại có tính cả internet (bật khi kết quả đầu chỉ mới tìm trong thư viện).")
        self.internet_button.clicked.connect(lambda: self._start_search(include_internet=True))
        self.internet_button.setEnabled(False)
        self.web_button = QPushButton("Mở trình duyệt", self)
        self.web_button.setToolTip("Mở trình duyệt của bạn với trang tìm kiếm cho từ khóa này. MewBook không đọc kết quả.")
        self.web_button.clicked.connect(self._on_search_web)
        search_row = QHBoxLayout()
        search_row.addWidget(self.title_edit, 2)  # ~2/3 of the row; the buttons and the stretch after take the rest
        search_row.addWidget(self.search_button)
        search_row.addWidget(self.internet_button)
        search_row.addWidget(self.web_button)
        search_row.addStretch(1)

        self.status_label = QLabel("", self)
        self.status_label.setWordWrap(True)
        status_box = QFrame(self)
        status_box.setObjectName("StatusBox")
        status_box.setStyleSheet(f"#StatusBox {{ background: {theme_manager().token('surface')};"
                                 f" border: 1px solid {theme_manager().token('line2')}; border-radius: 6px; }}")
        status_box_layout = QVBoxLayout(status_box)
        status_box_layout.setContentsMargins(10, 8, 10, 8)
        status_box_layout.addWidget(self.status_label)

        # -- Frame 2: thông tin tìm được (trái: kết quả, phải: chi tiết + chọn cập nhật) ----
        self.candidate_list = QListWidget(self)
        row_height = self.candidate_list.fontMetrics().height() + 8
        self.candidate_list.setFixedHeight(row_height * 5 + 6)  # 5 rows visible; more scrolls
        self.candidate_list.currentRowChanged.connect(self._show_candidate)

        self.select_all_check = QCheckBox("Chọn tất cả", self)
        self.select_all_check.setToolTip("Đánh dấu (hoặc bỏ đánh dấu) mọi mục ở bảng bên dưới cùng lúc.")
        self.select_all_check.toggled.connect(self._on_select_all_toggled)

        self.table = QTableWidget(0, 5, self)
        self.table.setHorizontalHeaderLabels(["", "MỤC", "HIỆN TẠI", "ĐỀ XUẤT", "NGUỒN"])
        self.table.verticalHeader().setVisible(False)
        self.table.setEditTriggers(QAbstractItemView.NoEditTriggers)
        self.table.setSelectionMode(QAbstractItemView.NoSelection)
        self.table.setWordWrap(True)
        header = self.table.horizontalHeader()
        header.setSectionResizeMode(_COL_CHECK, QHeaderView.ResizeToContents)
        header.setSectionResizeMode(_COL_FIELD, QHeaderView.ResizeToContents)
        header.setSectionResizeMode(_COL_CURRENT, QHeaderView.Stretch)
        header.setSectionResizeMode(_COL_SUGGESTED, QHeaderView.Stretch)
        header.setSectionResizeMode(_COL_SOURCE, QHeaderView.ResizeToContents)
        self.table.setMinimumHeight(150)
        self.table.setMaximumHeight(280)  # about 8 rows (every field at once) -- more scrolls, instead of stretching empty
        self.table.itemChanged.connect(lambda _item: self._update_apply_enabled())

        info_split = QHBoxLayout()
        left_col = QVBoxLayout()
        left_col.addWidget(self.candidate_list)
        left_col.addStretch(1)
        right_col = QVBoxLayout()
        right_col.addWidget(self.select_all_check, 0, Qt.AlignRight)
        right_col.addWidget(self.table, 1)
        info_split.addLayout(left_col, 2)  # 40%
        info_split.addLayout(right_col, 3)  # 60%

        # -- Frame 3: ảnh bìa ----------------------------------------------------------------
        # Covers found for the same search: pick one to use as the book's picture (independent of the information).
        # Same widget as the standalone "Đổi ảnh bìa" dialog, without its own query box -- the shared box above
        # drives it too, so this is one window with a tab for each way to get a cover, not two windows.
        self.cover_panel = CoverSearchWidget(context, doc, self, show_query_row=False)
        self.cover_panel.setMinimumHeight(320)
        self.cover_list = self.cover_panel.results_list  # kept as an alias: callers/tests reach the results list here
        self.cover_panel.selectionChanged.connect(self._update_apply_enabled)

        # -- Frame 4: tùy chọn cập nhật --------------------------------------------------------
        self.write_check = QCheckBox("Ghi đè lên file sách gốc", self)
        self.write_hint = QLabel("", self)
        self.write_hint.setWordWrap(True)
        self.write_hint.setStyleSheet(f"color: {theme_manager().token('ink2')}; font-size: 13px;")
        self.locked_note = QLabel("", self)
        self.locked_note.setWordWrap(True)
        self.locked_note.setStyleSheet(f"color: {theme_manager().token('ink2')}; font-size: 13px;")
        self.locked_note.hide()
        self._setup_write_option()

        self.apply_info_check = QCheckBox("Áp dụng thông tin sách", self)
        self.apply_info_check.setChecked(True)
        self.apply_cover_check = QCheckBox("Áp dụng ảnh bìa đã chọn", self)
        self.apply_cover_check.setChecked(True)
        for check in (self.apply_info_check, self.apply_cover_check):
            check.toggled.connect(lambda _checked: self._update_apply_enabled())
        apply_row = QHBoxLayout()
        apply_row.addWidget(self.write_check)
        apply_row.addWidget(self.apply_info_check)
        apply_row.addWidget(self.apply_cover_check)
        apply_row.addStretch(1)

        self.body.addLayout(search_row)
        self.body.addWidget(status_box)
        self.body.addWidget(QLabel("THÔNG TIN TÌM ĐƯỢC", self))
        self.body.addLayout(info_split)
        self.body.addWidget(QLabel("ẢNH BÌA", self))
        self.body.addWidget(self.cover_panel)
        self.body.addWidget(self.locked_note)
        self.body.addWidget(QLabel("TÙY CHỌN CẬP NHẬT", self))
        self.body.addLayout(apply_row)
        self.body.addWidget(self.write_hint)

        self.undo_button = self.add_footer_link("Hoàn tác lần gần nhất", "refresh", self._on_undo)
        self.selected_label = self.add_footer_note("0 mục được chọn")
        self.add_footer_button("Hủy", on_click=self.reject)
        self.apply_button = self.add_footer_button("Áp dụng", "primary", on_click=self._on_apply)
        self.apply_button.setEnabled(False)

        self.lookup_finished.connect(self._on_lookup_finished)
        self.covers_finished.connect(self._on_covers_finished)
        self._refresh_undo_button()
        self._set_step(1)
        if self.title_edit.text().strip():
            self._start_search(include_internet=False)

    def _set_step(self, step: int) -> None:
        tm = theme_manager()
        parts = []
        for number, name in _STEPS:
            if number == step:
                parts.append(f"<b style='color:{tm.token('ink')}'>{number}. {name}</b>")
            else:
                parts.append(f"<span style='color:{tm.token('ink3')}'>{number}. {name}</span>")
        self.step_label.setText("  ›  ".join(parts))

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
            return
        self.write_check.setChecked(bool(self.context.config.config.metadata_write_to_file_default))
        if len(writable) == len(_FIELD_ORDER):
            detail = "Ghi được tất cả thông tin."
        else:
            names = ", ".join(FIELD_LABELS[f] for f in writable)
            detail = f"Định dạng .{extension} chỉ ghi được: {names}. Phần còn lại chỉ lưu trong thư viện."
        if self.context.config.config.backup_before_change:
            undo = "Nếu ghi nhầm, bấm \"Hoàn tác\" để trả file về như cũ."
        else:
            undo = "Chưa bật \"Sao lưu trước khi thay đổi\" (Cài đặt › Sao lưu) nên file cũ sẽ không được giữ lại."
        self.write_hint.setText(f"{_WRITE_WARNING} {detail} {undo}")

    # -- search -----------------------------------------------------------------------

    def _min_score(self) -> float:
        return max(0.0, min(1.0, int(self.context.config.config.cover_match_percent) / 100))

    def _on_search_web(self) -> None:
        text = self.title_edit.text().strip()
        if not text:
            QMessageBox.warning(self, "Thiếu từ khóa", "Vui lòng nhập tên sách (và tác giả) để tìm.")
            return
        QDesktopServices.openUrl(QUrl(web_search_url(text)))

    def _start_search(self, *, include_internet: bool) -> None:
        text = self.title_edit.text().strip()
        if not text:
            QMessageBox.warning(self, "Thiếu tiêu đề", "Vui lòng nhập tiêu đề để tìm thông tin sách.")
            return
        self._search_number += 1
        number = self._search_number
        self._set_step(1)
        self.status_label.setText("Đang tìm kiếm..." if not include_internet else "Đang tìm trên internet...")
        self.search_button.setEnabled(False)
        self.internet_button.setEnabled(False)
        self.candidate_list.clear()
        self.table.setRowCount(0)
        self.cover_panel.clear_search_results()
        self.cover_panel.status_label.setText("Đang tìm ảnh bìa...")
        self._info_pending = self._cover_pending = True
        self._update_apply_enabled()

        service, doc, relay = self._service, self.doc, self._relay
        readings, min_score = split_query(text), self._min_score()
        config = self.context.config.config

        def lookup_worker() -> None:
            try:
                result, error = self._lookup(service, doc, readings, include_internet, min_score), ""
            except Exception as exc:  # noqa: BLE001 -- the dialog must show a message, never crash on a lookup bug
                logger.exception("Metadata lookup failed")
                result, error = None, str(exc)
            post(relay, "lookup_finished", number, result, error)

        def cover_worker() -> None:
            try:
                found = search_covers_for_text(
                    text, google_api_key=config.google_image_api_key, google_cx=config.google_image_search_cx,
                    min_score=min_score, disabled_sources=config.disabled_cover_sources)
            except CoverSearchError as exc:
                post(relay, "covers_finished", number, [], str(exc))
                return
            except Exception as exc:  # noqa: BLE001 -- the cover part failing must not spoil the information part
                logger.exception("Cover search failed")
                post(relay, "covers_finished", number, [], str(exc))
                return

            def fetch(candidate):
                try:
                    return candidate, download_cover_image(candidate, validate=True)
                except CoverSearchError:
                    return None  # one bad picture must not sink the rest

            with ThreadPoolExecutor(max_workers=4) as pool:
                downloaded = [pair for pair in pool.map(fetch, found) if pair is not None]
            post(relay, "covers_finished", number, downloaded, "")

        threading.Thread(target=lookup_worker, daemon=True).start()
        threading.Thread(target=cover_worker, daemon=True).start()

    @staticmethod
    def _lookup(service, doc: dict, readings: list[tuple[str, str]], include_internet: bool, min_score: float) -> LookupResult:
        """The information lookup for one line of text: the first reading of it (whole text as the title) that finds
        something wins; the next readings are only tried when it found nothing from outside the book's own file."""
        merged = LookupResult()
        for title, author in readings or [("", "")]:
            result = service.lookup(doc, title=title, author=author, include_internet=include_internet, min_score=min_score)
            merged.searched_internet = merged.searched_internet or result.searched_internet
            merged.errors.extend(e for e in result.errors if e not in merged.errors)
            merged.candidates.extend(result.candidates)
            if any(c.tier != 0 for c in result.candidates):
                break
        merged.candidates = MetadataLookupService._drop_duplicates(merged.candidates)
        return merged

    def _on_covers_finished(self, number: int, downloaded: list, error: str) -> None:
        if number != self._search_number:
            return
        self._cover_pending = False
        self.cover_panel.show_search_results(downloaded, error)
        self._update_apply_enabled()

    def _on_lookup_finished(self, number: int, result: LookupResult | None, error: str) -> None:
        if number != self._search_number:
            return  # a newer search superseded this one
        self._info_pending = False
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
        self._set_step(2 if self._candidates else 1)
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
        self.locked_note.hide()
        self.select_all_check.blockSignals(True)
        self.select_all_check.setChecked(False)
        self.select_all_check.blockSignals(False)
        if 0 <= row < len(self._candidates):
            self._set_step(3)
            candidate = self._candidates[row]
            doc = self._current_doc()
            locked = self.context.db.locked_fields(self.doc["id"])
            kept = [FIELD_LABELS[n] for n in _FIELD_ORDER if n in candidate.fields and n in locked]
            if kept:
                # A field the person typed by hand is never offered: say so instead of leaving it out silently.
                self.locked_note.setText("Giữ nguyên vì bạn đã tự sửa: " + ", ".join(kept) + ".")
                self.locked_note.show()
            for name in _FIELD_ORDER:
                if name not in candidate.fields or name in locked:
                    continue
                suggested, current = str(candidate.fields[name]), doc.get(name)
                current_text = "" if current is None else str(current)
                if current_text.strip().casefold() == suggested.strip().casefold():
                    continue  # nothing new
                self._add_row(name, current_text, suggested, tick=is_placeholder(name, current_text, doc),
                              source=candidate.source)
            if self.table.rowCount() == 0:
                self.status_label.setText("Kết quả này không có gì mới so với thông tin hiện tại.")
        self.table.blockSignals(False)
        self.table.resizeRowsToContents()
        self._update_apply_enabled()

    def _add_row(self, name: str, current: str, suggested: str, *, tick: bool, source: str = "") -> None:
        row = self.table.rowCount()
        self.table.insertRow(row)
        check = QTableWidgetItem()
        check.setFlags(Qt.ItemIsUserCheckable | Qt.ItemIsEnabled)
        check.setCheckState(Qt.Checked if tick else Qt.Unchecked)
        check.setData(Qt.UserRole, name)
        self.table.setItem(row, _COL_CHECK, check)
        for column, text in ((_COL_FIELD, FIELD_LABELS[name]), (_COL_CURRENT, current), (_COL_SUGGESTED, suggested),
                             (_COL_SOURCE, source)):
            item = QTableWidgetItem(_shorten(text) if column in (_COL_CURRENT, _COL_SUGGESTED) else text)
            item.setFlags(Qt.ItemIsEnabled)
            item.setToolTip(text)
            self.table.setItem(row, column, item)

    def _on_select_all_toggled(self, checked: bool) -> None:
        """"Chọn tất cả": ticks or clears every row of the comparison table at once."""
        self.table.blockSignals(True)
        for row in range(self.table.rowCount()):
            item = self.table.item(row, _COL_CHECK)
            if item is not None:
                item.setCheckState(Qt.Checked if checked else Qt.Unchecked)
        self.table.blockSignals(False)
        self._update_apply_enabled()

    def checked_changes(self) -> dict[str, str]:
        """The field -> suggested value pairs currently ticked."""
        changes = {}
        for row in range(self.table.rowCount()):
            check = self.table.item(row, _COL_CHECK)
            if check.checkState() == Qt.Checked:
                changes[check.data(Qt.UserRole)] = self.table.item(row, _COL_SUGGESTED).toolTip()
        return changes

    def _picked_cover(self) -> bytes | None:
        return self.cover_panel.picked_cover_bytes()

    def _will_apply_info(self) -> bool:
        return self.apply_info_check.isChecked() and bool(self.checked_changes())

    def _will_apply_cover(self) -> bool:
        return self.apply_cover_check.isChecked() and self._picked_cover() is not None

    def _update_apply_enabled(self) -> None:
        count = len(self.checked_changes())
        cover = self._picked_cover() is not None
        self.apply_info_check.setEnabled(count > 0)
        self.apply_cover_check.setEnabled(cover)
        info_on, cover_on = self._will_apply_info(), self._will_apply_cover()
        self.apply_button.setEnabled(info_on or cover_on)
        parts = ([f"{count} mục"] if info_on else []) + (["ảnh bìa"] if cover_on else [])
        self.apply_button.setText("Áp dụng " + " + ".join(parts) if parts else "Áp dụng")
        self.selected_label.setText(f"{count} mục được chọn" + (" · 1 ảnh bìa" if cover else ""))

    # -- apply / undo -------------------------------------------------------------------

    def _apply_cover(self) -> bool:
        """Use the picked picture as the book's cover; False (and a message) when it could not be saved."""
        data = self._picked_cover()
        doc_id = self.doc.get("id")
        if data is None or not doc_id:
            return False
        cover_path = self._cover_manager.save_cover(doc_id, data)
        if not cover_path:
            QMessageBox.warning(self, "Lỗi", "Không lưu được ảnh bìa.")
            return False
        self.context.db.update_document_cover(doc_id, cover_path)
        self.context.event_bus.publish(LibraryUpdatedEvent())
        return True

    def _on_apply(self) -> None:
        """Applies what is ticked: the information, the picture, or both -- each on its own."""
        want_cover = self._will_apply_cover()
        if not self._will_apply_info():
            if want_cover and self._apply_cover():
                QMessageBox.information(self, "Đã cập nhật", "Đã đổi ảnh bìa.")
                self.applied = True
                self.accept()
            return
        if want_cover and self._apply_cover():
            self.applied = True
        self._apply_info(also_cover=want_cover and self.applied)

    def _apply_info(self, also_cover: bool = False) -> None:
        changes = self.checked_changes()
        row = self.candidate_list.currentRow()
        if not changes or not 0 <= row < len(self._candidates):
            return
        candidate = self._candidates[row]
        write = self.write_check.isEnabled() and self.write_check.isChecked()
        if write:
            problem = self._applier.writer.backup_problem()  # "Sao lưu trước khi thay đổi" is on but has no folder
            if problem:
                QMessageBox.warning(self, "Chưa có nơi sao lưu", problem)
                return
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
        if also_cover:
            lines.append("Đã đổi ảnh bìa.")
        if result.written_fields:
            lines.append(f"Đã ghi đè {len(result.written_fields)} mục thông tin lên file sách gốc " + ("(file cũ đã được sao lưu, có thể hoàn tác)." if result.backup_made else "(không có bản sao lưu file cũ: bật \"Sao lưu trước khi thay đổi\" trong Cài đặt › Sao lưu nếu muốn)."))
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


def web_search_url(text: str) -> str:
    """The web search page for `text`, opened in the person's own browser."""
    from urllib.parse import quote_plus

    return "https://www.google.com/search?q=" + quote_plus(" ".join(text.split()) + " sách")
