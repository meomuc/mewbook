"""Document Detail Side Panel.

Shows full metadata, cover art, and quick-action buttons for the currently
selected document.  Hidden when no document or multiple documents are
selected.  Subscribes to ``DocumentSelectedEvent`` through the event bus;
the library view publishes that event whenever the selection changes.
"""
from __future__ import annotations

from datetime import datetime
from pathlib import Path

from PySide6.QtCore import QSize, Qt
from PySide6.QtGui import QCursor, QPixmap
from PySide6.QtWidgets import (
    QFrame,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QScrollArea,
    QSizePolicy,
    QVBoxLayout,
    QWidget,
)

from smartdoc.core.event_bus import DocumentSelectedEvent, LibraryUpdatedEvent
from smartdoc.presentation.file_actions import FileActionEngine
from smartdoc.presentation.metadata_editor import MetadataEditorDialog
from smartdoc.presentation.qt_event_bridge import QtEventBridge
from smartdoc.presentation.review_dialog import ReviewDialog
from smartdoc.presentation.theme import current_colors

COVER_WIDTH = 280
PANEL_MIN_WIDTH = 320


def _human_size(num_bytes: int) -> str:
    size = float(num_bytes or 0)
    for unit in ("B", "KB", "MB", "GB"):
        if size < 1024:
            return f"{size:.0f} {unit}" if unit == "B" else f"{size:.1f} {unit}"
        size /= 1024
    return f"{size:.1f} TB"


def _format_datetime(value) -> str:
    if not value:
        return "—"
    try:
        return datetime.fromtimestamp(value).strftime("%d/%m/%Y %H:%M")
    except (TypeError, ValueError, OSError):
        return "—"


def _rating_text(doc: dict) -> str:
    avg = doc.get("avg_rating")
    count = doc.get("review_count") or 0
    if avg is not None:
        return f"{avg:.1f} ★  ({count} đánh giá)"
    return "Chưa có đánh giá"


class _TagBadge(QFrame):
    """A single tag rendered as a rounded chip."""

    def __init__(self, text: str, parent=None) -> None:
        super().__init__(parent)
        colors = current_colors()
        self.setStyleSheet(
            f"background: {colors.accent}; color: {colors.accent_text}; "
            f"border-radius: 10px; padding: 3px 10px;"
        )
        label = QLabel(text, self)
        label.setStyleSheet(f"color: {colors.accent_text}; background: transparent;")
        layout = QHBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.addWidget(label)


