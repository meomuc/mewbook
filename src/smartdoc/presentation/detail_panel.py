"""Document Detail Side Panel.

Shows full metadata and cover art for the currently selected document.
There are no separate action buttons -- the info rows themselves are the
controls (click the cover to open the file, the path to reveal it in
Explorer, the rating to review it), and title/author/tags are edited
directly in place rather than through a separate dialog. Hidden when no
document or multiple documents are selected. Subscribes to
``DocumentSelectedEvent`` through the event bus; the library view publishes
that event whenever the selection changes.
"""
from __future__ import annotations

import sqlite3
import threading
from datetime import datetime
from pathlib import Path

from PySide6.QtCore import QRectF, QSize, Qt, Signal
from PySide6.QtGui import QColor, QCursor, QFont, QFontMetrics, QIcon, QPainter, QPainterPath, QPixmap
from PySide6.QtWidgets import (
    QBoxLayout,
    QFrame,
    QGraphicsDropShadowEffect,
    QHBoxLayout,
    QLabel,
    QLineEdit,
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
from smartdoc.presentation.cover_placeholder import gradient_pixmap
from smartdoc.presentation.cover_search_dialog import CoverSearchDialog
from smartdoc.presentation.file_actions import FileActionEngine
from smartdoc.presentation.format_utils import human_size as _human_size
from smartdoc.presentation.qt_event_bridge import QtEventBridge
from smartdoc.presentation.reader_manager import open_reader
from smartdoc.presentation.review_dialog import ReviewDialog
from smartdoc.presentation.sidebar_style import section_label
from smartdoc.presentation.theme import action_css, action_text, current_colors

COVER_WIDTH = 280
# The title is set this much larger than the content font size, as the
# panel's heading; the author and everything else use the size as-is.
_TITLE_STEP_PX = 4
_AUTHOR_STEP_PX = 1
# Extra width an editable field needs beyond its text: border, padding, the pencil icon and the cursor.
_EDITABLE_EXTRA_PX = 44
PANEL_MIN_WIDTH = 320


def _format_datetime(value) -> str:
    if not value:
        return "—"
    try:
        return datetime.fromtimestamp(value).strftime("%d/%m/%Y %H:%M")
    except (TypeError, ValueError, OSError):
        return "—"


def _format_date(value) -> str:
    """Date only: the added/modified dates share one row, which has no room for two full
    timestamps (the exact time stays in the tooltip)."""
    return _format_datetime(value).split(" ")[0]


def _pages_text(doc: dict) -> str:
    pages = doc.get("page_count") or 0
    if pages <= 0:
        return ""
    return f"{'~' if is_estimate(doc.get('extension')) else ''}{pages:,} trang"


def _others_texts(count: int) -> tuple[str, ...]:
    """The "other books by this author" link, longest wording first."""
    return (f"(có {count} tài liệu cùng tác giả)", f"({count} tài liệu cùng tác giả)", f"({count} cùng tác giả)")


def _rating_text(doc: dict) -> str:
    avg = doc.get("avg_rating")
    count = doc.get("review_count") or 0
    if avg is not None:
        return f"{avg:.1f} ★  ({count} đánh giá)"
    return "Chưa có đánh giá"


def _content_font_css(config, *, bold: bool = False, extra_px: int = 0) -> str:
    """CSS fragment for the document-content font (title/author/tags here)
    -- kept separate from the app's own chrome font, see AppConfig's
    docstring on content_font_family. Falls back to the theme's font stack
    (see ThemeColors.font_families) rather than the bare OS default."""
    colors = current_colors()
    if config.content_font_family:
        family = f'font-family: "{config.content_font_family}";'
    else:
        stack = ", ".join(f'"{name}"' for name in colors.font_families)
        family = f"font-family: {stack};"
    if colors.font_weight < 400:
        # Light themes stay light even for the title -- weight, not boldness,
        # is what carries their look.
        weight = f"font-weight: {400 if bold else colors.font_weight};"
    else:
        weight = "font-weight: bold;" if bold else ""
    return f"font-size: {config.content_font_size + extra_px}px; {family} {weight}"


def _rounded(pixmap: QPixmap, radius: int) -> QPixmap:
    """`pixmap` with rounded corners, for themes with soft cover corners."""
    if radius <= 2 or pixmap.isNull():
        return pixmap
    result = QPixmap(pixmap.size())
    result.fill(Qt.transparent)
    painter = QPainter(result)
    painter.setRenderHint(QPainter.Antialiasing)
    path = QPainterPath()
    path.addRoundedRect(QRectF(result.rect()), radius, radius)
    painter.setClipPath(path)
    painter.drawPixmap(0, 0, pixmap)
    painter.end()
    return result


def _rgba(color: str, alpha: float) -> str:
    c = QColor(color)
    return f"rgba({c.red()}, {c.green()}, {c.blue()}, {alpha})"


def editable_field_css(colors, font_css: str = "", text_color: str | None = None) -> str:
    """Every field you can change here looks the same: a thin outline that turns to the accent while you type, and
    a pencil at the right end (see _add_pencil). The outline and the pencil are shapes, so the difference from a
    read-only line holds even for someone who cannot tell colours apart."""
    text = text_color or colors.panel_text
    return (
        f"QLineEdit {{ {font_css} color: {text}; background: transparent; border: 1px solid {colors.border};"
        f" border-radius: 4px; padding: 4px 6px; }}"
        f" QLineEdit:hover {{ border: 1px solid {colors.muted_text}; }}"
        f" QLineEdit:focus {{ border: 1px solid {colors.accent}; }}"
    )


def readonly_field_css(colors) -> str:
    """Read-only lines: no outline, no pencil, a faint grey band behind the text."""
    return (
        f"color: {colors.panel_text}; font-size: 13px; background: {_rgba(colors.panel_text, 0.06)};"
        " border: none; border-radius: 4px; padding: 4px 8px;"
    )


def _pencil_icon(color: str) -> QIcon:
    pixmap = QPixmap(16, 16)
    pixmap.fill(Qt.transparent)
    painter = QPainter(pixmap)
    painter.setPen(QColor(color))
    font = QFont()
    font.setPixelSize(14)
    painter.setFont(font)
    painter.drawText(pixmap.rect(), Qt.AlignCenter, "✎")
    painter.end()
    return QIcon(pixmap)


def _add_pencil(edit: QLineEdit, colors) -> None:
    """Marks a line edit as editable: a pencil inside its right end."""
    action = edit.addAction(_pencil_icon(colors.muted_text), QLineEdit.TrailingPosition)
    action.setToolTip("Bấm vào ô để sửa")
    edit.setProperty("editable", True)


def _content_text_color(config, fallback: str) -> str:
    return config.content_text_color or fallback


class _ClickableLabel(QLabel):
    """A QLabel that emits ``clicked`` on left-click -- used so the detail
    panel's info rows themselves are the controls (click the cover to open,
    the path to reveal, the rating to review) instead of a separate row of
    buttons underneath."""

    clicked = Signal()

    def __init__(self, parent=None) -> None:
        super().__init__(parent)
        self.setCursor(QCursor(Qt.PointingHandCursor))

    def mouseReleaseEvent(self, event) -> None:  # noqa: N802 -- Qt naming convention
        if event.button() == Qt.LeftButton and self.rect().contains(event.pos()):
            self.clicked.emit()
        super().mouseReleaseEvent(event)


class _HashtagLabel(_ClickableLabel):
    """A single hashtag, rendered as plain clickable text -- no background,
    no border, just "#tag" in the accent color, for easy reading (per
    explicit request: chips/badges were judged too heavy for a list that's
    meant to be scanned quickly). Clicking it filters the library to every
    document sharing that tag."""

    def __init__(self, tag: str, app_config, parent=None) -> None:
        super().__init__(parent)
        self.tag = tag
        colors = current_colors()
        display_text = tag if tag.startswith("#") else f"#{tag}"
        self.setText(display_text)
        # Font family/size follow content settings like title/author; color
        # stays the theme's accent (not content_text_color) so a hashtag
        # keeps reading as a clickable link rather than as body text.
        self.setStyleSheet(f"color: {colors.accent}; {_content_font_css(app_config)}")
        self.setToolTip(f"Xem các tài liệu có {display_text}")


class _AuthorRow(QWidget):
    """Holds the author field and the "(N other books)" link, and tells the panel when
    its width changes so it can decide whether the two still fit side by side."""

    def __init__(self, on_resize, parent=None) -> None:
        super().__init__(parent)
        self._on_resize = on_resize

    def resizeEvent(self, event) -> None:  # noqa: N802 -- Qt naming convention
        super().resizeEvent(event)
        self._on_resize()


class DocumentDetailPanel(QWidget):
    """Right-side panel showing details of the selected document."""

    _page_count_ready = Signal(str, int)  # doc id, pages (0 = could not be counted)

    def __init__(self, context, parent=None) -> None:
        super().__init__(parent)
        self.context = context
        self.file_actions = FileActionEngine(context)
        self._current_doc: dict | None = None
        self._others_count = 0  # other books by this book's author(s), for the link beside the name
        self.setMinimumWidth(PANEL_MIN_WIDTH)
        self.setSizePolicy(QSizePolicy.Preferred, QSizePolicy.Expanding)

        colors = current_colors()
        self.setAttribute(Qt.WA_StyledBackground, True)
        radius = (
            f" border-top-left-radius: {colors.panel_radius}px; border-bottom-left-radius: {colors.panel_radius}px;"
            if colors.panel_radius
            else ""
        )
        self.setStyleSheet(
            f"DocumentDetailPanel {{ background: {colors.panel_bg}; "
            f"border-left: 1px solid {colors.border};{radius} }}"
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
        self._content_layout.setContentsMargins(24, 12, 24, 20)
        self._content_layout.setSpacing(10)

        # -- Refresh (re-fetch this document in case something changed it
        # outside a click this panel itself made) -- a small icon in the
        # corner rather than a whole header row above the cover --
        header_row = QHBoxLayout()
        self.refresh_label = _ClickableLabel(self._content)
        self.refresh_label.setText("⟳")
        self.refresh_label.setStyleSheet(f"color: {colors.muted_text}; font-size: 16px;")
        self.refresh_label.setToolTip("Làm mới thông tin")
        self.refresh_label.clicked.connect(self._on_refresh)
        header_row.addStretch(1)
        header_row.addWidget(self.refresh_label)
        self._content_layout.addLayout(header_row)

        # -- Cover (click to open the file) --
        self.cover_label = _ClickableLabel(self._content)
        self.cover_label.setAlignment(Qt.AlignCenter)
        self.cover_label.setMinimumHeight(int(COVER_WIDTH * 1.33))
        self.cover_label.setToolTip("Nhấn để đọc trong ứng dụng")
        cover_effect = self._cover_effect(colors)
        if cover_effect is not None:
            self.cover_label.setGraphicsEffect(cover_effect)
        self._content_layout.addWidget(self.cover_label)

        self.cover_search_label = _ClickableLabel(self._content)
        self.cover_search_label.setText(action_text("◉ Tìm ảnh bìa..."))
        self.cover_search_label.setAlignment(Qt.AlignCenter)
        self.cover_search_label.setStyleSheet(action_css(colors, font_px=13))
        self._content_layout.addWidget(self.cover_search_label)
        self._content_layout.addSpacing(8)

        # -- Title / Author: editable directly, no separate "Edit" dialog --
        # Font family/size/color here follow AppConfig.content_font_* (see
        # Settings > Font nội dung), kept separate from the app's own
        # chrome font -- not the theme's fixed 16px/13px from before.
        app_config = context.config.config
        self.title_edit = QLineEdit(self._content)
        self.title_edit.setPlaceholderText("Tiêu đề...")
        self.title_edit.setStyleSheet(
            editable_field_css(
                colors,
                _content_font_css(app_config, bold=True, extra_px=_TITLE_STEP_PX),
                _content_text_color(app_config, colors.panel_text),
            )
        )
        _add_pencil(self.title_edit, colors)
        self._content_layout.addWidget(self.title_edit)
        if colors.text_glow:
            glow = QGraphicsDropShadowEffect(self.title_edit)
            glow.setBlurRadius(12)
            glow.setOffset(0, 0)
            halo = QColor(colors.accent)
            halo.setAlpha(80)
            glow.setColor(halo)
            self.title_edit.setGraphicsEffect(glow)

        # The author is what tells one book from a same-titled other, so it gets full-contrast
        # text a step larger than the rest -- not the muted grey it used to share with captions.
        self._author_row = _AuthorRow(self._layout_author_row, self._content)
        self._author_layout = QBoxLayout(QBoxLayout.LeftToRight, self._author_row)
        self._author_layout.setContentsMargins(0, 0, 0, 0)
        self._author_layout.setSpacing(6)
        self.author_edit = QLineEdit(self._author_row)
        self.author_edit.setPlaceholderText("Tác giả...")
        self.author_edit.setStyleSheet(
            editable_field_css(
                colors,
                _content_font_css(app_config, extra_px=_AUTHOR_STEP_PX),
                _content_text_color(app_config, colors.panel_text),
            )
        )
        _add_pencil(self.author_edit, colors)
        self.author_edit.textChanged.connect(lambda _text: self._layout_author_row())

        # -- "(N other books by this author)" -- a link beside the author's name rather than
        # making the name itself clickable, since that field is where the name is *edited*
        # in place and a click there has to mean "edit".
        self.author_works_label = _ClickableLabel(self._author_row)
        self.author_works_label.setStyleSheet(f"color: {colors.accent}; font-size: 12px;")
        self.author_works_label.setWordWrap(True)
        self.author_works_label.clicked.connect(self._on_author_works_clicked)
        self._author_layout.addWidget(self.author_edit)
        self._author_layout.addWidget(self.author_works_label, 1)
        self._content_layout.addWidget(self._author_row)

        self._content_layout.addSpacing(4)

        # -- Info rows --
        self.format_size_label = self._info_label()
        self.bibliography_label = self._info_label()  # publisher, year, language, ISBN -- hidden while there are none
        self.dates_label = self._info_label()  # added and modified, side by side
        self._content_layout.addWidget(self.format_size_label)
        self._content_layout.addWidget(self.bibliography_label)
        self._content_layout.addWidget(self.dates_label)

        # -- Rating (click to open the review dialog) -- accent-colored,
        # like every other clickable action in this panel, so it visually
        # reads as "do something" rather than as plain status text.
        self.rating_label = _ClickableLabel(self._content)
        self.rating_label.setWordWrap(True)
        self.rating_label.setStyleSheet(f"color: {colors.muted_text}; font-size: 13px;")
        self.rating_label.setToolTip("Nhấn để xem / viết đánh giá")
        self._content_layout.addWidget(self.rating_label)

        # -- File path (click to reveal in Explorer) -- accent-colored too --
        self.path_label = _ClickableLabel(self._content)
        self.path_label.setWordWrap(True)
        self.path_label.setStyleSheet(f"color: {colors.muted_text}; font-size: 12px;")
        self.path_label.setToolTip("Nhấn để mở vị trí file")
        self._content_layout.addWidget(self.path_label)

        self.cover_label.clicked.connect(self._on_read)
        self.cover_search_label.clicked.connect(self._on_search_cover)
        self.rating_label.clicked.connect(self._on_review)
        self.path_label.clicked.connect(self._on_reveal)
        self.title_edit.editingFinished.connect(lambda: self._save_field("title", self.title_edit.text()))
        self.author_edit.editingFinished.connect(lambda: self._save_field("author", self.author_edit.text()))

        # -- Divider --
        self._content_layout.addWidget(self._divider())

        # -- Tags: plain clickable hashtags for display, one line edit to change them --
        self.tags_title_label = section_label("Hashtag", self._content)
        self._content_layout.addWidget(self.tags_title_label)
        self._tags_container = QWidget(self._content)
        self._tags_layout = _FlowLayout(self._tags_container)
        self._tags_layout.setContentsMargins(0, 0, 0, 0)
        self._content_layout.addWidget(self._tags_container)

        self.tags_edit = QLineEdit(self._content)
        self.tags_edit.setPlaceholderText("Thêm #tag, cách nhau bởi dấu phẩy (VD: Python, AI)...")
        self.tags_edit.setStyleSheet(editable_field_css(colors))
        _add_pencil(self.tags_edit, colors)
        self.tags_edit.editingFinished.connect(lambda: self._save_field("tags", self.tags_edit.text()))
        self._content_layout.addWidget(self.tags_edit)

        # -- Divider: separates the tags group above from AI Summary below --
        self._content_layout.addWidget(self._divider())

        # -- AI Summary --
        self.summary_title_label = section_label("Tóm tắt AI", self._content)
        self.summary_label = QLabel(self._content)
        self.summary_label.setWordWrap(True)
        self.summary_label.setStyleSheet(f"color: {colors.muted_text}; font-size: 12px;")
        self.ai_summary_action_label = _ClickableLabel(self._content)
        self.ai_summary_action_label.setStyleSheet(action_css(colors, font_px=15))
        if colors.action_style in ("bracket", "soft"):
            self.ai_summary_action_label.setAlignment(Qt.AlignCenter if colors.action_style == "bracket" else Qt.AlignLeft)
        self.ai_summary_action_label.clicked.connect(self._on_ai_summary)
        self._content_layout.addWidget(self.summary_title_label)
        self._content_layout.addWidget(self.summary_label)
        self._content_layout.addWidget(self.ai_summary_action_label)

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
        # Page counts are worked out on a worker thread; the signal hands the result back to the GUI thread.
        self._counting: set[str] = set()
        self._page_count_ready.connect(self._on_page_count_ready)

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

    def _show_bibliography(self, doc: dict) -> None:
        parts = [
            doc.get("publisher"),
            str(doc["pub_year"]) if doc.get("pub_year") else None,
            (doc.get("language") or "").upper() or None,
            f"ISBN {doc['isbn']}" if doc.get("isbn") else None,
        ]
        text = " · ".join(part for part in parts if part)
        self.bibliography_label.setText(f"📚  {text}" if text else "")
        self.bibliography_label.setVisible(bool(text))

    def _info_label(self) -> QLabel:
        label = QLabel(self._content)
        label.setWordWrap(True)
        label.setStyleSheet(readonly_field_css(current_colors()))
        label.setToolTip("Thông tin đọc từ file, không sửa được ở đây")
        label.setProperty("editable", False)
        return label

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

    def _cover_effect(self, colors):
        """The big cover's shadow in the theme's style: a neutral soft
        shadow, a warm lifted one, an accent glow (glowing themes), or none."""
        if colors.cover_shadow == "none" and not colors.text_glow:
            return None
        effect = QGraphicsDropShadowEffect(self.cover_label)
        if colors.text_glow:
            effect.setBlurRadius(26)
            effect.setOffset(0, 0)
            halo = QColor(colors.accent)
            halo.setAlpha(70)
            effect.setColor(halo)
        elif colors.cover_shadow == "warm":
            effect.setBlurRadius(22)
            effect.setOffset(0, 6)
            effect.setColor(QColor(107, 85, 64, 70))
        else:
            effect.setBlurRadius(18)
            effect.setOffset(0, 3)
            effect.setColor(QColor(0, 0, 0, 70))
        return effect

    def _populate(self, doc: dict) -> None:
        # Cover
        cover_path = doc.get("cover_path")
        if cover_path and Path(cover_path).exists():
            pixmap = QPixmap(cover_path).scaledToWidth(
                COVER_WIDTH, Qt.SmoothTransformation
            )
            self.cover_label.setPixmap(_rounded(pixmap, current_colors().cover_radius))
        else:
            placeholder_size = QSize(COVER_WIDTH, int(COVER_WIDTH * 1.33))
            placeholder = gradient_pixmap(
                doc.get("id", ""),
                placeholder_size,
                current_colors(),
                title=doc.get("title") or "",
                author=doc.get("author") or "",
            )
            self.cover_label.setPixmap(_rounded(placeholder, current_colors().cover_radius))

        # Text fields (editable directly -- setText() doesn't fire
        # editingFinished, so this never re-triggers a save)
        self.title_edit.setText(doc.get("title") or "")
        self.author_edit.setText(doc.get("author") or "")
        # Show the start of a long title/author, not its tail (setText
        # leaves the cursor -- and so the visible part -- at the end).
        self.title_edit.setCursorPosition(0)
        self.author_edit.setCursorPosition(0)
        self.title_edit.setToolTip(doc.get("title") or "")
        self._update_author_works_link(doc)

        self._show_format_line(doc)
        self._maybe_count_pages(doc)

        self._show_bibliography(doc)
        self.dates_label.setText(
            f"📅  Thêm: {_format_date(doc.get('created_at'))}  ·  🕒  Sửa: {_format_date(doc.get('updated_at'))}"
        )
        self.dates_label.setToolTip(
            f"Thêm: {_format_datetime(doc.get('created_at'))}\nSửa: {_format_datetime(doc.get('updated_at'))}"
        )
        self.rating_label.setText(f"⭐  {_rating_text(doc)}")

        file_path = doc.get("file_path", "")
        display_path = file_path
        if len(display_path) > 60:
            display_path = "…" + display_path[-57:]
        self.path_label.setText(f"📁  {display_path}")
        self.path_label.setToolTip(file_path)

        # Tags
        self._clear_tags()
        tags_str = doc.get("tags", "") or ""
        self.tags_edit.setText(tags_str)
        if tags_str:
            for tag in tags_str.split(","):
                tag = tag.strip()
                if tag:
                    hashtag_label = _HashtagLabel(tag, self.context.config.config, self._tags_container)
                    hashtag_label.clicked.connect(lambda _checked=False, t=tag: self._on_tag_clicked(t))
                    self._tags_layout.addWidget(hashtag_label)
            self._tags_container.show()
        else:
            self._tags_container.hide()

        # AI Summary
        self.summary_title_label.show()
        summary = doc.get("ai_summary")
        if summary:
            self.summary_label.setText(summary)
            self.summary_label.show()
            self.ai_summary_action_label.setText(action_text("🔄 Tạo lại tóm tắt AI"))
        else:
            self.summary_label.hide()
            self.ai_summary_action_label.setText(action_text("✦ Tạo tóm tắt AI"))

    def _show_format_line(self, doc: dict) -> None:
        parts = [(doc.get("extension") or "").upper(), _human_size(doc.get("file_size", 0)), _pages_text(doc)]
        self.format_size_label.setText("📄  " + " · ".join(part for part in parts if part))

    def _maybe_count_pages(self, doc: dict) -> None:
        """Books imported before page counts existed have none stored. Work it out once,
        for the book being looked at, off the GUI thread -- and never for a OneDrive
        placeholder, which reading would download."""
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
            self._refresh_current_document()

    def _refresh_current_document(self) -> None:
        """Re-fetches the current document from the database and
        repopulates the panel -- used both automatically (on
        LibraryUpdatedEvent, in case something changed the metadata) and
        manually via the 🔄 header button, for whenever the user wants to
        be sure they're looking at the latest information."""
        if not self._current_doc:
            return
        doc_id = self._current_doc.get("id")
        if not doc_id:
            return
        fresh = self.context.db.get_document(doc_id)
        self.set_document(dict(fresh) if fresh else None)

    # ── Click / inline-edit handlers ─────────────────────────────────

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
            ReviewDialog(self.context, self._current_doc, self).exec()

    def _on_search_cover(self) -> None:
        if self._current_doc:
            CoverSearchDialog(self.context, self._current_doc, self).exec()

    def _on_ai_summary(self) -> None:
        if self._current_doc:
            AISummaryDialog(self.context, self._current_doc, self).exec()

    def _on_tag_clicked(self, tag: str) -> None:
        """Clicking a hashtag here jumps to every document with this tag,
        not just whatever the previous filters left. The "Đang lọc" bar shows
        the (new) filter, so the jump is visible and one click undoes it."""
        self.context.filters.set(LibraryFilter(tags=(tag,)))

    def _update_author_works_link(self, doc: dict) -> None:
        names = split_author_names(doc.get("author"))
        others = 0
        if names:
            sql, params = self.context.db.filter_where(LibraryFilter(authors=tuple(names)))
            # Counts each person's own books and the ones they co-wrote (the same matching the
            # sidebar's author list uses), and excludes this book itself.
            others = self.context.db.count_documents_matching(where_sql=sql, params=params) - 1
        if others <= 0:
            self.author_works_label.hide()
        else:
            self._others_count = others
            self.author_works_label.setToolTip(
                f"Có {others} tài liệu khác cùng tác giả. Nhấn để xem các tài liệu của "
                f"{names[0] if len(names) == 1 else 'các tác giả này'}, kể cả sách viết chung"
            )
            self.author_works_label.setText(_others_texts(others)[0])
            self.author_works_label.show()
        self._layout_author_row()

    def _layout_author_row(self) -> None:
        """Name and link on one line when they fit, the link under the name when not.

        Side by side the name field is cut to its text (a QLineEdit otherwise takes all the
        width and pushes the link away), and grows as the name is edited."""
        edit, link = self.author_edit, self.author_works_label
        edit.ensurePolished()  # so font() reflects the stylesheet, not the default
        link.ensurePolished()
        text = edit.text() or edit.placeholderText()
        name_width = QFontMetrics(edit.font()).horizontalAdvance(text) + _EDITABLE_EXTRA_PX  # border, padding, pencil, cursor
        room = self._author_row.width() - name_width - self._author_layout.spacing()
        side_by_side = False
        if not link.isHidden() and self._author_row.width() > 0:
            # The full wording if it fits beside the name, else a shorter one; only when even
            # the shortest doesn't fit does the link drop below.
            link_metrics = QFontMetrics(link.font())
            for wording in _others_texts(self._others_count):
                if link_metrics.horizontalAdvance(wording) + 2 <= room:
                    link.setText(wording)
                    side_by_side = True
                    break
            else:
                link.setText(_others_texts(self._others_count)[0])
        if side_by_side:
            self._author_layout.setDirection(QBoxLayout.LeftToRight)
            edit.setFixedWidth(name_width)
        else:
            self._author_layout.setDirection(QBoxLayout.TopToBottom)
            edit.setMinimumWidth(0)
            edit.setMaximumWidth(16777215)  # QWIDGETSIZE_MAX: undo setFixedWidth

    def _on_author_works_clicked(self) -> None:
        """Shows every document by this document's author(s) -- their own
        books and any they co-wrote -- in the main library view. Like a
        hashtag click, this replaces whatever was filtered before (so the
        result matches the count the link announced) and shows up in the
        "Đang lọc" bar."""
        if not self._current_doc:
            return
        names = split_author_names(self._current_doc.get("author"))
        if not names:
            return
        self.context.filters.set(LibraryFilter(authors=tuple(names)))

    def _save_field(self, field: str, value: str) -> None:
        """Inline edit of title/author/tags directly on the panel -- these
        are the only fields the app supports editing at all (see
        DatabaseManager._EDITABLE_FIELDS), so this fully replaces the old
        separate "Edit" dialog/button for this panel."""
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
