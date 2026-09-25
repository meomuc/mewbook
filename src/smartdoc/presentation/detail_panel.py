# SPDX-License-Identifier: AGPL-3.0-or-later
"""Detail panel (324 px, right column): everything about the picked book, with title, author and hashtags edited in
place.

Layout, top to bottom: header "CHI TIẾT" (refresh, close) · the cover with a "Bấm để đọc" pill beside a column of four
actions (★ Sẽ đọc, Đổi bìa, Tìm thông tin, Gửi máy đọc) · title and author as editable fields with the link to the
author's other books · a read-only table (format, publisher, year and language, ISBN, added/modified, rating, file
location) · hashtag chips · the AI summary card. Editable fields are dashed with a pen icon; read-only rows have
neither (see editable_field.py) -- the difference is a shape, not only a colour.

The panel reacts to `DocumentSelectedEvent` (published by the library view) and `LibraryUpdatedEvent`, through
QtEventBridge. It writes only title, author and hashtags, through DatabaseManager, and never touches the book file.
"""
from __future__ import annotations

import sqlite3
import threading
from datetime import datetime
from pathlib import Path

from PySide6.QtCore import QRectF, QSize, Qt, Signal
from PySide6.QtGui import QColor, QCursor, QFont, QFontMetrics, QPainter, QPainterPath, QPixmap
from PySide6.QtWidgets import (
    QFrame,
    QGridLayout,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QPushButton,
    QScrollArea,
    QSizePolicy,
    QVBoxLayout,
    QWidget,
)

from smartdoc.core.event_bus import DocumentSelectedEvent, LibraryUpdatedEvent
from smartdoc.domain.author_names import split_author_names
from smartdoc.domain.library_filter import LibraryFilter
from smartdoc.infrastructure.cloud_files import is_cloud_only
from smartdoc.infrastructure.page_count import SUPPORTED_EXTENSIONS as _PAGE_COUNT_EXTENSIONS
from smartdoc.infrastructure.page_count import count_pages, is_estimate
from smartdoc.presentation.ai_summary_dialog import AISummaryDialog
from smartdoc.presentation.cover_search_dialog import CoverSearchDialog
from smartdoc.presentation.editable_field import EditableField
from smartdoc.presentation.file_actions import FileActionEngine
from smartdoc.presentation.format_utils import human_size as _human_size
from smartdoc.presentation.line_icons import icon_pixmap, line_icon
from smartdoc.presentation.metadata_suggest_dialog import MetadataSuggestDialog
from smartdoc.presentation.qt_event_bridge import QtEventBridge
from smartdoc.presentation.reader_manager import open_reader
from smartdoc.presentation.review_dialog import open_review_dialog
from smartdoc.presentation.sidebar_style import section_font
from smartdoc.presentation.tag_editor import TagEditor
from smartdoc.presentation.theme_manager import DETAIL_W, theme_manager

COVER_W, COVER_H = 140, 186  # the design's cover in the panel
PANEL_MIN_WIDTH = 300
LABEL_COL_W = 92
_TITLE_STEP_PX = 3  # the title is set this much larger than the content font size; everything else uses it as-is


def _format_datetime(value) -> str:
    if not value:
        return "—"
    try:
        return datetime.fromtimestamp(value).strftime("%d/%m/%Y %H:%M")
    except (TypeError, ValueError, OSError):
        return "—"


def _format_date(value) -> str:
    """Date only: added and modified share one row (the exact time stays in the tooltip)."""
    return _format_datetime(value).split(" ")[0]


def _pages_text(doc: dict) -> str:
    pages = doc.get("page_count") or 0
    if pages <= 0:
        return ""
    return f"{'~' if is_estimate(doc.get('extension')) else ''}{pages:,} trang".replace(",", ".")


def _rating_text(doc: dict) -> str:
    avg = doc.get("avg_rating")
    count = doc.get("review_count") or 0
    if avg is not None:
        return f"{avg:.1f} ★  ({count} đánh giá)"
    return "Chưa có đánh giá"


def _others_text(count: int) -> str:
    return f"Còn {count} tài liệu cùng tác giả"


