# SPDX-License-Identifier: AGPL-3.0-or-later
"""The card at the top of the library that tells how adding books is going -- instead of pop-up windows.

While files are being added it shows "Đang thêm sách…", a progress bar, "Đã xong 280 / 450", a rough time left and a
"Dừng" button; when a batch is finished it is replaced by ONE summary card: ✓ added · ○ already there (skipped) ·
✕ failed (with a list), a line saying the original files were not touched, and -- when smart classification is
available and not switched off -- the question "Phân loại N sách mới này?" with "Để sau" / "Phân loại ngay".

Batches come from three places (Thêm sách…, drag and drop, the watched folders, whose files are grouped over 5 s in
the import queue), and all use this one card. It never opens a window on its own; only "xem danh sách" opens a small
list of the files that could not be added.
"""
from __future__ import annotations

import time

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QDialog,
    QFrame,
    QHBoxLayout,
    QLabel,
    QListWidget,
    QProgressBar,
    QPushButton,
    QVBoxLayout,
    QWidget,
)

from smartdoc.core.event_bus import ImportBatchCompletedEvent, ImportProgressEvent
from smartdoc.presentation.brand import accessible_name, mascot_pixmap
from smartdoc.presentation.line_icons import line_icon
from smartdoc.presentation.qt_event_bridge import QtEventBridge
from smartdoc.presentation.ornaments import notice_qss
from smartdoc.presentation.theme_manager import theme_manager


def _n(value: int) -> str:
    return f"{value:,}".replace(",", ".")


def remaining_text(done: int, total: int, elapsed: float) -> str:
    """"còn khoảng 2 phút" from the speed so far; empty until there is something to base it on."""
    if done <= 0 or elapsed < 2.0 or total <= done:
        return ""
    seconds = elapsed / done * (total - done)
    if seconds < 60:
        return "còn khoảng vài chục giây" if seconds >= 15 else "sắp xong"
    return f"còn khoảng {round(seconds / 60)} phút"


class ImportFailuresDialog(QDialog):
    def __init__(self, paths: tuple[str, ...], parent=None) -> None:
        super().__init__(parent)
        self.setWindowTitle("Các file chưa thêm được")
        self.setMinimumWidth(520)
        note = QLabel("Những file này không đọc được hoặc không phải sách. File gốc vẫn ở nguyên chỗ cũ.", self)
        note.setWordWrap(True)
        self.list_widget = QListWidget(self)
        self.list_widget.addItems(list(paths))
        close = QPushButton("Đóng", self)
        close.clicked.connect(self.accept)
        layout = QVBoxLayout(self)
        layout.setContentsMargins(16, 16, 16, 16)
        layout.setSpacing(12)
        layout.addWidget(note)
        layout.addWidget(self.list_widget, 1)
        layout.addWidget(close, 0, Qt.AlignRight)


