# SPDX-License-Identifier: AGPL-3.0-or-later
"""Phân loại thông minh (stage G8): one dialog, three steps -- pick what to look at, watch it work, see what happened.

1. **Chọn phạm vi**: three cards ("Phần đang lọc" or the books picked in the list / "Sách chưa phân loại" / "Tất cả tài
   liệu"), each with how many books it means, a strip of a few covers and the promise that only hashtags are added.
2. **Đang phân loại**: the mascot, a progress bar with a rough time left and the last three books looked at. "Chạy nền"
   closes the dialog and lets the job go on (the status bar keeps counting); "Dừng" stops it.
3. **Kết quả**: three cards -- tagged, not sure, could not read -- each with a link that lists exactly those books, and
   "Hoàn tác phân loại", which takes back the hashtags of this run only (the ones the person added by hand stay; the
   service keys the undo by `run_id`).

The dialog only collects decisions and shows events; the work is `SmartClassifyService` (application layer). It follows
the job's events whoever started it, so opening it while a job runs lands on step 2.
"""
from __future__ import annotations

import time
from dataclasses import dataclass

from PySide6.QtCore import QPointF, QRectF, Qt, QTimer, Signal
from PySide6.QtGui import QFontMetrics, QPainter, QPen, QPixmap
from PySide6.QtWidgets import (
    QFrame,
    QHBoxLayout,
    QLabel,
    QProgressBar,
    QPushButton,
    QRadioButton,
    QStackedWidget,
    QVBoxLayout,
    QWidget,
)

from smartdoc.application.smart_classifier import ClassifyScope, SmartClassifyService
from smartdoc.core.event_bus import SmartClassifyFinishedEvent, SmartClassifyProgressEvent
from smartdoc.presentation.brand import mascot_pixmap
from smartdoc.presentation.design_dialog import DesignDialog, confirm_danger
from smartdoc.presentation.line_icons import icon_pixmap, line_icon
from smartdoc.presentation.qt_event_bridge import QtEventBridge
from smartdoc.presentation.smart_classify_results import ClassifyBooksDialog, build_tree
from smartdoc.presentation.theme_manager import theme_manager

STEP_SCOPE, STEP_RUNNING, STEP_RESULT = 0, 1, 2
_STEP_NAMES = ("Chọn phạm vi", "Đang phân loại", "Kết quả")
COVER_W, COVER_H = 52, 74
RUNNING_W = 460
WHAT_IT_DOES = "Chỉ thêm hashtag trong thư viện. <b>Không đổi tên, không di chuyển file.</b> Có thể “Hoàn tác phân loại” sau khi xong."


@dataclass(frozen=True)
class ScopeOption:
    key: str
    title: str
    description: str
    scope: ClassifyScope
    reclassify: bool = False


def _minutes(seconds: float) -> str:
    if seconds < 45:
        return "chưa tới 1 phút"
    return f"khoảng {max(1, round(seconds / 60))} phút"