def _rounded(pixmap: QPixmap, radius: int) -> QPixmap:
    if radius <= 0 or pixmap.isNull():
        return pixmap
    result = QPixmap(pixmap.size())
    result.setDevicePixelRatio(pixmap.devicePixelRatio())
    result.fill(Qt.transparent)
    painter = QPainter(result)
    painter.setRenderHint(QPainter.Antialiasing)
    path = QPainterPath()
    path.addRoundedRect(QRectF(0, 0, pixmap.width() / pixmap.devicePixelRatio(), pixmap.height() / pixmap.devicePixelRatio()),
                        radius, radius)
    painter.setClipPath(path)
    painter.drawPixmap(0, 0, pixmap)
    painter.end()
    return result


class _ClickableLabel(QLabel):
    """A QLabel that emits ``clicked`` on left-click: the row itself is the control (the path, the rating, the cover)."""

    clicked = Signal()

    def __init__(self, parent=None) -> None:
        super().__init__(parent)
        self.setCursor(QCursor(Qt.PointingHandCursor))

    def mouseReleaseEvent(self, event) -> None:  # noqa: N802 -- Qt naming convention
        if event.button() == Qt.LeftButton and self.rect().contains(event.pos()):
            self.clicked.emit()
        super().mouseReleaseEvent(event)


class _PathLabel(_ClickableLabel):
    """The file location on one line, shortened in the middle when the panel is narrow (a path has no spaces to wrap
    at, so a plain wrapping label would push the whole panel wider). The full path stays in the tooltip."""

    def __init__(self, parent=None) -> None:
        super().__init__(parent)
        self._full = ""
        self.setSizePolicy(QSizePolicy.Ignored, QSizePolicy.Preferred)

    def set_path(self, path: str) -> None:
        self._full = path
        self.setToolTip(f"{path}\nBấm để mở thư mục chứa file")
        self._elide()

    def _elide(self) -> None:
        width = max(20, self.width())
        self.setText(QFontMetrics(self.font()).elidedText(self._full, Qt.ElideMiddle, width))

    def resizeEvent(self, event) -> None:  # noqa: N802 -- Qt override
        super().resizeEvent(event)
        self._elide()

    def full_text(self) -> str:
        return self._full


class _CoverLabel(_ClickableLabel):
    """The cover, or -- for a book without one -- a plain placeholder with the title; a "Bấm để đọc" pill sits at
    the bottom (the whole cover opens the reader)."""

    def __init__(self, parent=None) -> None:
        super().__init__(parent)
        self.setFixedSize(COVER_W, COVER_H)
        self._cover: QPixmap | None = None
        self._title = ""
        self.setToolTip("Bấm để đọc trong ứng dụng")

    def set_cover(self, pixmap: QPixmap | None, title: str) -> None:
        self._cover, self._title = pixmap, title
        self.update()

    def paintEvent(self, event) -> None:  # noqa: N802 -- Qt override
        tm = theme_manager()
        painter = QPainter(self)
        painter.setRenderHint(QPainter.Antialiasing)
        painter.setRenderHint(QPainter.SmoothPixmapTransform)
        rect = self.rect()
        clip = QPainterPath()
        clip.addRoundedRect(QRectF(rect), 3, 3)
        painter.setClipPath(clip)
        if self._cover is not None and not self._cover.isNull():
            scaled = self._cover.scaled(rect.size() * self.devicePixelRatioF(), Qt.KeepAspectRatioByExpanding,
                                        Qt.SmoothTransformation)
            scaled.setDevicePixelRatio(self.devicePixelRatioF())
            x = (rect.width() - scaled.width() / self.devicePixelRatioF()) / 2
            y = (rect.height() - scaled.height() / self.devicePixelRatioF()) / 2
            painter.drawPixmap(int(x), int(y), scaled)
        else:
            painter.fillRect(rect, QColor(tm.token("surface2")))
            painter.setClipping(False)
            painter.setPen(QColor(tm.token("line2")))
            painter.drawRoundedRect(QRectF(rect).adjusted(0.5, 0.5, -0.5, -0.5), 3, 3)
            painter.drawPixmap(rect.center().x() - 12, int(rect.height() * 0.2), icon_pixmap("book", tm.token("ink3"), 24))
            font = QFont(tm.font_family("content"))
            font.setPixelSize(13)
            font.setWeight(QFont.DemiBold)
            painter.setFont(font)
            painter.setPen(QColor(tm.token("ink")))
            painter.drawText(QRectF(10, rect.height() * 0.2 + 34, rect.width() - 20, rect.height() * 0.4),
                             Qt.AlignHCenter | Qt.AlignTop | Qt.TextWordWrap, self._title)
            small = QFont(tm.font_family("ui"))
            small.setPixelSize(10)
            painter.setFont(small)
            painter.setPen(QColor(tm.token("ink3")))
            painter.drawText(QRectF(0, rect.height() - 52, rect.width(), 14), Qt.AlignCenter, "Chưa có bìa")
        painter.setClipping(False)
        # The "Bấm để đọc" pill.
        pill_font = QFont(tm.font_family("ui"))
        pill_font.setPixelSize(11)
        pill_font.setWeight(QFont.DemiBold)
        painter.setFont(pill_font)
        text = "Bấm để đọc"
        text_w = QFontMetrics(pill_font).horizontalAdvance(text)
        pill = QRectF((rect.width() - (text_w + 34)) / 2, rect.height() - 34, text_w + 34, 22)
        painter.setPen(Qt.NoPen)
        painter.setBrush(QColor(0, 0, 0, 175))
        painter.drawRoundedRect(pill, 11, 11)
        painter.drawPixmap(int(pill.left() + 9), int(pill.center().y() - 6), icon_pixmap("book", "#ffffff", 12))
        painter.setPen(QColor(255, 255, 255))
        painter.drawText(pill.adjusted(24, 0, -6, 0), Qt.AlignVCenter | Qt.AlignLeft, text)
        painter.end()