class DocumentDetailPanel(QWidget):
    """Right-side panel showing details of the selected document."""

    def __init__(self, context, parent=None) -> None:
        super().__init__(parent)
        self.context = context
        self.file_actions = FileActionEngine(context)
        self._current_doc: dict | None = None
        self.setMinimumWidth(PANEL_MIN_WIDTH)
        self.setSizePolicy(QSizePolicy.Preferred, QSizePolicy.Expanding)

        colors = current_colors()
        self.setStyleSheet(
            f"DocumentDetailPanel {{ background: {colors.surface}; "
            f"border-left: 1px solid {colors.border}; }}"
        )

        # Scrollable inner content
        self._scroll = QScrollArea(self)
        self._scroll.setWidgetResizable(True)
        self._scroll.setFrameShape(QFrame.NoFrame)
        self._scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        self._scroll.setStyleSheet("background: transparent;")

        self._content = QWidget()
        self._content.setStyleSheet("background: transparent;")
        self._content_layout = QVBoxLayout(self._content)
        self._content_layout.setContentsMargins(16, 16, 16, 16)
        self._content_layout.setSpacing(12)

        # -- Cover --
        self.cover_label = QLabel(self._content)
        self.cover_label.setAlignment(Qt.AlignCenter)
        self.cover_label.setMinimumHeight(int(COVER_WIDTH * 1.33))
        self._content_layout.addWidget(self.cover_label)

        # -- Title --
        self.title_label = QLabel(self._content)
        self.title_label.setWordWrap(True)
        self.title_label.setStyleSheet(
            f"font-size: 16px; font-weight: bold; color: {colors.text};"
        )
        self._content_layout.addWidget(self.title_label)

        # -- Author --
        self.author_label = QLabel(self._content)
        self.author_label.setWordWrap(True)
        self.author_label.setStyleSheet(f"color: {colors.muted_text}; font-size: 13px;")
        self._content_layout.addWidget(self.author_label)

        # -- Divider --
        self._content_layout.addWidget(self._divider())

        # -- Info rows --
        self.format_size_label = self._info_label()
        self.date_added_label = self._info_label()
        self.date_modified_label = self._info_label()
        self.rating_label = self._info_label()
        self._content_layout.addWidget(self.format_size_label)
        self._content_layout.addWidget(self.date_added_label)
        self._content_layout.addWidget(self.date_modified_label)
        self._content_layout.addWidget(self.rating_label)

        # -- File path (truncated) --
        self.path_label = self._info_label()
        self.path_label.setTextInteractionFlags(Qt.TextSelectableByMouse)
        self.path_label.setCursor(QCursor(Qt.IBeamCursor))
        self._content_layout.addWidget(self.path_label)

        # -- Divider --
        self._content_layout.addWidget(self._divider())

        # -- Action buttons --
        btn_row_1 = QHBoxLayout()
        self.open_btn = self._action_button("Mở file")
        self.reveal_btn = self._action_button("Mở vị trí")
        btn_row_1.addWidget(self.open_btn)
        btn_row_1.addWidget(self.reveal_btn)
        self._content_layout.addLayout(btn_row_1)

        btn_row_2 = QHBoxLayout()
        self.edit_btn = self._action_button("Chỉnh sửa")
        self.review_btn = self._action_button("Đánh giá")
        btn_row_2.addWidget(self.edit_btn)
        btn_row_2.addWidget(self.review_btn)
        self._content_layout.addLayout(btn_row_2)

        self.open_btn.clicked.connect(self._on_open)
        self.reveal_btn.clicked.connect(self._on_reveal)
        self.edit_btn.clicked.connect(self._on_edit)
        self.review_btn.clicked.connect(self._on_review)

        # -- Divider --
        self._content_layout.addWidget(self._divider())

        # -- Tags --
        self.tags_title_label = QLabel("Thể loại", self._content)
        self.tags_title_label.setStyleSheet(
            f"font-weight: bold; color: {colors.text}; font-size: 13px;"
        )
        self._content_layout.addWidget(self.tags_title_label)
        self._tags_container = QWidget(self._content)
        self._tags_layout = _FlowLayout(self._tags_container)
        self._tags_layout.setContentsMargins(0, 0, 0, 0)
        self._content_layout.addWidget(self._tags_container)

        # -- AI Summary --
        self.summary_title_label = QLabel("Tóm tắt AI", self._content)
        self.summary_title_label.setStyleSheet(
            f"font-weight: bold; color: {colors.text}; font-size: 13px;"
        )
        self.summary_label = QLabel(self._content)
        self.summary_label.setWordWrap(True)
        self.summary_label.setStyleSheet(f"color: {colors.muted_text}; font-size: 12px;")
        self._content_layout.addWidget(self.summary_title_label)
        self._content_layout.addWidget(self.summary_label)

        # Stretch at the bottom
        self._content_layout.addStretch(1)

        self._scroll.setWidget(self._content)
        outer = QVBoxLayout(self)
        outer.setContentsMargins(0, 0, 0, 0)
        outer.addWidget(self._scroll)

        # -- Empty state --
        self._empty_label = QLabel("Chọn một tài liệu để xem chi tiết", self)
        self._empty_label.setAlignment(Qt.AlignCenter)
        self._empty_label.setWordWrap(True)
        self._empty_label.setStyleSheet(f"color: {colors.muted_text}; font-size: 13px;")
        outer.addWidget(self._empty_label)

        # Subscribe via bridge for thread safety
        self._bridge = QtEventBridge(self)
        self._bridge.event_received.connect(self._on_bridged_event)
        self._bridge.subscribe(context.event_bus, DocumentSelectedEvent)
        self._bridge.subscribe(context.event_bus, LibraryUpdatedEvent)

        self._show_empty()

    # ── Helpers ──────────────────────────────────────────────────────

    def _divider(self) -> QFrame:
        line = QFrame(self._content)
        colors = current_colors()
        line.setFrameShape(QFrame.HLine)
        line.setFrameShadow(QFrame.Plain)
        line.setStyleSheet(f"color: {colors.border};")
        line.setFixedHeight(1)
        return line

    def _info_label(self) -> QLabel:
        label = QLabel(self._content)
        label.setWordWrap(True)
        colors = current_colors()
        label.setStyleSheet(f"color: {colors.text}; font-size: 12px;")
        return label

    def _action_button(self, text: str) -> QPushButton:
        btn = QPushButton(text, self._content)
        colors = current_colors()
        btn.setStyleSheet(
            f"QPushButton {{ background: {colors.accent}; color: {colors.accent_text}; "
            f"border: none; border-radius: 4px; padding: 6px 12px; font-size: 12px; }}"
            f" QPushButton:hover {{ background: {colors.border}; color: {colors.text}; }}"
        )
        btn.setCursor(QCursor(Qt.PointingHandCursor))
        return btn

    # ── State transitions ────────────────────────────────────────────

    def _show_empty(self) -> None:
        self._scroll.hide()
        self._empty_label.show()

    def _show_detail(self) -> None:
        self._empty_label.hide()
        self._scroll.show()

    def set_document(self, doc: dict | None) -> None:
        """Update the panel for the given document, or clear it."""
        self._current_doc = doc
        if doc is None:
            self._show_empty()
            return
        self._show_detail()
        self._populate(doc)

    def _populate(self, doc: dict) -> None:
        # Cover
        cover_path = doc.get("cover_path")
        if cover_path and Path(cover_path).exists():
            pixmap = QPixmap(cover_path).scaledToWidth(
                COVER_WIDTH, Qt.SmoothTransformation
            )
            self.cover_label.setPixmap(pixmap)
        else:
            from PySide6.QtGui import QColor as _QC

            placeholder = QPixmap(QSize(COVER_WIDTH, int(COVER_WIDTH * 1.33)))
            placeholder.fill(_QC("#cfd8dc"))
            self.cover_label.setPixmap(placeholder)

        # Text fields
        self.title_label.setText(doc.get("title", "Untitled"))
        self.author_label.setText(doc.get("author", "Unknown"))

        ext = (doc.get("extension") or "").upper()
        size = _human_size(doc.get("file_size", 0))
        self.format_size_label.setText(f"📄  {ext} • {size}" if ext else f"📄  {size}")

        self.date_added_label.setText(f"📅  Thêm: {_format_datetime(doc.get('created_at'))}")
        self.date_modified_label.setText(f"✏️  Sửa: {_format_datetime(doc.get('updated_at'))}")
        self.rating_label.setText(f"⭐  {_rating_text(doc)}")

        file_path = doc.get("file_path", "")
        display_path = file_path
        if len(display_path) > 60:
            display_path = "…" + display_path[-57:]
        self.path_label.setText(f"📁  {display_path}")
        self.path_label.setToolTip(file_path)

        # Tags
        self._clear_tags()
        tags_str = doc.get("tags", "")
        if tags_str:
            for tag in tags_str.split(","):
                tag = tag.strip()
                if tag:
                    self._tags_layout.addWidget(_TagBadge(tag, self._tags_container))
            self.tags_title_label.show()
            self._tags_container.show()
        else:
            self.tags_title_label.hide()
            self._tags_container.hide()

        # AI Summary
        summary = doc.get("ai_summary")
        if summary:
            self.summary_label.setText(summary)
            self.summary_title_label.show()
            self.summary_label.show()
        else:
            self.summary_title_label.hide()
            self.summary_label.hide()

    def _clear_tags(self) -> None:
        while self._tags_layout.count():
            item = self._tags_layout.takeAt(0)
            if item and item.widget():
                item.widget().deleteLater()

    # ── Event handling ───────────────────────────────────────────────

    def _on_bridged_event(self, event) -> None:
        if isinstance(event, DocumentSelectedEvent):
            self.set_document(event.doc)
        elif isinstance(event, LibraryUpdatedEvent):
            # Re-fetch the document in case metadata changed
            if self._current_doc:
                doc_id = self._current_doc.get("id")
                if doc_id:
                    fresh = self.context.db.get_document(doc_id)
                    if fresh:
                        self.set_document(dict(fresh))
                    else:
                        self.set_document(None)

    # ── Button handlers ──────────────────────────────────────────────

    def _on_open(self) -> None:
        if self._current_doc:
            self.file_actions.open_file(self._current_doc["file_path"])

    def _on_reveal(self) -> None:
        if self._current_doc:
            self.file_actions.show_in_file_manager(self._current_doc["file_path"])

    def _on_edit(self) -> None:
        if self._current_doc:
            MetadataEditorDialog(self.context, self._current_doc, self).exec()

    def _on_review(self) -> None:
        if self._current_doc:
            ReviewDialog(self.context, self._current_doc, self).exec()