class ImportStatusCard(QFrame):
    """See the module docstring. `import_manager` may be None (then "Dừng" does nothing); `smart_classifier` is
    the SmartClassifyService used to offer classification of the new books."""

    def __init__(self, context, import_manager=None, smart_classifier=None, parent=None) -> None:
        super().__init__(parent)
        self.context = context
        self.import_manager = import_manager
        self.smart_classifier = smart_classifier
        self.setObjectName("ImportCard")
        self.setAttribute(Qt.WA_StyledBackground, True)
        self._started_at: float | None = None
        self._last_batch: ImportBatchCompletedEvent | None = None
        self._new_ids: list[str] = []
        self.mode = "hidden"  # "progress" | "summary" | "hidden"

        self.mascot = QLabel(self)
        self.mascot.setFixedWidth(56)
        self.mascot.setAlignment(Qt.AlignCenter)

        # -- progress page --
        self.title_label = QLabel(self)
        self.title_label.setObjectName("CardTitle")
        self.eta_label = QLabel(self)
        self.eta_label.setObjectName("CardHint")
        self.bar = QProgressBar(self)
        self.bar.setTextVisible(False)
        self.bar.setFixedHeight(6)
        self.detail_label = QLabel(self)
        self.detail_label.setTextFormat(Qt.RichText)
        self.stop_button = QPushButton("Dừng", self)
        self.stop_button.setToolTip("Dừng thêm các file còn lại (sách đã thêm vẫn ở trong thư viện)")
        self.stop_button.clicked.connect(self._on_stop)

        # -- summary page --
        self.added_label = QLabel(self)
        self.duplicate_label = QLabel(self)
        self.failed_label = QLabel(self)
        self.failed_label.setTextFormat(Qt.RichText)
        self.failed_label.linkActivated.connect(self._show_failures)
        self.safe_label = QLabel("File gốc vẫn ở nguyên chỗ cũ, không bị đổi tên hay di chuyển.", self)
        self.safe_label.setObjectName("CardHint")
        self.question_label = QLabel(self)
        self.later_button = QPushButton("Để sau", self)
        self.later_button.setFlat(True)
        self.later_button.clicked.connect(self.dismiss)
        self.classify_button = QPushButton("Phân loại ngay", self)
        self.classify_button.setProperty("role", "primary")
        self.classify_button.clicked.connect(self._on_classify)
        self.close_button = QPushButton(self)
        self.close_button.setFlat(True)
        self.close_button.setToolTip("Đóng")
        self.close_button.clicked.connect(self.dismiss)

        head = QHBoxLayout()
        head.setSpacing(8)
        head.addWidget(self.title_label)
        head.addWidget(self.eta_label)
        head.addStretch(1)
        counts = QHBoxLayout()
        counts.setSpacing(16)
        for label in (self.added_label, self.duplicate_label, self.failed_label):
            counts.addWidget(label)
        counts.addStretch(1)
        middle = QVBoxLayout()
        middle.setSpacing(4)
        middle.addLayout(head)
        middle.addWidget(self.bar)
        middle.addWidget(self.detail_label)
        middle.addLayout(counts)
        middle.addWidget(self.safe_label)
        side = QVBoxLayout()
        side.setSpacing(8)
        side.addWidget(self.question_label, 0, Qt.AlignRight)
        buttons = QHBoxLayout()
        buttons.addWidget(self.later_button)
        buttons.addWidget(self.classify_button)
        side.addLayout(buttons)
        side.addWidget(self.stop_button, 0, Qt.AlignRight)
        side.addWidget(self.close_button, 0, Qt.AlignRight)
        row = QHBoxLayout(self)
        row.setContentsMargins(16, 12, 16, 12)
        row.setSpacing(12)
        row.addWidget(self.mascot, 0, Qt.AlignTop)
        row.addLayout(middle, 1)
        row.addLayout(side)

        self._restyle()
        theme_manager().themeChanged.connect(self._restyle)
        self._bridge = QtEventBridge(self)
        self._bridge.event_received.connect(self._on_bridged_event)
        self._bridge.subscribe(context.event_bus, ImportProgressEvent)
        self._bridge.subscribe(context.event_bus, ImportBatchCompletedEvent)
        self.hide()

    # -- look ------------------------------------------------------------------------------------------------------
    def _restyle(self, _key: str = "") -> None:
        tm = theme_manager()
        self.setStyleSheet(
            f"#ImportCard {{ background: {tm.token('surface')}; border: 1px solid {tm.token('line2')}; border-radius: 10px; }}"
            f" #ImportCard QLabel {{ color: {tm.token('ink')}; font-size: 13px; background: transparent; }}"
            f" #CardTitle {{ font-weight: 600; }}"
            f" #CardHint {{ color: {tm.token('ink3')}; font-size: 12px; }}"
        )
        self.setStyleSheet(self.styleSheet() + " " + notice_qss(tm, "#ImportCard"))  # a chalkboard theme overrides the card
        self.close_button.setIcon(line_icon("close", tm.token("ink3"), 12))
        self._set_mascot("waiting" if self.mode == "progress" else "done")

    def _set_mascot(self, role: str) -> None:
        pixmap = mascot_pixmap(role, 48, self.devicePixelRatioF())
        self.mascot.setPixmap(pixmap) if pixmap is not None else self.mascot.clear()
        self.mascot.setAccessibleName(accessible_name(role))

    # -- events ----------------------------------------------------------------------------------------------------
    def _on_bridged_event(self, event) -> None:
        if isinstance(event, ImportProgressEvent):
            self.show_progress(event.done, event.total)
        elif isinstance(event, ImportBatchCompletedEvent):
            self.show_summary(event)

    def show_progress(self, done: int, total: int) -> None:
        if total <= 0 or done >= total:
            if self.mode == "progress":
                self._hide_progress()
            return
        if self.mode != "progress":
            self._started_at = time.monotonic()
        self.mode = "progress"
        self._set_mascot("waiting")
        tm = theme_manager()
        self.title_label.setText("Đang thêm sách vào thư viện")
        self.eta_label.setText(remaining_text(done, total, time.monotonic() - (self._started_at or time.monotonic())))
        self.bar.setRange(0, total)
        self.bar.setValue(done)
        self.detail_label.setText(
            f"Đã xong <b>{_n(done)} / {_n(total)}</b> — có thể tiếp tục dùng thư viện trong lúc chờ")
        self.detail_label.setStyleSheet(f"color: {tm.token('ink2')}; font-size: 13px;")
        for widget in (self.title_label, self.eta_label, self.bar, self.detail_label, self.stop_button):
            widget.show()
        for widget in (self.added_label, self.duplicate_label, self.failed_label, self.safe_label, self.question_label,
                       self.later_button, self.classify_button, self.close_button):
            widget.hide()
        self.stop_button.setEnabled(True)
        self.show()

    def _hide_progress(self) -> None:
        self.mode = "hidden"
        self.hide()

    def show_summary(self, event: ImportBatchCompletedEvent) -> None:
        """ONE summary per batch. A batch with nothing to report (everything cancelled) just closes the card."""
        self._last_batch = event
        if event.success + event.duplicate + event.failed == 0:
            self.dismiss()
            return
        tm = theme_manager()
        self.mode = "summary"
        self._set_mascot("done")
        self._new_ids = list(event.doc_ids)
        self.title_label.setText(
            f"Xong: đã thêm {_n(event.success)} sách mới" if event.success else "Xong: không có sách mới nào")
        self.eta_label.setText("")
        self.added_label.setText(f"<span style='color:{tm.token('ok')}'>✓</span> {_n(event.success)} thêm mới")
        self.added_label.setTextFormat(Qt.RichText)
        self.duplicate_label.setText(f"○ {_n(event.duplicate)} trùng — bỏ qua")
        if event.failed:
            self.failed_label.setText(
                f"<span style='color:{tm.token('err')}'>■</span> {_n(event.failed)} lỗi "
                f"<a href='#' style='color:{tm.token('accent')}'>xem danh sách</a>")
        else:
            self.failed_label.setText("")
        for widget in (self.title_label, self.added_label, self.duplicate_label, self.safe_label):
            widget.show()
        self.failed_label.setVisible(bool(event.failed))
        for widget in (self.eta_label, self.bar, self.detail_label, self.stop_button):
            widget.hide()

        offer = self._classification_offer()
        self.question_label.setVisible(offer)
        self.later_button.setVisible(offer)
        self.classify_button.setVisible(offer)
        self.close_button.setVisible(not offer)
        if offer:
            self.question_label.setText(f"Phân loại {_n(len(self._new_ids))} sách mới này?")
        elif self._auto_classify():
            self.smart_classifier.enqueue(self._new_ids)
        self.show()

    def show_notice(self, text: str) -> None:
        """A one-line message in the card (no pop-up): used when a request produced nothing to add."""
        self.mode = "summary"
        self._set_mascot("thinking")
        self.title_label.setText(text)
        self.title_label.show()
        for widget in (self.eta_label, self.bar, self.detail_label, self.stop_button, self.added_label,
                       self.duplicate_label, self.failed_label, self.safe_label, self.question_label,
                       self.later_button, self.classify_button):
            widget.hide()
        self.close_button.show()
        self.show()

    # -- smart classification offer ------------------------------------------------------------------------------------
    def _mode(self) -> str:
        return self.context.config.config.smart_classify_on_import

    def _can_classify(self) -> bool:
        return bool(self._new_ids) and self.smart_classifier is not None and self._mode() != "never" \
            and self.smart_classifier.availability()[0]

    def _auto_classify(self) -> bool:
        return self._can_classify() and self._mode() == "always"

    def _classification_offer(self) -> bool:
        return self._can_classify() and self._mode() != "always"

    def _on_classify(self) -> None:
        if self.smart_classifier is not None and self._new_ids:
            self.smart_classifier.enqueue(self._new_ids)
        self.dismiss()

    # -- buttons -----------------------------------------------------------------------------------------------------------
    def _on_stop(self) -> None:
        self.stop_button.setEnabled(False)
        self.title_label.setText("Đang dừng…")
        if self.import_manager is not None:
            self.import_manager.cancel_pending()

    def dismiss(self) -> None:
        self.mode = "hidden"
        self.hide()

    def _show_failures(self, _link: str = "") -> None:
        if self._last_batch is None:
            return
        dialog = ImportFailuresDialog(self._last_batch.failed_paths, self)
        dialog.exec()
        dialog.deleteLater()


if __name__ == "__main__":
    import sys
    import tempfile
    from pathlib import Path

    from PySide6.QtWidgets import QApplication

    from smartdoc.core.app_context import AppContext

    demo = QApplication(sys.argv)
    theme_manager().apply(demo, "broadsheet")
    with tempfile.TemporaryDirectory() as tmp:
        ctx = AppContext.create_in_memory(Path(tmp))
        card = ImportStatusCard(ctx)
        card.show_progress(280, 450)
        holder = QWidget()
        QVBoxLayout(holder).addWidget(card)
        holder.resize(900, 140)
        holder.show()
        demo.exec()
        ctx.shutdown()
