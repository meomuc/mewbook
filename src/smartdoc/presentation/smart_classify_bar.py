"""The strip above the document list: the "phân loại và sắp xếp thông minh" button.

Idle, it is a single button (and a note that it applies to the list below).
While a job runs it turns into a progress display with a Stop button; when the
job ends it shows what happened, with "Hoàn tác" (undo) and a dismiss button.
Nothing here blocks: the user keeps browsing, searching and reading while the
worker process trickles through the library.

The bar reacts to the events a job publishes, whatever started it -- this
button, the "classify these new documents?" popup, the right-click menu, or the
"always classify" setting -- so its state always matches reality.
"""
from __future__ import annotations

from collections.abc import Callable

from PySide6.QtCore import Qt
from PySide6.QtWidgets import QDialog, QHBoxLayout, QLabel, QMessageBox, QProgressBar, QPushButton, QSizePolicy, QWidget

from smartdoc.application.smart_classifier import ClassifyScope, SmartClassifyService
from smartdoc.core.event_bus import SmartClassifyFinishedEvent, SmartClassifyProgressEvent
from smartdoc.presentation.qt_event_bridge import QtEventBridge
from smartdoc.presentation.smart_classify_dialogs import LIST_SUBJECT, SmartClassifyScopeDialog
from smartdoc.presentation.theme import action_css, action_text, current_colors

_IDLE_HINT = "Áp dụng cho danh sách đang xem bên dưới"


def summarize(event: SmartClassifyFinishedEvent) -> str:
    """One readable line for a finished (or stopped) job."""
    if event.error:
        return f"⚠️ {event.error}"
    if event.total == 0:
        return f"Không có tài liệu nào cần phân loại ({event.skipped:,} tài liệu đã có thể loại hoặc đã được xét)."
    parts = [f"{event.tagged:,} tài liệu đã được gắn thể loại"]
    if event.unknown:
        parts.append(f"{event.unknown:,} chưa đủ chắc chắn nên để nguyên")
    if event.failed:
        parts.append(f"{event.failed:,} không đọc được")
    if event.skipped:
        parts.append(f"{event.skipped:,} bỏ qua vì đã có thể loại")
    text = "; ".join(parts) + "."
    if event.by_group:
        top = ", ".join(f"{name} ({count:,})" for name, count in event.by_group[:3] if name)
        if top:
            text += f" Nhiều nhất: {top}."
    return ("⏹ Đã dừng. " if event.cancelled else "✅ ") + text


class _ElidedLabel(QLabel):
    """A one-line label that shortens itself to the space it gets. A plain
    QLabel demands room for its whole text, and a long result line would
    stretch the entire window."""

    def __init__(self, text: str = "", parent=None) -> None:
        super().__init__(parent)
        self._full_text = ""
        self.setTextFormat(Qt.PlainText)
        self.setSizePolicy(QSizePolicy.Ignored, QSizePolicy.Preferred)
        self.setMinimumWidth(0)
        self.setText(text)

    def setText(self, text: str) -> None:  # noqa: N802 -- Qt naming convention
        self._full_text = text
        self._elide()

    def full_text(self) -> str:
        return self._full_text

    def resizeEvent(self, event) -> None:  # noqa: N802 -- Qt naming convention
        super().resizeEvent(event)
        self._elide()

    def _elide(self) -> None:
        width = max(self.width() - 2, 0)
        shown = self.fontMetrics().elidedText(self._full_text, Qt.ElideRight, width) if width else self._full_text
        super().setText(shown)