class _FlowLayout(QVBoxLayout):
    """Minimal flow layout approximation using QHBoxLayout rows.

    A real QFlowLayout implementation is non-trivial in Qt, and the tag
    list is short enough that wrapping into a few horizontal rows with
    word-wrap is perfectly acceptable here.
    """

    def __init__(self, parent=None) -> None:
        super().__init__(parent)
        self._current_row: QHBoxLayout | None = None
        self._row_widget_count = 0
        self._max_per_row = 4
        self.setSpacing(6)

    def addWidget(self, widget):  # noqa: N802 -- Qt naming convention
        if self._current_row is None or self._row_widget_count >= self._max_per_row:
            self._current_row = QHBoxLayout()
            self._current_row.setSpacing(6)
            self._current_row.setContentsMargins(0, 0, 0, 0)
            super().addLayout(self._current_row)
            self._row_widget_count = 0
        self._current_row.addWidget(widget)
        self._row_widget_count += 1

    def takeAt(self, index):  # noqa: N802
        # Used by _clear_tags: iterate nested layouts and remove widgets
        for i in range(super().count()):
            item = self.itemAt(i)
            if item and item.layout():
                inner = item.layout()
                while inner.count():
                    child = inner.takeAt(0)
                    if child and child.widget():
                        return child
        return super().takeAt(index)

    def count(self):
        total = 0
        for i in range(super().count()):
            item = self.itemAt(i)
            if item and item.layout():
                total += item.layout().count()
            elif item and item.widget():
                total += 1
        return total


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
            "d1",
            {
                "title": "Python Cơ Bản cho Người Mới Bắt Đầu",
                "author": "Nguyễn Văn A",
                "file_path": __file__,
                "file_size": 15_500_000,
                "extension": "pdf",
                "tags": "Python,Lập trình,Sách hay",
                "created_at": 1700000000.0,
            },
        )
        doc = context.db.list_all_documents()[0]

        app = QApplication(sys.argv)
        apply_light_theme(app)
        panel = DocumentDetailPanel(context)
        panel.set_document(dict(doc))
        panel.resize(340, 700)
        panel.show()
        sys.exit(app.exec())