class DocumentDetailPanel(QFrame):
    """Right-side panel showing details of the selected document."""

    _page_count_ready = Signal(str, int)  # doc id, pages (0 = could not be counted)
    close_requested = Signal()  # the × in the header
    ereader_requested = Signal()  # "Gửi máy đọc": the main window sends the selected book

    def __init__(self, context, parent=None) -> None:
        super().__init__(parent)
        self.context = context
        self.file_actions = FileActionEngine(context)
        self._current_doc: dict | None = None
        self._others_count = 0
        self.setObjectName("DetailPanel")
        self.setAttribute(Qt.WA_StyledBackground, True)
        self.setMinimumWidth(PANEL_MIN_WIDTH)
        self.setSizePolicy(QSizePolicy.Preferred, QSizePolicy.Expanding)
        self.resize(DETAIL_W, 600)

        tm = theme_manager()

        # -- header: CHI TIẾT · refresh · close --
        self._header = QFrame(self)
        self._header.setObjectName("DetailHeader")
        self.title_label = QLabel("CHI TIẾT", self._header)
        self.title_label.setFont(section_font(self.title_label.font()))
        self.refresh_label = _ClickableLabel(self._header)
        self.refresh_label.setToolTip("Làm mới thông tin")
        self.refresh_label.clicked.connect(self._on_refresh)
        self.close_label = _ClickableLabel(self._header)
        self.close_label.setToolTip("Đóng panel chi tiết")
        self.close_label.clicked.connect(self.close_requested)
        header_row = QHBoxLayout(self._header)
        header_row.setContentsMargins(16, 10, 12, 6)
        header_row.setSpacing(10)
        header_row.addWidget(self.title_label)
        header_row.addStretch(1)
        header_row.addWidget(self.refresh_label)
        header_row.addWidget(self.close_label)

        # -- cover + the four actions --
        self.cover_label = _CoverLabel(self)
        self.cover_label.clicked.connect(self._on_read)
        self.star_button = self._action_button("Sẽ đọc", "star", "Thêm vào / bỏ khỏi danh sách Sẽ đọc")
        self.cover_search_label = self._action_button("Đổi bìa", "image", "Tìm hoặc chọn ảnh bìa khác")
        self.metadata_button = self._action_button("Tìm thông tin", "search", "Tìm thông tin còn thiếu của sách")
        self.ereader_button = self._action_button("Gửi máy đọc", "send", "Chép file sách sang máy đọc sách")
        self.star_button.clicked.connect(self._on_toggle_star)
        self.cover_search_label.clicked.connect(self._on_search_cover)
        self.metadata_button.clicked.connect(self._on_find_metadata)
        self.ereader_button.clicked.connect(self.ereader_requested)
        actions = QVBoxLayout()
        actions.setSpacing(8)
        for button in (self.star_button, self.cover_search_label, self.metadata_button, self.ereader_button):
            actions.addWidget(button)
        actions.addStretch(1)
        top = QHBoxLayout()
        top.setSpacing(12)
        top.addWidget(self.cover_label, 0, Qt.AlignTop)
        top.addLayout(actions, 1)

        # -- title / author: editable in place --
        self.title_edit = QLineEdit(self)
        self.title_edit.setPlaceholderText("Tên sách…")
        self.author_edit = QLineEdit(self)
        self.author_edit.setPlaceholderText("Tác giả…")
        self._apply_content_fonts()
        self.title_field = EditableField(self.title_edit, self)
        self.author_field = EditableField(self.author_edit, self)
        self.title_caption = self._caption("Tên sách · bấm để sửa")
        self.author_caption = self._caption("Tác giả")
        self.author_works_label = _ClickableLabel(self)
        self.author_works_label.clicked.connect(self._on_author_works_clicked)
        self.title_edit.editingFinished.connect(lambda: self._save_field("title", self.title_edit.text()))
        self.author_edit.editingFinished.connect(lambda: self._save_field("author", self.author_edit.text()))

        # -- read-only table --
        self.format_size_label = self._value_label()
        self.publisher_label = self._value_label()
        self.year_label = self._value_label()
        self.isbn_label = self._value_label()
        self.dates_label = self._value_label()
        self.rating_label = _ClickableLabel(self)
        self.rating_label.setToolTip("Bấm để xem / viết đánh giá")
        self.rating_label.setTextFormat(Qt.RichText)
        self.rating_label.clicked.connect(self._on_review)
        self.path_label = _PathLabel(self)
        self.path_label.clicked.connect(self._on_reveal)
        self._info_rows: list[tuple[QLabel, QWidget]] = []
        info = QGridLayout()
        info.setContentsMargins(0, 0, 0, 0)
        info.setHorizontalSpacing(8)
        info.setVerticalSpacing(8)
        info.setColumnMinimumWidth(0, LABEL_COL_W)
        info.setColumnStretch(1, 1)
        rows = (
            ("Định dạng", self.format_size_label), ("Nhà xuất bản", self.publisher_label),
            ("Năm, ngôn ngữ", self.year_label), ("ISBN", self.isbn_label),
            ("Thêm / sửa", self.dates_label), ("Đánh giá", self.rating_label), ("Vị trí file", self.path_label),
        )
        for row, (caption, value) in enumerate(rows):
            label = QLabel(caption, self)
            label.setObjectName("InfoCaption")
            label.setAlignment(Qt.AlignLeft | Qt.AlignTop)
            info.addWidget(label, row, 0, Qt.AlignTop)
            info.addWidget(value, row, 1)
            self._info_rows.append((label, value))

        # -- hashtags --
        self.tags_title_label = self._caption("Hashtag")
        self.tag_editor = TagEditor(self)
        self.tags_edit = self.tag_editor.line_edit  # the "+ thêm" text box
        self.tag_editor.changed.connect(lambda text: self._save_field("tags", text))
        self.tag_editor.tag_clicked.connect(self._on_tag_clicked)

        # -- AI summary card --
        self.summary_card = QFrame(self)
        self.summary_card.setObjectName("SummaryCard")
        self.summary_title_label = QLabel("Tóm tắt AI", self.summary_card)
        self.ai_summary_action_label = _ClickableLabel(self.summary_card)
        self.ai_summary_action_label.clicked.connect(self._on_ai_summary)
        self.summary_label = QLabel(self.summary_card)
        self.summary_label.setWordWrap(True)
        self.summary_label.setTextInteractionFlags(Qt.TextSelectableByMouse)
        card_head = QHBoxLayout()
        card_head.addWidget(self.summary_title_label)
        card_head.addStretch(1)
        card_head.addWidget(self.ai_summary_action_label)
        card = QVBoxLayout(self.summary_card)
        card.setContentsMargins(12, 10, 12, 12)
        card.setSpacing(6)
        card.addLayout(card_head)
        card.addWidget(self.summary_label)

        # -- assemble --
        self._content = QWidget()
        self._content.setObjectName("DetailContent")
        body = QVBoxLayout(self._content)
        body.setContentsMargins(16, 4, 16, 20)
        body.setSpacing(6)
        body.addLayout(top)
        body.addSpacing(6)
        body.addWidget(self.title_caption)
        body.addWidget(self.title_field)
        body.addWidget(self.author_caption)
        body.addWidget(self.author_field)
        body.addWidget(self.author_works_label)
        body.addSpacing(6)
        body.addLayout(info)
        body.addSpacing(8)
        body.addWidget(self.tags_title_label)
        body.addWidget(self.tag_editor)
        body.addSpacing(8)
        body.addWidget(self.summary_card)
        body.addStretch(1)
        self._scroll = QScrollArea(self)
        self._scroll.setWidgetResizable(True)
        self._scroll.setFrameShape(QFrame.NoFrame)
        self._scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        self._scroll.setWidget(self._content)
        self._empty_label = QLabel("Chọn một tài liệu để xem chi tiết", self)
        self._empty_label.setAlignment(Qt.AlignCenter)
        self._empty_label.setWordWrap(True)
        outer = QVBoxLayout(self)
        outer.setContentsMargins(0, 0, 0, 0)
        outer.setSpacing(0)
        outer.addWidget(self._header)
        outer.addWidget(self._scroll, 1)
        outer.addWidget(self._empty_label, 1)

        self._restyle()
        tm.themeChanged.connect(self._restyle)

        self._bridge = QtEventBridge(self)
        self._bridge.event_received.connect(self._on_bridged_event)
        self._bridge.subscribe(context.event_bus, DocumentSelectedEvent)
        self._bridge.subscribe(context.event_bus, LibraryUpdatedEvent)
        # Page counts are worked out on a worker thread; the signal hands the result back to the GUI thread.
        self._counting: set[str] = set()
        self._page_count_ready.connect(self._on_page_count_ready)
        self._show_empty()

    # -- construction helpers -------------------------------------------------------------------------------------------
    def _action_button(self, text: str, icon: str, tooltip: str) -> QPushButton:
        button = QPushButton(text, self)
        button.setProperty("icon_name", icon)
        button.setToolTip(tooltip)
        button.setMinimumHeight(28)
        button.setCursor(Qt.PointingHandCursor)
        return button

    def _caption(self, text: str) -> QLabel:
        label = QLabel(text, self)
        label.setObjectName("FieldCaption")
        return label

    def _value_label(self) -> QLabel:
        label = QLabel(self)
        label.setWordWrap(True)
        label.setTextFormat(Qt.RichText)
        label.setProperty("editable", False)
        label.setToolTip("Thông tin đọc từ file, không sửa được ở đây")
        return label

    def _apply_content_fonts(self) -> None:
        """Title and author follow Settings > Font nội dung (family, size in px, colour); the design's content face
        (Lora) is used when none is chosen."""
        config = self.context.config.config
        family = config.content_font_family or theme_manager().font_family("content")
        for edit, extra, weight in ((self.title_edit, _TITLE_STEP_PX, QFont.DemiBold), (self.author_edit, 0, QFont.Normal)):
            font = QFont(family)
            font.setPixelSize(config.content_font_size + extra)
            font.setWeight(weight)
            edit.setFont(font)
            if config.content_text_color:
                edit.setStyleSheet(f"QLineEdit {{ background: transparent; border: none; padding: 0;"
                                   f" color: {config.content_text_color}; }}")

    def _restyle(self, _key: str = "") -> None:
        tm = theme_manager()
        ink, ink2, ink3, line = tm.token("ink"), tm.token("ink2"), tm.token("ink3"), tm.token("line")
        self.setStyleSheet(
            f"#DetailPanel {{ background: {tm.token('panel')}; border-left: 1px solid {line}; }}"
            f" #DetailHeader, #DetailContent {{ background: transparent; }}"
            f" QScrollArea {{ background: transparent; }}"
            f" QLabel {{ color: {ink}; font-size: 13px; background: transparent; }}"
            f" #FieldCaption {{ color: {ink3}; font-size: 11px; font-style: italic; }}"
            f" #InfoCaption {{ color: {ink3}; font-size: 13px; }}"
            f" #SummaryCard {{ background: {tm.token('surface2')}; border-radius: 8px; }}"
            f" #SummaryCard QLabel {{ color: {ink2}; font-size: 12px; }}"
            f" QPushButton {{ text-align: left; padding: 0 10px; min-height: 26px; font-size: 12px; }}"
        )
        self.title_label.setStyleSheet(f"color: {ink3};")
        self.title_label.setFont(section_font(self.title_label.font()))
        self.refresh_label.setPixmap(icon_pixmap("refresh", ink3, 14))
        self.close_label.setPixmap(icon_pixmap("close", ink3, 14))
        self.author_works_label.setStyleSheet(f"color: {tm.token('accent')}; font-size: 13px; text-decoration: underline;")
        self.path_label.setStyleSheet(f"color: {tm.token('accent')}; font-size: 12px; text-decoration: underline;")
        self.summary_title_label.setStyleSheet(f"color: {ink}; font-size: 12px; font-weight: 600;")
        self.ai_summary_action_label.setStyleSheet(f"color: {tm.token('accent')}; font-size: 12px; text-decoration: underline;")
        self.summary_label.setStyleSheet(f"color: {ink2}; font-family: {tm.token('content')}; font-size: 13px;")
        self._empty_label.setStyleSheet(f"color: {ink3}; font-family: {tm.token('content')}; font-style: italic;")
        for button in (self.star_button, self.cover_search_label, self.metadata_button, self.ereader_button):
            button.setIcon(line_icon(button.property("icon_name"), ink2, 14))
        self._apply_content_fonts()

    # -- state transitions ----------------------------------------------------------------------------------------------
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
        tm = theme_manager()
        cover_path = doc.get("cover_path")
        cover = QPixmap(cover_path) if cover_path and Path(cover_path).exists() else None
        self.cover_label.set_cover(cover, doc.get("title") or "")

        # setText() does not fire editingFinished, so filling the fields never re-triggers a save.
        self.title_edit.setText(doc.get("title") or "")
        self.author_edit.setText("" if (doc.get("author") or "") in ("Unknown",) else doc.get("author") or "")
        self.title_edit.setCursorPosition(0)  # show the start of a long title, not its tail
        self.author_edit.setCursorPosition(0)
        self.title_edit.setToolTip(doc.get("title") or "")
        self._update_author_works_link(doc)
        self._update_star(doc)

        self._show_format_line(doc)
        self._maybe_count_pages(doc)
        self.publisher_label.setText(doc.get("publisher") or "—")
        year = str(doc["pub_year"]) if doc.get("pub_year") else ""
        language = _LANGUAGE_NAMES.get((doc.get("language") or "").lower(), (doc.get("language") or "").upper())
        self.year_label.setText(", ".join(part for part in (year, language) if part) or "—")
        self.isbn_label.setText(doc.get("isbn") or "—")
        self.dates_label.setText(f"{_format_date(doc.get('created_at'))} · {_format_date(doc.get('updated_at'))}")
        self.dates_label.setToolTip(
            f"Thêm: {_format_datetime(doc.get('created_at'))}\nSửa: {_format_datetime(doc.get('updated_at'))}")

        avg, count = doc.get("avg_rating"), doc.get("review_count") or 0
        if avg is not None:
            filled = max(0, min(5, round(avg)))
            stars = ("★" * filled) + f"<span style='color:{tm.token('line2')}'>{'★' * (5 - filled)}</span>"
            number = f"{avg:.1f}".replace(".", ",")
            self.rating_label.setText(
                f"<span style='color:{tm.token('accent')}'>{stars}</span> {number} "
                f"<span style='color:{tm.token('accent')}; text-decoration:underline'>({count} đánh giá)</span>")
        else:
            self.rating_label.setText(
                f"<span style='color:{tm.token('accent')}; text-decoration:underline'>Chưa có đánh giá · viết đánh giá</span>")

        file_path = doc.get("file_path", "")
        self.path_label.set_path(file_path)

        self.tag_editor.set_tags([t for t in (doc.get("tags", "") or "").split(",") if t.strip()])

        summary = doc.get("ai_summary")
        if summary:
            self.summary_label.setText(summary)
            self.summary_label.show()
            self.ai_summary_action_label.setText("Tạo lại")
        else:
            self.summary_label.hide()
            self.ai_summary_action_label.setText("Tạo tóm tắt")

    def _show_format_line(self, doc: dict) -> None:
        tm = theme_manager()
        extension = (doc.get("extension") or "").upper()
        chip = (f"<span style='background-color:{tm.token('surface2')}; border:1px solid {tm.token('line2')};"
                f" font-weight:600; font-size:11px;'>&nbsp;{extension}&nbsp;</span>&nbsp; ") if extension else ""
        size = _human_size(doc.get("file_size", 0)).replace(".", ",")
        pages = _pages_text(doc)
        self.format_size_label.setText(chip + ", ".join(part for part in (size, pages) if part))

    def _update_star(self, doc: dict) -> None:
        starred = doc.get("id") in self.context.db.reading_list_ids()
        self.star_button.setProperty("starred", starred)
        tm = theme_manager()
        self.star_button.setIcon(line_icon("star_fill" if starred else "star", tm.token("accent") if starred else tm.token("ink2"), 14))
        self.star_button.setText("Đã trong Sẽ đọc" if starred else "Sẽ đọc")

    def _maybe_count_pages(self, doc: dict) -> None:
        """Books imported before page counts existed have none stored. Work it out once, for the book being looked
        at, off the GUI thread -- and never for a OneDrive placeholder, which reading would download."""
        doc_id, path = doc.get("id"), doc.get("file_path") or ""
        if (
            doc.get("page_count") is not None
            or not doc_id
            or doc_id in self._counting
            or (doc.get("extension") or "").lower() not in _PAGE_COUNT_EXTENSIONS
            or is_cloud_only(path)
        ):
            return
        self._counting.add(doc_id)
        threading.Thread(
            target=self._count_in_background, args=(doc_id, path, doc["extension"]), name="page-count", daemon=True
        ).start()

    def _count_in_background(self, doc_id: str, path: str, extension: str) -> None:
        pages = count_pages(path, extension) or 0
        try:
            self.context.db.set_page_count(doc_id, pages)
            self._page_count_ready.emit(doc_id, pages)
        except (sqlite3.Error, RuntimeError):
            pass  # the app is closing: database closed or this widget already destroyed

    def _on_page_count_ready(self, doc_id: str, pages: int) -> None:
        self._counting.discard(doc_id)
        if self._current_doc and self._current_doc.get("id") == doc_id:
            self._current_doc["page_count"] = pages
            self._show_format_line(self._current_doc)

    # -- events -----------------------------------------------------------------------------------------------------------
    def _on_bridged_event(self, event) -> None:
        if isinstance(event, DocumentSelectedEvent):
            self.set_document(event.doc)
        elif isinstance(event, LibraryUpdatedEvent):
            self._refresh_current_document()

    def _refresh_current_document(self) -> None:
        """Re-fetches the current document and repopulates the panel -- automatically on LibraryUpdatedEvent and by
        hand with the refresh icon."""
        if not self._current_doc:
            return
        doc_id = self._current_doc.get("id")
        if not doc_id:
            return
        fresh = self.context.db.get_document(doc_id)
        self.set_document(dict(fresh) if fresh else None)

    # -- click / inline-edit handlers ----------------------------------------------------------------------------------------
    def _on_refresh(self) -> None:
        self._refresh_current_document()

    def _on_read(self) -> None:
        if self._current_doc:
            open_reader(self.context, self._current_doc, self)

    def _on_reveal(self) -> None:
        if self._current_doc:
            self.file_actions.show_in_file_manager(self._current_doc["file_path"])

    def _on_review(self) -> None:
        if self._current_doc:
            open_review_dialog(self.context, self._current_doc, self)

    def _on_search_cover(self) -> None:
        if self._current_doc:
            CoverSearchDialog(self.context, self._current_doc, self).exec()

    def _on_find_metadata(self) -> None:
        if self._current_doc:
            MetadataSuggestDialog(self.context, self._current_doc, self).exec()

    def _on_ai_summary(self) -> None:
        if self._current_doc:
            AISummaryDialog(self.context, self._current_doc, self).exec()

    def _on_toggle_star(self) -> None:
        doc_id = self._current_doc.get("id") if self._current_doc else None
        if not doc_id:
            return
        self.context.db.toggle_reading_list(doc_id)
        self.context.event_bus.publish(LibraryUpdatedEvent())
        self._update_star(self._current_doc)

    def _on_tag_clicked(self, tag: str) -> None:
        """Clicking a hashtag jumps to every document with it (replacing the other filters, so the list matches what
        the click promised); the "Đang lọc" bar shows the new filter and one click undoes it."""
        self.context.filters.set(LibraryFilter(tags=(tag,)))

    def _update_author_works_link(self, doc: dict) -> None:
        names = split_author_names(doc.get("author"))
        others = 0
        if names:
            sql, params = self.context.db.filter_where(LibraryFilter(authors=tuple(names)))
            # Counts each person's own books and the ones they co-wrote (the same matching the sidebar's author list
            # uses), and excludes this book itself.
            others = self.context.db.count_documents_matching(where_sql=sql, params=params) - 1
        if others <= 0:
            self.author_works_label.hide()
            return
        self._others_count = others
        self.author_works_label.setToolTip(
            f"Có {others} tài liệu khác cùng tác giả. Bấm để xem các tài liệu của "
            f"{names[0] if len(names) == 1 else 'các tác giả này'}, kể cả sách viết chung")
        self.author_works_label.setText(_others_text(others))
        self.author_works_label.show()

    def _on_author_works_clicked(self) -> None:
        """Shows every document by this document's author(s) -- their own books and any they co-wrote -- in the main
        library view, replacing whatever was filtered (so the result matches the count the link announced)."""
        if not self._current_doc:
            return
        names = split_author_names(self._current_doc.get("author"))
        if names:
            self.context.filters.set(LibraryFilter(authors=tuple(names)))

    def _save_field(self, field: str, value: str) -> None:
        """Inline edit of title/author/hashtags -- the only fields the app edits at all (see
        DatabaseManager._EDITABLE_FIELDS)."""
        if not self._current_doc:
            return
        doc_id = self._current_doc.get("id")
        if not doc_id:
            return
        value = value.strip()
        if value == (self._current_doc.get(field) or ""):
            return
        self.context.db.update_document_fields(doc_id, {field: value})
        if field in ("title", "author"):
            self.context.db.lock_fields(doc_id, [field])  # typed by hand: a metadata suggestion won't overwrite it
        self._current_doc[field] = value
        self.context.event_bus.publish(LibraryUpdatedEvent())

    def sizeHint(self) -> QSize:  # noqa: N802 -- Qt override
        return QSize(DETAIL_W, 600)


_LANGUAGE_NAMES = {"vi": "Tiếng Việt", "en": "Tiếng Anh", "fr": "Tiếng Pháp", "zh": "Tiếng Trung", "ja": "Tiếng Nhật",
                   "ko": "Tiếng Hàn", "de": "Tiếng Đức", "ru": "Tiếng Nga", "es": "Tiếng Tây Ban Nha"}


if __name__ == "__main__":
    import sys
    import tempfile

    from PySide6.QtWidgets import QApplication

    from smartdoc.core.app_context import AppContext

    with tempfile.TemporaryDirectory() as tmp:
        context = AppContext.create_in_memory(Path(tmp))
        context.db.add_or_update_document(
            "d1", {"title": "Thiết kế hệ thống điện nhẹ", "author": "Nguyễn Văn Hải", "file_path": __file__,
                   "file_size": 12_400_000, "extension": "pdf", "tags": "điện-nhẹ,camera", "created_at": 1700000000.0})
        app = QApplication(sys.argv)
        theme_manager().apply(app, "broadsheet")
        panel = DocumentDetailPanel(context)
        panel.set_document(dict(context.db.list_all_documents()[0]))
        panel.resize(340, 800)
        panel.show()
        sys.exit(app.exec())