class StepBar(QWidget):
    """① Chọn phạm vi —— ② Đang phân loại —— ③ Kết quả: done steps get a tick, the current one a ring."""

    def __init__(self, parent=None) -> None:
        super().__init__(parent)
        self._step = STEP_SCOPE
        self.setFixedHeight(30)

    @property
    def step(self) -> int:
        return self._step

    def set_step(self, step: int) -> None:
        self._step = step
        self.update()

    def paintEvent(self, _event) -> None:  # noqa: N802 -- Qt override
        tm = theme_manager()
        painter = QPainter(self)
        painter.setRenderHint(QPainter.Antialiasing)
        x, y, radius = 2.0, self.height() / 2, 11.0
        for index, name in enumerate(_STEP_NAMES):
            centre = QPointF(x + radius, y)
            if index < self._step:
                painter.setPen(Qt.NoPen)
                painter.setBrush(tm.color("ok"))
                painter.drawEllipse(centre, radius, radius)
                painter.drawPixmap(int(centre.x() - 6), int(centre.y() - 6), icon_pixmap("check", "#ffffff", 12))
            else:
                current = index == self._step
                painter.setPen(QPen(tm.color("ink" if current else "line2"), 1.6 if current else 1.2))
                painter.setBrush(Qt.NoBrush)
                painter.drawEllipse(centre, radius, radius)
                painter.setPen(tm.color("ink" if current else "ink3"))
                painter.drawText(QRectF(centre.x() - radius, centre.y() - radius, 2 * radius, 2 * radius),
                                 Qt.AlignCenter, str(index + 1))
            x += 2 * radius + 8
            label_font = painter.font()
            label_font.setBold(index == self._step)
            painter.setFont(label_font)
            painter.setPen(tm.color("ink" if index == self._step else "ink2" if index < self._step else "ink3"))
            width = QFontMetrics(label_font).horizontalAdvance(name)
            painter.drawText(QRectF(x, 0, width + 2, self.height()), Qt.AlignVCenter | Qt.AlignLeft, name)
            x += width + 12
            if index < len(_STEP_NAMES) - 1:
                painter.setPen(QPen(tm.color("line2"), 1))
                painter.drawLine(QPointF(x, y), QPointF(x + 36, y))
                x += 48


class _ScopeCard(QFrame):
    """One radio card: title, a line of explanation, and the number of books on the right."""

    def __init__(self, option: ScopeOption, parent: QWidget) -> None:
        super().__init__(parent)
        self.option = option
        self.setObjectName("ScopeCard")
        self.setCursor(Qt.PointingHandCursor)
        self.radio = QRadioButton(self)
        self.title_label = QLabel(option.title, self)
        self.title_label.setStyleSheet("font-weight: 600; background: transparent;")
        self.description_label = QLabel(option.description, self)
        self.description_label.setWordWrap(True)
        self.description_label.setStyleSheet(f"color: {theme_manager().token('ink2')}; font-size: 13px; background: transparent;")
        self.count_label = QLabel("", self)
        self.count_label.setStyleSheet("background: transparent;")
        text = QVBoxLayout()
        text.setSpacing(2)
        text.addWidget(self.title_label)
        text.addWidget(self.description_label)
        row = QHBoxLayout(self)
        row.setContentsMargins(14, 10, 14, 10)
        row.addWidget(self.radio, 0, Qt.AlignTop)
        row.addLayout(text, 1)
        row.addWidget(self.count_label, 0, Qt.AlignVCenter)
        self.refresh_style()

    def refresh_style(self) -> None:
        tm = theme_manager()
        border = tm.token("accent") if self.radio.isChecked() else tm.token("line")
        width = 2 if self.radio.isChecked() else 1
        self.setStyleSheet(f"#ScopeCard {{ background: {tm.token('surface')}; border: {width}px solid {border};"
                           f" border-radius: 8px; }}")

    def mousePressEvent(self, event) -> None:  # noqa: N802 -- Qt override
        if self.radio.isEnabled():
            self.radio.setChecked(True)
        super().mousePressEvent(event)


