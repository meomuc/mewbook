"""Bottom selection action bar -- the "Kệ Sách Gỗ" theme's replacement for
the right-hand Document Detail Panel.

That theme gives the covers the full width of the window instead of
reserving a permanent column for details of whichever book happens to be
selected. This bar is the trade-off: it stays out of the way entirely
until something is selected, then slides in along the bottom with just the
things you actually act on -- open, edit, and the rest behind one overflow
menu -- rather than the panel's full metadata dump.

Everything here reuses the same dialogs/actions the detail panel and the
library view's context menu already use; this is a different surface for
them, not a second implementation.
"""
from __future__ import annotations

from pathlib import Path

from PySide6.QtCore import QSize, Qt
from PySide6.QtGui import QColor, QPixmap
from PySide6.QtWidgets import (
    QGraphicsDropShadowEffect,
    QHBoxLayout,
    QLabel,
    QMenu,
    QPushButton,
    QVBoxLayout,
    QWidget,
)

from smartdoc.core.event_bus import DocumentSelectedEvent, LibraryUpdatedEvent
from smartdoc.presentation.ai_summary_dialog import AISummaryDialog
from smartdoc.presentation.cover_placeholder import gradient_pixmap
from smartdoc.presentation.cover_search_dialog import CoverSearchDialog
from smartdoc.presentation.file_actions import FileActionEngine
from smartdoc.presentation.format_utils import human_size
from smartdoc.presentation.metadata_editor import MetadataEditorDialog
from smartdoc.presentation.qt_event_bridge import QtEventBridge
from smartdoc.presentation.reader_manager import open_reader
from smartdoc.presentation.review_dialog import ReviewDialog
from smartdoc.presentation.theme import current_colors

BAR_HEIGHT = 84
_MINI_COVER = QSize(48, 68)