class SmartClassifyBar(QWidget):
    def __init__(
        self,
        context,
        service: SmartClassifyService,
        scope_provider: Callable[[], ClassifyScope],
        parent=None,
    ) -> None:
        super().__init__(parent)
        self.context = context
        self.service = service
        self._scope_provider = scope_provider
        self._run_id: str | None = None

        colors = current_colors()
        self.setObjectName("SmartClassifyBar")
        self.setAttribute(Qt.WA_StyledBackground, True)
        self.setStyleSheet(
            f"#SmartClassifyBar {{ background: {colors.content_bg}; border-bottom: 1px solid {colors.border}; }}"
            f" #SmartClassifyBar QLabel {{ color: {colors.muted_text}; background: transparent; }}"
        )

        self.classify_button = QPushButton(action_text("✨ Phân loại thông minh"), self)
        self.classify_button.setCursor(Qt.PointingHandCursor)
        self.classify_button.setToolTip(
            "Tự động gắn thể loại (hashtag) và sắp xếp vào cây Hashtag cho các tài liệu đang hiển thị trong danh sách"
        )
        if colors.action_style == "default":
            self.classify_button.setStyleSheet(
                f"QPushButton {{ background: {colors.surface}; color: {colors.accent}; border: 1px solid {colors.border};"
                f" border-radius: {min(colors.control_radius, 8)}px; padding: 5px 14px; font-weight: 600; }}"
                f" QPushButton:hover {{ border-color: {colors.accent}; }}"
                f" QPushButton:disabled {{ color: {colors.muted_text}; }}"
            )
        else:
            self.classify_button.setStyleSheet(f"QPushButton {{ {action_css(colors, font_px=13)} }}")
        self.classify_button.clicked.connect(self._on_classify_clicked)

        self.status_label = _ElidedLabel(_IDLE_HINT, self)

        self.progress = QProgressBar(self)
        self.progress.setFixedWidth(180)
        self.progress.setFixedHeight(12)
        self.progress.setTextVisible(False)
        self.progress.hide()

        self.stop_button = QPushButton("Dừng", self)
        self.stop_button.setCursor(Qt.PointingHandCursor)
        self.stop_button.clicked.connect(self.service.cancel)
        self.stop_button.hide()

        self.undo_button = QPushButton("↩ Hoàn tác", self)
        self.undo_button.setCursor(Qt.PointingHandCursor)
        self.undo_button.setToolTip("Gỡ các hashtag thể loại mà lần phân loại vừa rồi đã thêm")
        self.undo_button.clicked.connect(self._on_undo_clicked)
        self.undo_button.hide()

        self.dismiss_button = QPushButton("✕", self)
        self.dismiss_button.setFlat(True)
        self.dismiss_button.setCursor(Qt.PointingHandCursor)
        self.dismiss_button.setFixedWidth(26)
        self.dismiss_button.clicked.connect(self._reset_to_idle)
        self.dismiss_button.hide()

        row = QHBoxLayout(self)
        row.setContentsMargins(max(12, colors.page_margin), 5, max(12, colors.page_margin), 5)
        row.setSpacing(10)
        row.addWidget(self.classify_button)
        row.addWidget(self.status_label, stretch=1)
        row.addWidget(self.progress)
        row.addWidget(self.stop_button)
        row.addWidget(self.undo_button)
        row.addWidget(self.dismiss_button)

        self._bridge = QtEventBridge(self)
        self._bridge.event_received.connect(self._on_bridged_event)
        self._bridge.subscribe(context.event_bus, SmartClassifyProgressEvent)
        self._bridge.subscribe(context.event_bus, SmartClassifyFinishedEvent)

        if self.service.running:
            self._show_running(0, 0, phase="starting")

    # -- Events from the job ----------------------------------------------------

    def _on_bridged_event(self, event) -> None:
        if isinstance(event, SmartClassifyProgressEvent):
            self._show_running(event.done, event.total, event.tagged, event.phase)
        elif isinstance(event, SmartClassifyFinishedEvent):
            self._show_finished(event)

    def _show_running(self, done: int, total: int, tagged: int = 0, phase: str = "running") -> None:
        self.classify_button.setEnabled(False)
        self.undo_button.hide()
        self.dismiss_button.hide()
        self.stop_button.show()
        self.stop_button.setEnabled(True)
        self.progress.show()
        if phase == "starting" or total == 0:
            self.progress.setRange(0, 0)  # busy indicator until the first result
            self.status_label.setText("Đang khởi động bộ phân loại (chạy nền)...")
        else:
            self.progress.setRange(0, total)
            self.progress.setValue(min(done, total))
            self.status_label.setText(f"Đang phân loại {done:,}/{total:,} · đã gắn thể loại cho {tagged:,}")

    def _show_finished(self, event: SmartClassifyFinishedEvent) -> None:
        self.progress.hide()
        self.stop_button.hide()
        self.classify_button.setEnabled(True)
        self.status_label.setText(summarize(event))
        self.status_label.setToolTip(summarize(event))
        self._run_id = event.run_id
        self.undo_button.setVisible(event.tagged > 0 and not event.error)
        self.dismiss_button.show()

    def _reset_to_idle(self) -> None:
        self.progress.hide()
        self.stop_button.hide()
        self.undo_button.hide()
        self.dismiss_button.hide()
        self.classify_button.setEnabled(not self.service.running)
        self.status_label.setText(_IDLE_HINT)
        self.status_label.setToolTip("")

    # -- User actions -----------------------------------------------------------

    def _on_classify_clicked(self) -> None:
        self.ask_and_start(self._scope_provider())

    def ask_and_start(self, scope: ClassifyScope, subject: str = LIST_SUBJECT) -> None:
        """Tells the user what a run over `scope` would touch, and starts it
        if they agree. `subject` is how the scope is named in that message
        ("danh sách đang xem", "các tài liệu đã chọn")."""
        usable, reason = self.service.availability()
        if not usable:
            QMessageBox.information(self, "Phân loại thông minh", reason)
            return
        if self.service.running:
            QMessageBox.information(self, "Phân loại thông minh", "Một lần phân loại khác đang chạy. Hãy chờ nó xong hoặc bấm Dừng.")
            return
        if self.service.preview(scope).total == 0:
            QMessageBox.information(self, "Phân loại thông minh", "Không có tài liệu nào để phân loại.")
            return
        dialog = SmartClassifyScopeDialog(
            scope.description or "Tất cả tài liệu",
            lambda reclassify: self.service.preview(scope, reclassify=reclassify),
            notice=self.service.model_notice(),
            parent=self,
            subject=subject,
        )
        if dialog.exec() == QDialog.Accepted:
            self.start(scope, reclassify=dialog.reclassify())

    def start(self, scope: ClassifyScope, *, reclassify: bool = False) -> bool:
        """Starts a job and puts the bar straight into its running state
        (rather than waiting for the first progress event, which only comes
        once the worker has warmed up)."""
        if self.service.start(scope, reclassify=reclassify) is None:
            QMessageBox.information(self, "Phân loại thông minh", "Một lần phân loại khác đang chạy. Hãy chờ nó xong hoặc bấm Dừng.")
            return False
        self._show_running(0, 0, phase="starting")
        return True

    def _on_undo_clicked(self) -> None:
        if not self._run_id:
            return
        confirm = QMessageBox.question(
            self,
            "Hoàn tác phân loại",
            "Gỡ các hashtag thể loại mà lần phân loại vừa rồi đã thêm? (Hashtag bạn tự gắn không bị đụng tới.)",
        )
        if confirm != QMessageBox.Yes:
            return
        changed = self.service.undo(self._run_id)
        self._run_id = None
        self.undo_button.hide()
        self.status_label.setText(f"↩ Đã hoàn tác: gỡ thể loại khỏi {changed:,} tài liệu.")


if __name__ == "__main__":
    import sys
    import tempfile
    from pathlib import Path

    from PySide6.QtWidgets import QApplication

    from smartdoc.core.app_context import AppContext
    from smartdoc.presentation.theme import apply_theme

    with tempfile.TemporaryDirectory() as tmp:
        context = AppContext.create_in_memory(Path(tmp))
        service = SmartClassifyService(context)
        app = QApplication(sys.argv)
        apply_theme(app, context.config.config.theme)
        bar = SmartClassifyBar(context, service, lambda: ClassifyScope(description="Tất cả tài liệu"))
        bar.resize(800, 40)
        bar._show_running(120, 1234, 96)
        assert "120/1,234" in bar.status_label.full_text()
        bar._show_finished(
            SmartClassifyFinishedEvent(job_id="j", run_id="r", total=100, tagged=80, unknown=15, failed=1, skipped=4,
                                       by_group=(("Văn học", 50), ("Kinh tế - Kinh doanh", 30)))
        )
        print(bar.status_label.full_text())
        assert bar.undo_button.isVisibleTo(bar)
        print("bar OK")