class SmartClassifyWizard(DesignDialog):
    background_finished = Signal(str)  # the job ended while the dialog was hidden: one line for the notice card

    def __init__(self, context, service: SmartClassifyService, current_scope, parent=None, *,
                 selected_scope: ClassifyScope | None = None) -> None:
        """`current_scope` is a callable returning "the list I am looking at"; `selected_scope` (the books picked in
        the list) replaces that first card."""
        super().__init__(parent, title="Phân loại thông minh", subtitle="Tự gắn hashtag dựa trên tên, mục lục và nội dung",
                         icon="bolt", width=760)
        self.context = context
        self.service = service
        self._run_id: str | None = None
        self._last_result: SmartClassifyFinishedEvent | None = None
        self._started_at = 0.0
        self._job_was_running = False  # set just before subscribing; see _on_event guard
        tm = theme_manager()

        self.step_bar = StepBar(self)
        self.body.addWidget(self.step_bar)
        self.pages = QStackedWidget(self)
        self.body.addWidget(self.pages, 1)

        # -- step 1 ----------------------------------------------------------------------------------------------
        self.options: list[ScopeOption] = []
        if selected_scope is not None:
            self.options.append(ScopeOption("selected", "Các sách đã chọn", selected_scope.description, selected_scope))
        else:
            scope = current_scope()
            self.options.append(ScopeOption("filter", "Phần đang lọc", scope.description or "Tất cả tài liệu", scope))
        self.options.append(ScopeOption("unclassified", "Sách chưa phân loại", "Chỉ những cuốn chưa có hashtag thể loại",
                                        ClassifyScope(description="Tất cả tài liệu")))
        self.options.append(ScopeOption("all", "Tất cả tài liệu", "Xét lại cả sách đã được phân loại trước đó",
                                        ClassifyScope(description="Tất cả tài liệu"), reclassify=True))
        scope_page = QWidget(self)
        scope_layout = QVBoxLayout(scope_page)
        scope_layout.setContentsMargins(0, 8, 0, 0)
        scope_layout.setSpacing(10)
        heading = QLabel("Phân loại sách nào?", self)
        heading.setStyleSheet("font-weight: 600;")
        scope_layout.addWidget(heading)
        self.cards: dict[str, _ScopeCard] = {}
        self._counts: dict[str, int] = {}
        for option in self.options:
            card = _ScopeCard(option, self)
            card.radio.toggled.connect(lambda _c, c=card: self._on_option_toggled(c))
            self.cards[option.key] = card
            scope_layout.addWidget(card)
        self.preview_heading = QLabel("", self)
        self.preview_heading.setStyleSheet("font-weight: 600;")
        scope_layout.addWidget(self.preview_heading)
        self.covers_row = QHBoxLayout()
        self.covers_row.setSpacing(8)
        scope_layout.addLayout(self.covers_row)
        self.more_label = QLabel("", self)
        self.more_label.setStyleSheet(f"color: {tm.token('ink2')};")
        self.notice_holder = QVBoxLayout()
        scope_layout.addLayout(self.notice_holder)
        scope_layout.addWidget(self.add_note_box(WHAT_IT_DOES, "ok"))
        scope_layout.addStretch(1)
        self.pages.addWidget(scope_page)

        # -- step 2 ----------------------------------------------------------------------------------------------
        running_page = QWidget(self)
        running_layout = QVBoxLayout(running_page)
        running_layout.setAlignment(Qt.AlignHCenter)
        self.mascot_label = QLabel(self)
        self.mascot_label.setAlignment(Qt.AlignCenter)
        self.running_title = QLabel("Mèo Mực đang đọc lướt từng cuốn…", self)
        self.running_title.setAlignment(Qt.AlignCenter)
        self.running_title.setStyleSheet(f"font-family: {tm.token('content')}; font-size: 18px; font-weight: 600;")
        self.progress = QProgressBar(self)
        self.progress.setTextVisible(False)
        self.progress.setFixedHeight(8)
        self.progress.setFixedWidth(RUNNING_W)
        self.done_label = QLabel("", self)
        self.eta_label = QLabel("", self)
        self.eta_label.setAlignment(Qt.AlignRight)
        counts = QHBoxLayout()
        counts.addWidget(self.done_label)
        counts.addStretch(1)
        counts.addWidget(self.eta_label)
        counts_holder = QWidget(self)
        counts_holder.setFixedWidth(RUNNING_W)
        counts_holder.setLayout(counts)
        self.recent_box = QFrame(self)
        self.recent_box.setObjectName("RecentBox")
        self.recent_box.setFixedWidth(RUNNING_W)
        self.recent_box.setStyleSheet(f"#RecentBox {{ background: {tm.token('surface')}; border: 1px solid {tm.token('line')};"
                                      f" border-radius: 8px; }}")
        recent_layout = QVBoxLayout(self.recent_box)
        recent_layout.setContentsMargins(14, 10, 14, 10)
        recent_layout.setSpacing(3)
        recent_layout.addWidget(QLabel("Vừa xong", self.recent_box))
        self.recent_labels = [QLabel("", self.recent_box) for _ in range(3)]
        for label in self.recent_labels:
            label.setTextFormat(Qt.PlainText)
            recent_layout.addWidget(label)
        self.background_hint = QLabel("Bạn có thể đóng cửa sổ này; tiến trình vẫn hiện ở thanh dưới cùng.", self)
        self.background_hint.setAlignment(Qt.AlignCenter)
        self.background_hint.setStyleSheet(f"color: {tm.token('ink2')};")
        for widget in (self.mascot_label, self.running_title):
            running_layout.addWidget(widget, 0, Qt.AlignHCenter)
        running_layout.addWidget(self.progress, 0, Qt.AlignHCenter)
        running_layout.addWidget(counts_holder, 0, Qt.AlignHCenter)
        running_layout.addWidget(self.recent_box, 0, Qt.AlignHCenter)
        running_layout.addWidget(self.background_hint)
        running_layout.addStretch(1)
        self.pages.addWidget(running_page)

        # -- step 3 ----------------------------------------------------------------------------------------------
        result_page = QWidget(self)
        result_layout = QVBoxLayout(result_page)
        result_layout.setSpacing(12)
        head = QHBoxLayout()
        self.result_mascot = QLabel(self)
        head.addWidget(self.result_mascot)
        titles = QVBoxLayout()
        titles.addStretch(1)
        self.result_title = QLabel("", self)
        self.result_title.setStyleSheet(f"font-family: {tm.token('content')}; font-size: 20px; font-weight: 600;")
        self.result_subtitle = QLabel("", self)
        self.result_subtitle.setWordWrap(True)
        self.result_subtitle.setStyleSheet(f"color: {tm.token('ink2')};")
        titles.addWidget(self.result_title)
        titles.addWidget(self.result_subtitle)
        titles.addStretch(1)
        head.addLayout(titles, 1)
        result_layout.addLayout(head)
        cards = QHBoxLayout()
        cards.setSpacing(12)
        self.tagged_count, self.tagged_link = self._result_card(cards, "check", "ok", "Đã gắn hashtag")
        self.unknown_count, self.unknown_link = self._result_card(cards, "tag", "ink3", "Chưa chắc: để bạn tự chọn")
        self.failed_count, self.failed_link = self._result_card(cards, "close", "err", "Lỗi đọc file")
        result_layout.addLayout(cards)
        result_layout.addWidget(self.add_note_box(
            "Không ưng? <b>Hoàn tác phân loại</b> sẽ gỡ toàn bộ hashtag vừa thêm ở lần chạy này. "
            "Hashtag bạn tự gắn không bị đụng tới.", "ok"))
        self.error_label = QLabel("", self)
        self.error_label.setWordWrap(True)
        self.error_label.hide()
        result_layout.addWidget(self.error_label)
        result_layout.addStretch(1)
        self.pages.addWidget(result_page)
        self.tagged_link.clicked.connect(lambda: self._show_books("tagged"))
        self.unknown_link.clicked.connect(lambda: self._show_books("unknown"))
        self.failed_link.clicked.connect(lambda: self._show_books("failed"))

        # -- footer ----------------------------------------------------------------------------------------------
        self.undo_button = self.add_footer_button("Hoàn tác phân loại", on_click=self._on_undo, left=True)
        self.undo_button.setIcon(line_icon("refresh", tm.token("ink"), 14))
        self.cancel_button = self.add_footer_button("Hủy", on_click=self.reject)
        self.start_button = self.add_footer_button("Bắt đầu", "primary", on_click=self._on_start)
        self.background_button = self.add_footer_button("Chạy nền", on_click=self._on_background)
        self.stop_button = self.add_footer_button("Dừng", "danger", on_click=self.service.cancel)
        self.done_button = self.add_footer_button("Xong", "primary", on_click=self.accept)

        # Capture before subscribing: if the job finishes between subscribe() and
        # the service.running check below, the guard in _on_event must still accept
        # the finished event (see _on_event for the race-condition explanation).
        self._job_was_running = self.service.running

        self._bridge = QtEventBridge(self)
        self._bridge.event_received.connect(self._on_event)
        self._bridge.subscribe(context.event_bus, SmartClassifyProgressEvent)
        self._bridge.subscribe(context.event_bus, SmartClassifyFinishedEvent)

        # Watchdog: fires every 2 s while on the running step. If the finished event
        # was somehow missed (bridge subscribed after publish, or slot raised), this
        # catches the dialog stuck at STEP_RUNNING and shows the result from last_result.
        self._watchdog = QTimer(self)
        self._watchdog.setInterval(2000)
        self._watchdog.timeout.connect(self._on_watchdog)

        self._load_counts()
        if self.service.running:
            self._set_step(STEP_RUNNING)
            self._show_progress(0, 0, "starting", ())
        elif self._job_was_running and self.service.last_result is not None:
            # Race: job finished between the _job_was_running snapshot and this check;
            # the finished event was published before we subscribed so it will never arrive.
            self._show_result(self.service.last_result)
        else:
            self._set_step(STEP_SCOPE)

    # -- helpers -------------------------------------------------------------------------------------------------
    def _result_card(self, row: QHBoxLayout, icon: str, colour: str, caption: str):
        tm = theme_manager()
        frame = QFrame(self)
        frame.setObjectName("ResultCard")
        frame.setStyleSheet(f"#ResultCard {{ background: {tm.token('surface')}; border: 1px solid {tm.token('line')};"
                            f" border-radius: 8px; }}")
        mark = QLabel(frame)
        mark.setPixmap(icon_pixmap(icon, tm.token(colour), 16))
        count = QLabel("0", frame)
        count.setStyleSheet("font-size: 24px; font-weight: 600; background: transparent;")
        top = QHBoxLayout()
        top.addWidget(mark)
        top.addWidget(count)
        top.addStretch(1)
        link = QPushButton("", frame)
        link.setFlat(True)
        link.setCursor(Qt.PointingHandCursor)
        link.setStyleSheet(f"QPushButton {{ border: none; background: transparent; color: {tm.token('accent')};"
                           f" text-align: left; padding: 0; text-decoration: underline; }}")
        caption_label = QLabel(caption, frame)
        caption_label.setStyleSheet("background: transparent;")
        column = QVBoxLayout(frame)
        column.setContentsMargins(14, 12, 14, 12)
        column.setSpacing(2)
        column.addLayout(top)
        column.addWidget(caption_label)
        column.addWidget(link, 0, Qt.AlignLeft)
        row.addWidget(frame, 1)
        return count, link

    def _set_step(self, step: int) -> None:
        self.step_bar.set_step(step)
        self.pages.setCurrentIndex(step)
        self.start_button.setVisible(step == STEP_SCOPE)
        self.cancel_button.setVisible(step == STEP_SCOPE)
        self.background_button.setVisible(step == STEP_RUNNING)
        self.stop_button.setVisible(step == STEP_RUNNING)
        self.done_button.setVisible(step == STEP_RESULT)
        self.undo_button.setVisible(step == STEP_RESULT)
        if step == STEP_RUNNING:
            self._watchdog.start()
        else:
            self._watchdog.stop()

    def _set_mascot(self, label: QLabel, role: str, height: int) -> None:
        pixmap = mascot_pixmap(role, height, self.devicePixelRatioF())
        label.setPixmap(pixmap if pixmap is not None else QPixmap())

    # -- step 1 --------------------------------------------------------------------------------------------------
    def _load_counts(self) -> None:
        usable, reason = self.service.availability()
        first_with_books = None
        for option in self.options:
            pending = self.service.preview(option.scope, reclassify=option.reclassify).pending
            self._counts[option.key] = pending
            card = self.cards[option.key]
            card.count_label.setText(f"{pending:,} sách".replace(",", "."))
            card.radio.setEnabled(pending > 0 and usable)
            if first_with_books is None and pending > 0:
                first_with_books = option.key
        while self.notice_holder.count():
            self.notice_holder.takeAt(0).widget().deleteLater()
        self._notice = ""
        if not usable:
            self._notice = reason
        elif self.service.model_notice():
            self._notice = self.service.model_notice()
        if self._notice:
            self.notice_holder.addWidget(self.add_note_box(self._notice, "warn", rich=False))
        chosen = first_with_books or self.options[0].key
        self.cards[chosen].radio.setChecked(True)
        self._on_option_toggled(self.cards[chosen])

    def selected_option(self) -> ScopeOption | None:
        for option in self.options:
            if self.cards[option.key].radio.isChecked():
                return option
        return None

    def _on_option_toggled(self, changed: _ScopeCard) -> None:
        if changed.radio.isChecked():
            for card in self.cards.values():
                if card is not changed and card.radio.isChecked():
                    card.radio.setChecked(False)
        for card in self.cards.values():
            card.refresh_style()
        option = self.selected_option()
        count = self._counts.get(option.key, 0) if option else 0
        self.start_button.setText(f"Bắt đầu với {count:,} sách".replace(",", ".") if count else "Bắt đầu")
        self.start_button.setEnabled(bool(option) and count > 0 and self.service.availability()[0])
        self._fill_covers(option)

    def _fill_covers(self, option: ScopeOption | None) -> None:
        while self.covers_row.count():
            item = self.covers_row.takeAt(0)
            widget = item.widget()
            if widget is not None and widget is not self.more_label:
                widget.hide()  # deleteLater is not immediate: a label out of the layout would sit at the corner
                widget.deleteLater()
            elif widget is not None:
                widget.hide()
        if option is None or not self._counts.get(option.key):
            self.preview_heading.setText("")
            return
        ids = self.service.preview_ids(option.scope, reclassify=option.reclassify, limit=6)
        docs = self.context.db.get_documents_light(ids) if ids else []
        self.preview_heading.setText("Xem trước vài cuốn trong phạm vi")
        tm = theme_manager()
        for doc in docs:
            label = QLabel(self)
            label.setFixedSize(COVER_W, COVER_H)
            label.setAlignment(Qt.AlignCenter)
            label.setToolTip(doc["title"] or "")
            pixmap = QPixmap(doc.get("cover_path") or "") if doc.get("cover_path") else QPixmap()
            if pixmap.isNull():
                label.setText("Chưa có\nbìa")
                label.setStyleSheet(f"background: {tm.token('surface2')}; border: 1px dashed {tm.token('line2')};"
                                    f" color: {tm.token('ink3')}; font-size: 10px;")
            else:
                label.setPixmap(pixmap.scaled(COVER_W, COVER_H, Qt.KeepAspectRatio, Qt.SmoothTransformation))
            self.covers_row.addWidget(label)
        rest = self._counts[option.key] - len(docs)
        if rest > 0:
            self.more_label.setText(f"…và {rest:,} cuốn khác".replace(",", "."))
            self.covers_row.addWidget(self.more_label)
            self.more_label.show()
        self.covers_row.addStretch(1)

    def _on_start(self) -> None:
        option = self.selected_option()
        if option is None:
            return
        if self.service.start(option.scope, reclassify=option.reclassify) is None:
            return  # one is already running: the events will move the dialog to step 2
        self._started_at = time.monotonic()
        self._set_step(STEP_RUNNING)
        self._show_progress(0, 0, "starting", ())

    # -- step 2 --------------------------------------------------------------------------------------------------
    def _show_progress(self, done: int, total: int, phase: str, recent: tuple) -> None:
        self._set_mascot(self.mascot_label, "thinking", 110)
        if phase == "layer2":
            self.progress.setRange(0, 0)  # indeterminate spinner: duration unknown
            self.running_title.setText("AI Lớp 2 đang xem lại sách chưa chắc…")
            self.done_label.setText(f"Lớp 1 xong: {done:,} sách. Đang chờ Ollama…".replace(",", "."))
            self.done_label.setTextFormat(Qt.PlainText)
            self.eta_label.setText("")
        elif phase == "starting" or total == 0:
            self.progress.setRange(0, 0)
            self.done_label.setText("Đang khởi động bộ phân loại…")
            self.eta_label.setText("")
        else:
            self.progress.setRange(0, total)
            self.progress.setValue(min(done, total))
            self.done_label.setText(f"Đã xong <b>{done:,}</b> / {total:,}".replace(",", "."))
            self.done_label.setTextFormat(Qt.RichText)
            elapsed = time.monotonic() - self._started_at if self._started_at else 0.0
            self.eta_label.setText(f"còn {_minutes(elapsed / done * (total - done))}" if done and elapsed else "")
        marks = {True: "✓ ", False: "○ "}
        for label, item in zip(self.recent_labels, list(recent) + [None] * 3, strict=False):
            if item is None:
                label.setText("")
            else:
                title, tag = item
                label.setText(f"{marks[bool(tag)]}{title} → #{tag.lower().replace(' ', '-')}" if tag
                              else f"{marks[False]}{title} → chưa chắc, để bạn xem")

    def _on_background(self) -> None:
        self.hide()

    # -- step 3 --------------------------------------------------------------------------------------------------
    def _show_result(self, event: SmartClassifyFinishedEvent) -> None:
        self._last_result = event
        self._run_id = event.run_id
        self._set_step(STEP_RESULT)
        self.error_label.setVisible(bool(event.error))
        if event.error:
            self._set_mascot(self.result_mascot, "sad", 96)
            self.result_title.setText("Chưa phân loại được")
            self.result_subtitle.setText(event.error)
        elif event.cancelled:
            self._set_mascot(self.result_mascot, "done", 96)
            self.result_title.setText(f"Đã dừng. {event.tagged + event.unknown + event.failed:,} sách đã được xem qua.".replace(",", "."))
            self.result_subtitle.setText("Bạn có thể chạy lại, MewBook sẽ bỏ qua những cuốn đã xét.")
        else:
            self._set_mascot(self.result_mascot, "done", 96)
            seen = event.tagged + event.unknown + event.failed
            self.result_title.setText(f"Xong. {seen:,} sách đã được xem qua.".replace(",", "."))
            self.result_subtitle.setText(
                "Không có cuốn nào cần phân loại." if event.total == 0 else "Đã dừng ở cuốn cuối cùng, không có gì bị bỏ dở.")
        for count, link, number, text in (
            (self.tagged_count, self.tagged_link, event.tagged, "Xem {n} sách"),
            (self.unknown_count, self.unknown_link, event.unknown, "Xem và chọn"),
            (self.failed_count, self.failed_link, event.failed, "Xem lý do"),
        ):
            count.setText(f"{number:,}".replace(",", "."))
            link.setText(text.format(n=f"{number:,}".replace(",", ".")))
            link.setVisible(number > 0)
        self.undo_button.setEnabled(event.tagged > 0 and not event.error)
        if not self.isVisible():
            self.background_finished.emit(self._one_line(event))

    @staticmethod
    def _one_line(event: SmartClassifyFinishedEvent) -> str:
        if event.error:
            return f"Phân loại chưa xong: {event.error}"
        return (f"Phân loại xong: {event.tagged:,} sách đã gắn hashtag, {event.unknown:,} chưa chắc, "
                f"{event.failed:,} lỗi đọc file.").replace(",", ".")

    def _show_books(self, kind: str) -> None:
        """Opens the list behind a result card: the books of this run, grouped and browsable (smart_classify_results.py)."""
        event = self._last_result
        if event is None:
            return
        if kind == "failed":
            ids = [doc_id for doc_id, _why in event.failed_items]
        else:
            ids = list(event.tagged_ids if kind == "tagged" else event.unknown_ids)
        docs = {d["id"]: d for d in self.context.db.get_documents_light(ids)} if ids else {}
        titles = {"tagged": ("Sách đã gắn hashtag", "Những cuốn được gắn ở lần chạy này, theo thư mục và hashtag"),
                  "unknown": ("Sách chưa chắc", "Theo lý do MewBook chưa dám gắn; bạn tự gắn hashtag nếu muốn"),
                  "failed": ("Sách không đọc được", "Lý do đi kèm từng nhóm; lần chạy sau MewBook sẽ thử lại")}
        dialog = ClassifyBooksDialog(
            self, title=titles[kind][0], subtitle=titles[kind][1], tree=build_tree(kind, event, docs), docs=docs,
            choices=self.service.category_choices(), tagger=self.service.tag_books,
            reload=lambda changed: {d["id"]: d for d in self.context.db.get_documents_light(list(changed))})
        dialog.exec()
        dialog.deleteLater()

    def _confirm_undo(self, tagged: int) -> bool:
        return confirm_danger(
            self, title="Hoàn tác phân loại?", subtitle="Bước xác nhận cuối",
            message=f"Hashtag đã thêm cho <b>{tagged:,} sách</b> ở lần chạy này sẽ được gỡ.".replace(",", "."),
            safe_text="<b>Không bị đụng tới:</b> hashtag bạn tự gắn và file sách trên máy.",
            ack_text="Tôi hiểu hashtag của lần chạy này sẽ bị gỡ", action_text="Hoàn tác phân loại", cancel_text="Giữ lại")

    def _on_undo(self) -> None:
        event = self._last_result
        if self._run_id is None or event is None or not self._confirm_undo(event.tagged):
            return
        changed = self.service.undo(self._run_id)
        self._run_id = None
        self.undo_button.setEnabled(False)
        self.result_title.setText(f"Đã hoàn tác: gỡ hashtag khỏi {changed:,} sách.".replace(",", "."))
        self.result_subtitle.setText("Bạn có thể chạy lại bất cứ lúc nào.")

    # -- events --------------------------------------------------------------------------------------------------
    def _on_event(self, event) -> None:
        if isinstance(event, SmartClassifyProgressEvent):
            # Don't re-enter STEP_RUNNING after the result is shown: a second background job
            # queued by AutoClassifyOnImport must not steal the dialog away from STEP_RESULT.
            if self.pages.currentIndex() == STEP_RESULT:
                return
            if self.pages.currentIndex() != STEP_RUNNING:
                self._started_at = self._started_at or time.monotonic()
                self._set_step(STEP_RUNNING)
            self._show_progress(event.done, event.total, event.phase, event.recent)
        elif isinstance(event, SmartClassifyFinishedEvent):
            # Guard: skip a finished event for a job nobody in *this* dialog started,
            # BUT not when a job was already running when the dialog opened (_job_was_running).
            # Race window: job publishes finished → bridge enqueues it → we subscribe → we
            # check service.running (False) → we land on STEP_SCOPE with _started_at=0 →
            # without _job_was_running the guard would drop the event and leave the dialog stuck.
            if self.pages.currentIndex() == STEP_SCOPE and not self._started_at and not self._job_was_running:
                return
            if self.pages.currentIndex() == STEP_RESULT:
                return  # already showed a result; a second background job's finished event is ignored
            self._job_was_running = False  # one finished event per opening is enough
            self._show_result(event)

    def _on_watchdog(self) -> None:
        """Failsafe: if the finished event was lost (bridge subscribed after publish, or a slot
        raised before _show_result ran), detect the stuck STEP_RUNNING state and recover."""
        if self.pages.currentIndex() != STEP_RUNNING:
            return
        if self.service.running:
            return  # still going, nothing to do
        result = self.service.last_result
        if result is not None:
            self._watchdog.stop()
            self._job_was_running = False
            self._show_result(result)