class SelectionActionBar(QWidget):
    def __init__(self, context, parent=None) -> None:
        super().__init__(parent)
        self.context = context
        self.file_actions = FileActionEngine(context)
        self._doc: dict | None = None

        self.setFixedHeight(BAR_HEIGHT)
        colors = current_colors()
        self.setAttribute(Qt.WA_StyledBackground, True)
        self.setStyleSheet(
            f"SelectionActionBar {{ background: {colors.surface};"
            f" border-top: 1px solid {colors.border}; }}"
        )
        cover_shadow = QGraphicsDropShadowEffect(self)
        cover_shadow.setBlurRadius(8)
        cover_shadow.setOffset(0, 2)
        cover_shadow.setColor(QColor(0, 0, 0, 60))

        self.cover_label = QLabel(self)
        self.cover_label.setFixedSize(_MINI_COVER)
        self.cover_label.setScaledContents(True)
        self.cover_label.setGraphicsEffect(cover_shadow)

        self.title_label = QLabel(self)
        self.title_label.setStyleSheet(f"color: {colors.sidebar_text}; font-weight: 600; font-size: 16px;")
        self.subtitle_label = QLabel(self)
        self.subtitle_label.setStyleSheet(f"color: {colors.muted_text}; font-size: 13px;")

        text_column = QVBoxLayout()
        text_column.setContentsMargins(0, 0, 0, 0)
        text_column.setSpacing(2)
        text_column.addStretch(1)
        text_column.addWidget(self.title_label)
        text_column.addWidget(self.subtitle_label)
        text_column.addStretch(1)

        self.open_button = QPushButton("Mở sách", self)
        self.open_button.setCursor(Qt.PointingHandCursor)
        self.open_button.setStyleSheet(
            f"QPushButton {{ background: {colors.accent}; color: {colors.accent_text}; border: none;"
            " border-radius: 3px; padding: 10px 22px; font-weight: 600; font-size: 14px; }"
            f" QPushButton:hover {{ background: {colors.selected_text}; }}"
        )
        self.open_button.clicked.connect(self._on_open)

        self.edit_button = QPushButton("Chỉnh sửa", self)
        self.edit_button.setCursor(Qt.PointingHandCursor)
        self.edit_button.setStyleSheet(
            f"QPushButton {{ background: {colors.surface}; color: {colors.sidebar_text};"
            f" border: 1px solid rgba(32,30,29,.18); border-radius: 3px; padding: 9px 18px; font-size: 14px; }}"
            f" QPushButton:hover {{ border: 1px solid {colors.accent}; color: {colors.accent}; }}"
        )
        self.edit_button.clicked.connect(self._on_edit)

        self.more_button = QPushButton("⋯", self)
        self.more_button.setCursor(Qt.PointingHandCursor)
        self.more_button.setFixedSize(40, 40)
        self.more_button.setStyleSheet(
            f"QPushButton {{ background: {colors.surface}; color: {colors.sidebar_text};"
            f" border: 1px solid rgba(32,30,29,.18); border-radius: 3px; font-size: 15px; }}"
            f" QPushButton:hover {{ border: 1px solid {colors.accent}; color: {colors.accent}; }}"
        )
        self.more_button.clicked.connect(self._on_more)

        row = QHBoxLayout(self)
        row.setContentsMargins(30, 8, 30, 8)
        row.setSpacing(10)
        row.addWidget(self.cover_label)
        row.addSpacing(8)
        row.addLayout(text_column, stretch=1)
        row.addWidget(self.open_button)
        row.addWidget(self.edit_button)
        row.addWidget(self.more_button)

        self._bridge = QtEventBridge(self)
        self._bridge.event_received.connect(self._on_bridged_event)
        self._bridge.subscribe(context.event_bus, DocumentSelectedEvent)
        self._bridge.subscribe(context.event_bus, LibraryUpdatedEvent)

        self.hide()  # nothing selected yet -- the bar only exists when it has something to act on

    def _on_bridged_event(self, event) -> None:
        if isinstance(event, DocumentSelectedEvent):
            self.set_document(event.doc)
        elif isinstance(event, LibraryUpdatedEvent) and self._doc:
            refreshed = self.context.db.get_document(self._doc["id"])
            if refreshed:
                self.set_document(refreshed)

    def set_document(self, doc: dict | None) -> None:
        self._doc = doc
        if doc is None:
            self.hide()
            return

        title = doc.get("title") or "(Không có tiêu đề)"
        self.title_label.setText(title if len(title) <= 70 else title[:69] + "…")

        parts = [doc.get("author") or "Không rõ tác giả"]
        extension = (doc.get("extension") or "").upper()
        if extension:
            parts.append(extension)
        parts.append(human_size(doc.get("file_size", 0)))
        self.subtitle_label.setText(" · ".join(parts))

        cover_path = doc.get("cover_path")
        if cover_path and Path(cover_path).exists():
            self.cover_label.setPixmap(QPixmap(cover_path))
        else:
            self.cover_label.setPixmap(gradient_pixmap(doc.get("id", ""), _MINI_COVER * 2, current_colors()))
        self.show()

    # ── Actions ─────────────────────────────────────────────────────────

    def _on_open(self) -> None:
        if not self._doc:
            return
        open_reader(self.context, self._doc, self)

    def _on_edit(self) -> None:
        if self._doc:
            MetadataEditorDialog(self.context, self._doc, self).exec()

    def _on_more(self) -> None:
        if not self._doc:
            return
        menu = QMenu(self)
        cover_action = menu.addAction("🔍 Tìm ảnh bìa...")
        review_action = menu.addAction("⭐ Đánh giá...")
        summary_action = menu.addAction("✨ Tóm tắt AI...")
        menu.addSeparator()
        reveal_action = menu.addAction("📁 Mở vị trí file")

        chosen = self._exec_menu(menu)
        if chosen == cover_action:
            CoverSearchDialog(self.context, self._doc, self).exec()
        elif chosen == review_action:
            ReviewDialog(self.context, self._doc, self).exec()
        elif chosen == summary_action:
            AISummaryDialog(self.context, self._doc, self).exec()
        elif chosen == reveal_action:
            self.file_actions.show_in_file_manager(self._doc.get("file_path", ""))

    def _exec_menu(self, menu: QMenu):
        """Thin seam so tests can patch this instead of QMenu.exec, which
        opens a real modal loop that hangs forever under an offscreen Qt
        platform (same pattern as library_view/sidebar)."""
        return menu.exec(self.more_button.mapToGlobal(self.more_button.rect().bottomLeft()))
