"""TDD-013 (with the pagination/sort/cover-size Milestone D upgrades applied).

Qt Model/View so the widget cost stays flat regardless of library size —
QListView only ever calls data() for rows currently on screen, no matter
how many documents are loaded into the model. Grouping is not implemented
yet.
"""
from __future__ import annotations

import math
import os
import time
from datetime import datetime
from pathlib import Path

from PySide6.QtCore import (
    QAbstractListModel,
    QAbstractTableModel,
    QEvent,
    QModelIndex,
    QRect,
    QRectF,
    QSize,
    Qt,
    QTimer,
    Signal,
)
from PySide6.QtGui import (
    QColor,
    QFont,
    QFontMetrics,
    QIcon,
    QKeySequence,
    QPainter,
    QPainterPath,
    QPalette,
    QPen,
    QPixmap,
    QShortcut,
    QTextLayout,
)
from PySide6.QtWidgets import (
    QAbstractItemView,
    QApplication,
    QFileDialog,
    QHBoxLayout,
    QHeaderView,
    QInputDialog,
    QLabel,
    QListView,
    QMenu,
    QMessageBox,
    QPushButton,
    QSpinBox,
    QStackedWidget,
    QStyle,
    QStyledItemDelegate,
    QStyleOptionViewItem,
    QTableView,
    QVBoxLayout,
    QWidget,
)

from smartdoc.application.smart_classifier import ClassifyScope
from smartdoc.core.event_bus import (
    CoverSizeChangedEvent,
    DocumentSelectedEvent,
    FilterChangedEvent,
    LibraryUpdatedEvent,
    SortChangedEvent,
    ViewModeChangedEvent,
)
from smartdoc.domain.library_filter import LibraryFilter, describe
from smartdoc.domain.smart_collections import VirtualCollection
from smartdoc.presentation.ai_summary_dialog import AISummaryDialog
from smartdoc.presentation.clipboard_files import get_clipboard_file_paths, set_clipboard_files
from smartdoc.presentation.cover_loader import CoverLoader
from smartdoc.presentation.featured_book import FeaturedBookCard
from smartdoc.presentation.cover_placeholder import gradient_pixmap
from smartdoc.presentation.cover_search_dialog import CoverSearchDialog
from smartdoc.presentation.file_actions import FileActionEngine
from smartdoc.presentation.format_utils import human_size
from smartdoc.presentation.metadata_editor import BatchEditorDialog, MetadataEditorDialog
from smartdoc.presentation.metadata_suggest_dialog import MetadataSuggestDialog
from smartdoc.presentation.qt_event_bridge import QtEventBridge
from smartdoc.presentation.reader_manager import open_reader
from smartdoc.presentation.review_dialog import ReviewDialog
from smartdoc.presentation.theme import current_colors, qt_weight

DEFAULT_ICON_WIDTH = 120
# Height / width of a grid cover: roughly a real paperback (the mockups'
# covers are 105x150 and 163x232).
COVER_ASPECT = 1.42
ICON_SIZE = QSize(DEFAULT_ICON_WIDTH, int(DEFAULT_ICON_WIDTH * COVER_ASPECT))
# Placeholder jackets are painted once at this size and scaled *down* to
# whatever the grid shows -- painting them at the default size and scaling
# up made the text on large covers (Walnut Library's) blurry.
PLACEHOLDER_SIZE = QSize(180, int(180 * COVER_ASPECT))
TABLE_THUMB_SIZE = QSize(32, 46)  # List view's inline cover thumbnail, on the title column
DocumentRole = Qt.UserRole + 1
LIBRARY_RELOAD_DEBOUNCE_MS = 300
PAGE_SIZE = 100

# Sort dropdown options -> trusted ORDER BY fragments (see
# DatabaseManager.query_documents's order_by docstring on why this must stay
# a fixed whitelist rather than ever being built from user text).
SORT_OPTIONS: dict[str, str] = {
    "Ngày thêm (mới nhất)": "documents.created_at DESC",
    "Tiêu đề (A-Z)": "documents.title ASC",
    "Tác giả (A-Z)": "documents.author ASC",
    "Kích thước file (lớn nhất)": "documents.file_size DESC",
    "Được đánh giá cao nhất": "documents.avg_rating DESC",
}

# Selecting this one specifically triggers a background Supabase sync of
# cached rating stats first (see toolbar.py) -- every other sort option
# only ever touches the local SQLite index.
HIGHEST_RATED_SORT_LABEL = "Được đánh giá cao nhất"


_BADGE_FONT_HEIGHT_RATIO = 0.075  # font height = 7.5% of the cover's own height
_BADGE_MIN_FONT_PX = 7  # a tiny placeholder cover would otherwise round down to unreadable
_BADGE_MARGIN_RATIO = 0.035  # distance from the corner, as a fraction of the cover's height
# Space a placeholder jacket keeps free along its bottom edge for the badge
# (fraction of the cover's height) so the title/author never run under it.
BADGE_JACKET_RESERVE = 0.10
# No background plate behind the label -- it sits directly on the cover art.
# Instead the letters are solid (fully opaque) and wrapped in a thin outline
# of the opposite tone, which keeps them crisp and legible on any cover,
# light or dark, without a box competing with the artwork.
_BADGE_FG = QColor(255, 255, 255)
_BADGE_OUTLINE = QColor(0, 0, 0, 230)


def _badge_font_px(cover_height: int) -> int:
    return max(_BADGE_MIN_FONT_PX, round(cover_height * _BADGE_FONT_HEIGHT_RATIO))


def _with_format_badge(pixmap: QPixmap, extension: str) -> QPixmap:
    """Stamps a small "PDF"/"EPUB" label at the bottom-right corner of a
    grid cover thumbnail (the top-right carries the reading-list star, and
    a placeholder jacket's title/author sit bottom-left): solid, outlined
    letters with no plate behind them, enough to tell formats apart
    without opening anything.

    The badge is stamped directly onto the source pixmap (not drawn
    separately by the view), and the view then scales that whole icon to
    whatever the current grid cover size is -- so sizing the font as a
    fraction of *this* pixmap's height, rather than a fixed pixel size,
    keeps the badge proportionally the same size relative to the cover at
    any cover-size setting instead of looking tiny on large covers.
    """
    if not extension:
        return pixmap
    label = extension.upper()
    badged = QPixmap(pixmap)
    painter = QPainter(badged)
    painter.setRenderHint(QPainter.Antialiasing)
    painter.setRenderHint(QPainter.TextAntialiasing)
    font = QFont()
    font_px = _badge_font_px(badged.height())
    font.setPixelSize(font_px)
    font.setBold(True)
    metrics = QFontMetrics(font)
    margin = max(3, round(badged.height() * _BADGE_MARGIN_RATIO))
    x = badged.width() - margin - metrics.horizontalAdvance(label)
    baseline = badged.height() - margin - metrics.descent()

    foreground, outline = _BADGE_FG, _BADGE_OUTLINE
    if not _is_light(current_colors().cover_text_color):
        # Themes with light (pastel) placeholder covers print dark text on
        # them -- the badge follows, with a light outline instead of a dark one.
        ink = QColor(current_colors().cover_text_color)
        foreground, outline = ink, QColor(255, 255, 255, 230)

    path = QPainterPath()
    path.addText(x, baseline, font, label)
    painter.setPen(QPen(outline, max(1.5, font_px * 0.16), Qt.SolidLine, Qt.RoundCap, Qt.RoundJoin))
    painter.drawPath(path)  # the outline first...
    painter.setPen(Qt.NoPen)
    painter.setBrush(foreground)
    painter.drawPath(path)  # ...then the solid letters on top of it
    painter.end()
    return badged


# Character-based, not pixel-based (that would need a QFontMetrics call
# inside the model, awkward to keep in sync with the current font/DPI) --
# a conservative cap that keeps a two-line title+author label from
# expanding a grid cell taller than its neighbors, so every cover in the
# grid stays aligned to the same row/column grid rather than however tall
# its own text happens to wrap.
_TITLE_MAX_CHARS = 42
_AUTHOR_MAX_CHARS = 30


def _truncate(text: str, max_chars: int) -> str:
    text = text or ""
    if len(text) <= max_chars:
        return text
    return text[: max_chars - 1].rstrip() + "…"


def _content_font(config) -> QFont:
    """The document-content font (library titles/authors, detail panel) --
    kept separate from the app's own chrome font (see AppConfig's
    docstring on content_font_family)."""
    font = QFont(config.content_font_family) if config.content_font_family else QFont()
    font.setPointSize(config.content_font_size)
    return font


def _content_color(config) -> QColor | None:
    return QColor(config.content_text_color) if config.content_text_color else None


class _AsyncCoverMixin:
    """Cover icons for a model, decoded off the GUI thread (see
    cover_loader.py). data() never blocks on disk: a cover that isn't
    decoded yet shows its gradient placeholder, the loader is asked for the
    real image, and the row is repainted when it arrives.

    Subclasses provide `_documents` and `_build_cover_icon(pixmap, doc)`
    (how a decoded pixmap becomes the icon that view shows), plus
    `_cover_key_suffix(doc)` -- the part of the cache key beyond the cover
    itself (the grid's badge depends on the extension; the list's
    thumbnail doesn't).
    """

    _PLACEHOLDER_SIZE = ICON_SIZE
    # Whether the placeholder jacket carries the title/author (the grid's
    # full-size covers) or is just the gradient (the List view's thumbnails).
    _PLACEHOLDER_TEXT = False

    def _init_async_covers(self) -> None:
        self._icon_cache: dict[tuple[str | None, str], QIcon] = {}
        self._placeholder_cache: dict[tuple[str | None, str], QIcon] = {}
        self._failed_covers: set[str] = set()
        self._cover_stamps: dict[str, tuple[int, int] | None] = {}  # cover path -> (mtime, size) last seen
        self._rows_by_cover: dict[str, list[int]] = {}
        self._cover_loader = CoverLoader(self)
        self._cover_loader.loaded.connect(self._on_cover_loaded)

    def _index_covers(self) -> None:
        """Call whenever _documents is replaced: maps each cover back to the
        rows showing it, drops decode requests for the old rows, and forgets
        the decoded icon of any cover file that changed on disk."""
        self._rows_by_cover = {}
        for row, doc in enumerate(self._documents):
            cover_path = doc.get("cover_path")
            if cover_path:
                self._rows_by_cover.setdefault(cover_path, []).append(row)
        self._cover_loader.cancel_pending()
        self._evict_replaced_covers()

    def _evict_replaced_covers(self) -> None:
        """A cover is saved as <doc_id>.webp, so choosing a new cover for a book rewrites the *same path*: the
        icon caches (keyed by path) would go on showing the old picture until the app restarted. The file's
        modification time and size tell a replaced cover apart; only that path is evicted, so every other
        document keeps its decoded icon. Runs once per reload (a stat per visible cover), never in data()."""
        for cover_path in self._rows_by_cover:
            try:
                stat = os.stat(cover_path)
                stamp: tuple[int, int] | None = (stat.st_mtime_ns, stat.st_size)
            except OSError:
                stamp = None
            known = self._cover_stamps.get(cover_path, stamp)
            self._cover_stamps[cover_path] = stamp
            if stamp == known:
                continue
            self._failed_covers.discard(cover_path)
            for cache in (self._icon_cache, self._placeholder_cache):
                for key in [k for k in cache if k[0] == cover_path]:
                    del cache[key]

    def _cover_decoration(self, doc: dict) -> QIcon:
        cover_path = doc.get("cover_path")
        # When there's no real cover, the doc_id stands in for cover_path in
        # the key instead of every coverless document collapsing onto one
        # shared entry -- the gradient placeholder is chosen per doc_id (see
        # cover_placeholder.gradient_pixmap), so each needs its own slot.
        key = (cover_path or doc.get("id"), self._cover_key_suffix(doc))
        icon = self._icon_cache.get(key)
        if icon is not None:
            return icon

        if cover_path and cover_path not in self._failed_covers:
            self._cover_loader.request(cover_path)
            placeholder = self._placeholder_cache.get(key)
            if placeholder is None:
                placeholder = self._build_cover_icon(self._gradient_for(doc), doc)
                self._placeholder_cache[key] = placeholder
            return placeholder

        icon = self._build_cover_icon(self._gradient_for(doc), doc)
        self._icon_cache[key] = icon
        return icon

    def _gradient_for(self, doc: dict) -> QPixmap:
        if not self._PLACEHOLDER_TEXT:
            return gradient_pixmap(doc.get("id", ""), self._PLACEHOLDER_SIZE, current_colors())
        return gradient_pixmap(
            doc.get("id", ""),
            self._PLACEHOLDER_SIZE,
            current_colors(),
            title=doc.get("title") or "",
            author=doc.get("author") or "",
            bottom_reserve=BADGE_JACKET_RESERVE if doc.get("extension") else 0.0,
        )

    def _on_cover_loaded(self, cover_path: str, image) -> None:
        if image.isNull():
            # Missing/corrupt file: settle on the placeholder for good
            # rather than retrying it on every repaint.
            self._failed_covers.add(cover_path)
        for row in self._rows_by_cover.get(cover_path, []):
            if row >= len(self._documents):
                continue
            doc = self._documents[row]
            pixmap = QPixmap.fromImage(image) if not image.isNull() else self._gradient_for(doc)
            key = (cover_path, self._cover_key_suffix(doc))
            self._icon_cache[key] = self._build_cover_icon(pixmap, doc)
            self._placeholder_cache.pop(key, None)
            index = self.index(row, 0)
            self.dataChanged.emit(index, index, [Qt.DecorationRole])


class LibraryModel(_AsyncCoverMixin, QAbstractListModel):
    _PLACEHOLDER_TEXT = True
    _PLACEHOLDER_SIZE = PLACEHOLDER_SIZE

    def __init__(self, parent=None, *, context=None) -> None:
        super().__init__(parent)
        self._context = context
        self._documents: list[dict] = []
        self._init_async_covers()

    def set_documents(self, documents: list[dict]) -> None:
        self.beginResetModel()
        self._documents = documents
        self._index_covers()
        self.endResetModel()

    def _cover_key_suffix(self, doc: dict) -> str:
        # The format badge is stamped onto the pixmap itself, so the same
        # cover under two extensions needs two cache entries.
        return doc.get("extension", "")

    def _build_cover_icon(self, pixmap: QPixmap, doc: dict) -> QIcon:
        return QIcon(_with_format_badge(pixmap, doc.get("extension", "")))

    def document_at(self, row: int) -> dict | None:
        if 0 <= row < len(self._documents):
            return self._documents[row]
        return None

    def rowCount(self, parent: QModelIndex = QModelIndex()) -> int:  # noqa: B008
        return 0 if parent.isValid() else len(self._documents)

    def data(self, index: QModelIndex, role: int = Qt.DisplayRole):
        if not index.isValid():
            return None
        doc = self._documents[index.row()]
        if role == Qt.DisplayRole:
            title = _truncate(doc.get("title", ""), _TITLE_MAX_CHARS)
            author = _truncate(doc.get("author", ""), _AUTHOR_MAX_CHARS)
            return f"{title}\n{author}"
        if role == Qt.DecorationRole:
            return self._cover_decoration(doc)
        if role == Qt.FontRole and self._context:
            return _content_font(self._context.config.config)
        if role == Qt.ForegroundRole and self._context:
            color = _content_color(self._context.config.config)
            if color is not None:
                return color
        if role == DocumentRole:
            return doc
        return None


# (column key, header label). "title" is mandatory and always the first
# column; the rest are optional, user-chosen (right-click the list view's
# header -> see LibraryListWidget._show_column_picker), persisted in
# AppConfig.visible_columns.
COLUMN_DEFS: list[tuple[str, str]] = [
    ("title", "Tiêu đề"),
    ("author", "Tác giả"),
    ("format", "Định dạng"),
    ("file_size", "Dung lượng"),
    ("tags", "Thể loại"),
    ("avg_rating", "Đánh giá TB"),
    ("review_count", "Số đánh giá"),
    ("created_at", "Ngày thêm"),
    ("updated_at", "Ngày chỉnh sửa"),
]
_COLUMN_LABELS = dict(COLUMN_DEFS)
OPTIONAL_COLUMN_KEYS = [key for key, _label in COLUMN_DEFS if key != "title"]

# Sizing for the list view's columns (see LibraryListWidget._apply_column_widths).
# Title always stretches to fill whatever width is left, so the table spans
# the full viewport with no dead gutter on the right. Short, fixed-shape
# columns are sized to a sample of their widest realistic value in the
# current font (so a bigger font setting doesn't clip dates); free-text
# columns get a sensible fixed start width. All non-title columns stay
# user-resizable.
_COLUMN_WIDTH_SAMPLES = {
    "format": "AZW3",
    "file_size": "999.9 MB",
    "avg_rating": "4.5 ★",
    "review_count": "9999",
    "created_at": "31/12/2026 23:59",
    "updated_at": "31/12/2026 23:59",
}
_COLUMN_FIXED_WIDTHS = {"author": 190, "tags": 170}
_COLUMN_PADDING = 28
_COLUMN_ALIGNMENT = {
    "format": Qt.AlignCenter,
    "file_size": Qt.AlignRight | Qt.AlignVCenter,
    "avg_rating": Qt.AlignCenter,
    "review_count": Qt.AlignCenter,
    "created_at": Qt.AlignCenter,
    "updated_at": Qt.AlignCenter,
}


def _format_datetime(value) -> str:
    if not value:
        return "—"
    try:
        return datetime.fromtimestamp(value).strftime("%d/%m/%Y %H:%M")
    except (TypeError, ValueError, OSError):
        return "—"


def _format_cell(doc: dict, key: str) -> str:
    if key == "title":
        return doc.get("title", "")
    if key == "author":
        return doc.get("author", "") or "—"
    if key == "format":
        return (doc.get("extension") or "").upper() or "—"
    if key == "file_size":
        return human_size(doc.get("file_size", 0))
    if key == "tags":
        return doc.get("tags", "") or "—"
    if key == "avg_rating":
        value = doc.get("avg_rating")
        return f"{value:.1f} ★" if value is not None else "—"
    if key == "review_count":
        return str(doc.get("review_count") or 0)
    if key in ("created_at", "updated_at"):
        return _format_datetime(doc.get(key))
    return ""


_STAR_SIZE = 20
_STAR_ON = "#f5b301"


class _StarToggleMixin:
    """A ★ on every document that files it into (or out of) the built-in
    "Sẽ đọc" reading list in one click -- the grid draws it on the cover's
    corner, the list at the end of the title cell.

    Painted by the delegate rather than baked into the cover icon, so
    starring a book never invalidates the model's (expensive) icon cache.
    Presses inside the star are consumed, so starring doesn't also change
    the selection or, on a double click, open the reader.
    """

    def _init_star(self, is_starred, on_toggle) -> None:
        self._is_starred = is_starred
        self._on_toggle = on_toggle

    def _star_rect(self, option, index) -> QRect | None:  # overridden per view
        return None

    def _paint_star(self, painter, option, index) -> None:
        rect = self._star_rect(option, index)
        doc = index.data(DocumentRole)
        if rect is None or not doc:
            return
        starred = self._is_starred(doc.get("id"))
        painter.save()
        painter.setRenderHint(QPainter.Antialiasing)
        # A soft dark disc behind the glyph keeps it legible over any cover.
        painter.setPen(Qt.NoPen)
        painter.setBrush(QColor(0, 0, 0, 110 if starred else 70))
        painter.drawEllipse(rect)
        font = QFont()
        font.setPixelSize(int(rect.height() * 0.75))
        painter.setFont(font)
        painter.setPen(QColor(_STAR_ON) if starred else QColor(255, 255, 255, 200))
        painter.drawText(rect, Qt.AlignCenter, "★" if starred else "☆")
        painter.restore()

    def editorEvent(self, event, model, option, index) -> bool:  # noqa: N802 -- Qt override
        if event.type() in (QEvent.MouseButtonPress, QEvent.MouseButtonRelease, QEvent.MouseButtonDblClick):
            rect = self._star_rect(option, index)
            if rect is not None and rect.contains(event.position().toPoint()):
                if event.type() == QEvent.MouseButtonRelease and event.button() == Qt.LeftButton:
                    doc = index.data(DocumentRole)
                    if doc:
                        self._on_toggle(doc.get("id"))
                return True
        return super().editorEvent(event, model, option, index)


_CARD_PAD = 6  # inside each grid cell, above the cover
_CARD_TEXT_GAP = 8  # cover -> title
_CARD_TITLE_LINES = 2
_CARD_GUTTER = 24  # horizontal space between neighbouring cards


def _card_fonts(config) -> tuple[QFont, QFont]:
    # Pixel sizes, read the same way the detail panel reads
    # content_font_size (see detail_panel._content_font_css) -- as points
    # the card titles came out a third larger than everything around them.
    colors = current_colors()
    title_font = _content_font(config) if config is not None else QFont()
    size = config.content_font_size if config is not None else 13
    title_font.setPixelSize(max(9, size))
    title_font.setWeight(qt_weight(colors.card_title_weight))
    author_font = QFont(title_font)
    author_font.setWeight(qt_weight(min(colors.font_weight, 400)))
    author_font.setPixelSize(max(8, round(size * 0.9)))
    return title_font, author_font


def card_text_height(config) -> int:
    """Height of the title (up to two lines) + author block under a grid
    cover -- what the grid cell has to leave room for."""
    title_font, author_font = _card_fonts(config)
    title_metrics, author_metrics = QFontMetrics(title_font), QFontMetrics(author_font)
    return _CARD_TEXT_GAP + title_metrics.lineSpacing() * _CARD_TITLE_LINES + 4 + author_metrics.height()


def _wrap_lines(text: str, font: QFont, width: int, max_lines: int) -> list[str]:
    """`text` word-wrapped to `width` px, at most `max_lines` lines, the
    last one elided with "..." if the text runs over."""
    layout = QTextLayout(text, font)
    layout.beginLayout()
    spans = []
    while True:
        line = layout.createLine()
        if not line.isValid():
            break
        line.setLineWidth(width)
        spans.append((line.textStart(), line.textLength()))
    layout.endLayout()
    lines = [text[start : start + length].strip() for start, length in spans[:max_lines]]
    if len(spans) > max_lines and lines:
        rest = text[spans[max_lines - 1][0] :].strip()
        lines[-1] = QFontMetrics(font).elidedText(rest, Qt.ElideRight, width)
    return lines


class _GridStarDelegate(_StarToggleMixin, QStyledItemDelegate):
    """Paints each grid cell as a book card: the cover (with a soft drop
    shadow, cropped to one uniform shape so the shelf lines up), the title
    underneath in up to two lines, the author in a muted line below it. A
    selected card gets an accent outline around its cover and accent-coloured
    text, instead of a filled highlight block over the whole cell. The
    reading-list star sits in the cover's top-right corner."""

    _SCALED_CACHE_LIMIT = 400

    def __init__(self, parent, is_starred, on_toggle, config=None) -> None:
        super().__init__(parent)
        self._init_star(is_starred, on_toggle)
        self._config = config
        self._scaled: dict[tuple[int, int, int], QPixmap] = {}
        # Fades for themes with motion (ThemeColors.motion_ms): per
        # (doc id, "hover"/"select") -> (active, start time, start value).
        self._fades: dict[tuple[str, str], tuple[bool, float, float]] = {}
        self._fade_timer = QTimer(self)
        self._fade_timer.setInterval(16)
        self._fade_timer.timeout.connect(self._on_fade_tick)

    def _on_fade_tick(self) -> None:
        view = self.parent()
        if view is not None and hasattr(view, "viewport"):
            view.viewport().update()
        if not self._fades:
            self._fade_timer.stop()

    def _fade(self, key: tuple[str, str], active: bool, duration_ms: int) -> float:
        """0..1 eased progress of `key` towards `active` -- the Qt stand-in
        for a CSS `transition: all .5s ease` (Qt Widgets has none)."""
        if duration_ms <= 0:
            return 1.0 if active else 0.0
        now = time.monotonic()
        state = self._fades.get(key)
        if state is None and not active:
            return 0.0
        if state is None or state[0] != active:
            start = self._fade_value(state, now, duration_ms) if state else 0.0
            state = (active, now, start)
            self._fades[key] = state
        value = self._fade_value(state, now, duration_ms)
        target = 1.0 if active else 0.0
        if value == target:
            if not active:
                self._fades.pop(key, None)
        elif not self._fade_timer.isActive():
            self._fade_timer.start()
        return value

    @staticmethod
    def _fade_value(state, now: float, duration_ms: int) -> float:
        active, started, start_value = state
        t = min(1.0, (now - started) * 1000.0 / duration_ms)
        eased = t * t * (3 - 2 * t)  # smoothstep "ease"
        target = 1.0 if active else 0.0
        return start_value + (target - start_value) * eased

    @staticmethod
    def _cover_rect(option) -> QRect:
        size = option.decorationSize
        rect = option.rect
        x = rect.x() + (rect.width() - size.width()) // 2  # centred, so the gutters stay even
        return QRect(x, rect.y() + _CARD_PAD, size.width(), size.height())

    def _star_rect(self, option, index) -> QRect | None:
        opt = QStyleOptionViewItem(option)
        self.initStyleOption(opt, index)
        if opt.decorationSize.isEmpty():
            return None
        cover = self._cover_rect(opt)
        return QRect(cover.right() - _STAR_SIZE - 3, cover.top() + 3, _STAR_SIZE, _STAR_SIZE)

    def _cover_pixmap(self, icon: QIcon, size: QSize) -> QPixmap:
        """The cover scaled to fill `size` exactly (cropping the overflow),
        cached -- smooth-scaling every visible cover on every repaint would
        make scrolling stutter."""
        sizes = icon.availableSizes()
        source = icon.pixmap(sizes[0]) if sizes else icon.pixmap(size)
        key = (source.cacheKey(), size.width(), size.height())
        cached = self._scaled.get(key)
        if cached is not None:
            return cached
        scaled = source.scaled(size, Qt.KeepAspectRatioByExpanding, Qt.SmoothTransformation)
        if scaled.size() != size:
            scaled = scaled.copy(
                (scaled.width() - size.width()) // 2, (scaled.height() - size.height()) // 2, size.width(), size.height()
            )
        if len(self._scaled) >= self._SCALED_CACHE_LIMIT:
            self._scaled.clear()
        self._scaled[key] = scaled
        return scaled

    def paint(self, painter, option, index) -> None:
        opt = QStyleOptionViewItem(option)
        self.initStyleOption(opt, index)
        doc = index.data(DocumentRole) or {}
        colors = current_colors()
        selected = bool(opt.state & QStyle.State_Selected)
        cover = self._cover_rect(opt)

        painter.save()
        painter.setRenderHint(QPainter.Antialiasing)
        painter.setRenderHint(QPainter.SmoothPixmapTransform)

        radius = colors.cover_radius
        doc_key = str(doc.get("id") or index.row())
        hovered = bool(opt.state & QStyle.State_MouseOver)
        hover_level = self._fade((doc_key, "hover"), hovered and not selected, colors.motion_ms) if colors.motion_ms else 0.0
        select_level = self._fade((doc_key, "select"), selected, colors.motion_ms)

        painter.setPen(Qt.NoPen)
        if colors.cover_shadow == "soft":
            # Soft drop shadow: a few stacked translucent rounded rects.
            for spread, alpha in ((3, 10), (2, 16), (1, 26)):
                painter.setBrush(QColor(0, 0, 0, alpha))
                painter.drawRoundedRect(
                    cover.adjusted(-spread + 1, -spread + 2, spread - 1, spread + 2), radius + 1, radius + 1
                )
        elif colors.cover_shadow == "warm":
            # A lifted, warm-brown shadow (~0 6px 16px rgba(107,85,64,.18)).
            for spread, alpha in ((8, 6), (6, 9), (4, 12), (2, 16)):
                painter.setBrush(QColor(107, 85, 64, alpha))
                painter.drawRoundedRect(
                    cover.adjusted(-spread + 2, -spread + 6, spread - 2, spread + 6), radius + spread, radius + spread
                )

        glow_level = max(select_level if colors.card_selection == "glow" else 0.0, hover_level * 0.5)
        if glow_level > 0:
            _paint_glow(painter, QRectF(cover), radius, QColor(colors.accent), glow_level)

        icon = index.data(Qt.DecorationRole)
        clip = QPainterPath()
        clip.addRoundedRect(QRectF(cover), radius, radius)
        painter.save()
        painter.setClipPath(clip)
        if isinstance(icon, QIcon) and not icon.isNull():
            painter.drawPixmap(cover.topLeft(), self._cover_pixmap(icon, cover.size()))
        else:
            painter.fillRect(cover, QColor(colors.border))
        painter.restore()

        if colors.cover_border_color:
            painter.setPen(QPen(QColor(colors.cover_border_color), 1))
            painter.setBrush(Qt.NoBrush)
            painter.drawRoundedRect(QRectF(cover).adjusted(0.5, 0.5, -0.5, -0.5), radius, radius)

        if select_level > 0:
            ring = QColor(colors.accent)
            ring.setAlphaF(select_level)
            pen = QPen(ring)
            width = colors.card_outline_width
            pen.setWidth(width)
            painter.setPen(pen)
            painter.setBrush(Qt.NoBrush)
            grow = width if colors.card_selection == "outline" else 0
            painter.drawRoundedRect(QRectF(cover).adjusted(-grow, -grow, grow, grow), radius + 1, radius + 1)

        # Title (up to two lines) and author, left-aligned under the cover.
        title_font, author_font = _card_fonts(self._config)
        custom = _content_color(self._config) if self._config is not None else None
        title_color = QColor(colors.accent) if selected else (custom or QColor(colors.text))
        author_color = QColor(colors.accent) if selected else QColor(colors.muted_text)
        text_left = cover.left()
        text_width = max(10, opt.rect.right() - text_left - 4)
        y = cover.bottom() + _CARD_TEXT_GAP

        title_metrics = QFontMetrics(title_font)
        painter.setFont(title_font)
        glow_text = colors.text_glow and select_level > 0
        for line in _wrap_lines(doc.get("title") or "", title_font, text_width, _CARD_TITLE_LINES):
            line_rect = QRect(text_left, y, text_width, title_metrics.lineSpacing())
            if glow_text:
                # ~text-shadow: 0 0 10px accent -- a faint halo drawn around the glyphs.
                halo = QColor(colors.accent)
                halo.setAlphaF(0.22 * select_level)
                painter.setPen(halo)
                for dx, dy in ((-1, 0), (1, 0), (0, -1), (0, 1)):
                    painter.drawText(line_rect.translated(dx, dy), Qt.AlignLeft | Qt.AlignVCenter, line)
            painter.setPen(title_color)
            painter.drawText(line_rect, Qt.AlignLeft | Qt.AlignVCenter, line)
            y += title_metrics.lineSpacing()

        author = doc.get("author") or ""
        if author:
            author_metrics = QFontMetrics(author_font)
            painter.setFont(author_font)
            painter.setPen(author_color)
            painter.drawText(
                QRect(text_left, y + 4, text_width, author_metrics.height()),
                Qt.AlignLeft | Qt.AlignVCenter,
                author_metrics.elidedText(author, Qt.ElideRight, text_width),
            )
        painter.restore()
        self._paint_star(painter, option, index)


class _ThemedRowDelegate(_StarToggleMixin, QStyledItemDelegate):
    """Paints the shared "selected item" look (theme.py's selected_bg +
    a selected_border-colored left stripe + selected_text) for the List
    view's rows -- plain QSS can't target a left-border-only accent per
    selected row in a QTableView the way sidebar.py's QListWidget QSS can
    for its own items, so this paints it directly instead. Also carries the
    reading-list ★ at the end of the title cell (when wired up)."""

    _BORDER_WIDTH = 3

    def __init__(self, parent, is_starred=None, on_toggle=None) -> None:
        super().__init__(parent)
        self._init_star(is_starred, on_toggle)

    def _star_rect(self, option, index) -> QRect | None:
        if self._is_starred is None or index.column() != 0:  # title is always column 0
            return None
        rect = option.rect
        return QRect(rect.right() - _STAR_SIZE - 6, rect.center().y() - _STAR_SIZE // 2, _STAR_SIZE, _STAR_SIZE)

    def paint(self, painter, option, index) -> None:
        colors = current_colors()
        option = QStyleOptionViewItem(option)
        if option.state & QStyle.State_Selected:
            painter.save()
            painter.fillRect(option.rect, QColor(colors.selected_bg))
            painter.fillRect(
                option.rect.x(), option.rect.y(), self._BORDER_WIDTH, option.rect.height(), QColor(colors.selected_border)
            )
            painter.restore()
            # QPalette.Text is an enum on the class: PySide6 has no such attribute on an
            # instance, and painting raised (repeatedly) as soon as a row got selected.
            option.palette.setColor(QPalette.Text, QColor(colors.selected_text))
            # The native style would otherwise also paint its own solid
            # Highlight fill on top of what was just drawn above -- clearing
            # the selected state here means only this delegate's own look
            # (the tint + stripe above) ends up on screen.
            option.state &= ~QStyle.State_Selected
        super().paint(painter, option, index)
        self._paint_star(painter, option, index)


class LibraryTableModel(_AsyncCoverMixin, QAbstractTableModel):
    """Backs the List view's QTableView -- a proper multi-column table,
    unlike QListView's ListMode (still just one column of icon+text). Grid
    mode's LibraryModel above and this model are kept showing the same
    document list (see LibraryListWidget.reload()), just rendered two
    different ways.
    """

    def __init__(self, parent=None, *, context=None) -> None:
        super().__init__(parent)
        self._context = context
        self._documents: list[dict] = []
        self._columns: list[str] = ["title", *OPTIONAL_COLUMN_KEYS]
        self._init_async_covers()

    def set_documents(self, documents: list[dict]) -> None:
        self.beginResetModel()
        self._documents = documents
        self._index_covers()
        self.endResetModel()

    def set_visible_columns(self, optional_keys: list[str]) -> None:
        self.beginResetModel()
        self._columns = ["title", *[k for k in optional_keys if k in OPTIONAL_COLUMN_KEYS]]
        self.endResetModel()

    def visible_optional_columns(self) -> list[str]:
        return [key for key in self._columns if key != "title"]

    def column_keys(self) -> list[str]:
        return list(self._columns)

    _PLACEHOLDER_SIZE = TABLE_THUMB_SIZE

    def _cover_key_suffix(self, doc: dict) -> str:
        return ""

    def _build_cover_icon(self, pixmap: QPixmap, doc: dict) -> QIcon:
        # No format badge here (unlike the grid's cover icon) -- the
        # Format column already spells that out in text, and a badge would
        # be unreadable at this thumbnail's 32px width anyway.
        if pixmap.size() != TABLE_THUMB_SIZE:
            pixmap = pixmap.scaled(TABLE_THUMB_SIZE, Qt.KeepAspectRatio, Qt.SmoothTransformation)
        return QIcon(pixmap)

    def _cover_icon(self, doc: dict) -> QIcon:
        return self._cover_decoration(doc)

    def document_at(self, row: int) -> dict | None:
        if 0 <= row < len(self._documents):
            return self._documents[row]
        return None

    def rowCount(self, parent: QModelIndex = QModelIndex()) -> int:  # noqa: B008
        return 0 if parent.isValid() else len(self._documents)

    def columnCount(self, parent: QModelIndex = QModelIndex()) -> int:  # noqa: B008
        return 0 if parent.isValid() else len(self._columns)

    def headerData(self, section: int, orientation: Qt.Orientation, role: int = Qt.DisplayRole):
        if orientation != Qt.Horizontal or not 0 <= section < len(self._columns):
            return None
        key = self._columns[section]
        if role == Qt.DisplayRole:
            return _COLUMN_LABELS[key]
        if role == Qt.TextAlignmentRole:
            # Header text lines up with its column's cells.
            return int(_COLUMN_ALIGNMENT.get(key, Qt.AlignLeft | Qt.AlignVCenter))
        return None

    def data(self, index: QModelIndex, role: int = Qt.DisplayRole):
        if not index.isValid():
            return None
        doc = self._documents[index.row()]
        column_key = self._columns[index.column()]
        if role == Qt.DisplayRole:
            return _format_cell(doc, column_key)
        if role == Qt.DecorationRole and column_key == "title":
            return self._cover_icon(doc)
        if role == Qt.TextAlignmentRole and column_key in _COLUMN_ALIGNMENT:
            return int(_COLUMN_ALIGNMENT[column_key])
        if role == Qt.FontRole and self._context:
            return _content_font(self._context.config.config)
        if role == Qt.ForegroundRole and self._context:
            color = _content_color(self._context.config.config)
            if color is not None:
                return color
        if role == DocumentRole:
            return doc
        return None


class LibraryListWidget(QWidget):
    # "Phân loại thông minh" from the right-click menu: the ids of the selected documents.
    smart_classify_requested = Signal(list)

    def __init__(self, context, parent=None, import_manager=None) -> None:
        super().__init__(parent)
        self.context = context
        self.import_manager = import_manager  # only needed for paste_files()
        self.file_actions = FileActionEngine(context)
        self._current_page = 0
        self._total_pages = 1
        # None (not a SORT_OPTIONS value) on purpose: it means "let
        # query_documents use its own default", which is relevance rank
        # while a text search is active and newest-first otherwise. Only
        # picking an explicit sort in the toolbar overrides that -- defaulting
        # to e.g. "newest first" here would silently break relevance ranking
        # for every search until the user touched the sort dropdown.
        self._current_sort: str | None = None
        self._grid_icon_width = DEFAULT_ICON_WIDTH
        self._view_mode = "grid"

        self.model = LibraryModel(self, context=context)
        self.list_view = QListView(self)
        self.list_view.setModel(self.model)
        self.list_view.setViewMode(QListView.IconMode)
        self.list_view.setResizeMode(QListView.Adjust)
        self.list_view.setIconSize(ICON_SIZE)
        self.list_view.setSpacing(0)  # the gutters are part of gridSize (see _update_grid_size)
        self.list_view.setFrameShape(QListView.NoFrame)
        colors = current_colors()
        margin = colors.page_margin
        # In the featured layout the page row already carries the top margin
        # (so the grid's first row lines up with the featured cover's top).
        top = 0 if colors.grid_layout == "featured" else margin
        self.list_view.setViewportMargins(margin, top, margin, 8)
        if colors.motion_ms:
            # Hover fades need hover state on every card.
            self.list_view.setMouseTracking(True)
            self.list_view.viewport().setAttribute(Qt.WA_Hover, True)
        self.list_view.setMovement(QListView.Static)
        self.list_view.setWordWrap(True)
        self.list_view.setTextElideMode(Qt.ElideRight)
        # A fixed grid cell size (set in _update_grid_size, below) rather
        # than letting each item size itself off its own text is what
        # actually keeps every cover aligned into even rows/columns
        # regardless of title length; uniform sizes is also a real perf win
        # for QListView since it can skip per-item size hints.
        self.list_view.setUniformItemSizes(True)
        self.list_view.setEditTriggers(QAbstractItemView.NoEditTriggers)
        self.list_view.setSelectionMode(QAbstractItemView.ExtendedSelection)
        self.list_view.setContextMenuPolicy(Qt.CustomContextMenu)
        self.list_view.customContextMenuRequested.connect(self._show_context_menu)
        self.list_view.doubleClicked.connect(self._open_selected)
        # Reading-list stars: one set lookup per painted row, refreshed once
        # per reload() (see _starred_ids) rather than a query per row.
        self._starred_ids: set[str] = set()
        self.list_view.setItemDelegate(
            _GridStarDelegate(self.list_view, self._is_starred, self.toggle_reading_list, context.config.config)
        )
        self._update_grid_size()

        self.table_model = LibraryTableModel(self, context=context)
        self.table_model.set_visible_columns(context.config.config.visible_columns)
        self.table_view = QTableView(self)
        self.table_view.setModel(self.table_model)
        self.table_view.setSelectionBehavior(QAbstractItemView.SelectRows)
        self.table_view.setSelectionMode(QAbstractItemView.ExtendedSelection)
        self.table_view.setEditTriggers(QAbstractItemView.NoEditTriggers)
        # No zebra striping -- the themed selection delegate below (bg tint
        # + left border stripe) is the one "what's highlighted" signal now,
        # matching the design spec's "loại bỏ khung viền/box thừa" (remove
        # excess boxes/borders in favor of whitespace).
        self.table_view.setAlternatingRowColors(False)
        self.table_view.setIconSize(TABLE_THUMB_SIZE)
        self.table_view.verticalHeader().setDefaultSectionSize(TABLE_THUMB_SIZE.height() + 8)
        self.table_view.setItemDelegate(_ThemedRowDelegate(self.table_view, self._is_starred, self.toggle_reading_list))
        self.table_view.verticalHeader().setVisible(False)
        self.table_view.setWordWrap(False)
        self.table_view.setTextElideMode(Qt.ElideRight)
        self.table_view.horizontalHeader().setHighlightSections(False)
        self._apply_column_widths()
        self.table_view.horizontalHeader().setContextMenuPolicy(Qt.CustomContextMenu)
        self.table_view.horizontalHeader().customContextMenuRequested.connect(self._show_column_picker)
        self.table_view.setContextMenuPolicy(Qt.CustomContextMenu)
        self.table_view.customContextMenuRequested.connect(self._show_context_menu)
        self.table_view.doubleClicked.connect(self._open_selected)

        # Asymmetric grid (see featured_book.py): the page's first book shown
        # large beside the grid of the others.
        self.featured_card: FeaturedBookCard | None = None
        self._grid_page: QWidget = self.list_view
        if colors.grid_layout == "featured":
            self.featured_card = FeaturedBookCard(
                self, cover_aspect=COVER_ASPECT, content_font_size=context.config.config.content_font_size
            )
            self.featured_card.clicked.connect(self._on_featured_clicked)
            self.featured_card.double_clicked.connect(lambda doc: open_reader(self.context, doc, self))
            self.featured_card.context_menu_requested.connect(self._on_featured_context_menu)
            page = QWidget(self)
            row = QHBoxLayout(page)
            row.setContentsMargins(margin, margin, 0, 0)
            row.setSpacing(0)
            row.addWidget(self.featured_card, 0, Qt.AlignTop)
            row.addWidget(self.list_view, 1)
            self._grid_page = page

        self.view_stack = QStackedWidget(self)
        self.view_stack.addWidget(self._grid_page)
        self.view_stack.addWidget(self.table_view)

        # Emit DocumentSelectedEvent whenever the user clicks a row in
        # either view so the detail panel can update.
        self.list_view.selectionModel().selectionChanged.connect(
            lambda _sel, _desel: self._on_selection_changed()
        )
        self.table_view.selectionModel().selectionChanged.connect(
            lambda _sel, _desel: self._on_selection_changed()
        )

        self.pagination_bar = self._build_pagination_bar()

        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.addWidget(self.view_stack)
        layout.addWidget(self.pagination_bar)

        # A bulk import fires one LibraryUpdatedEvent per document. Reacting
        # to each one with a full model reset made large imports visibly
        # slower with every additional file, so bursts are coalesced into a
        # single reload shortly after the last event instead.
        self._reload_timer = QTimer(self)
        self._reload_timer.setSingleShot(True)
        self._reload_timer.setInterval(LIBRARY_RELOAD_DEBOUNCE_MS)
        self._reload_timer.timeout.connect(self.reload)

        # Esc in the list = "Xóa lọc" (search text and every chip), like the bar's button.
        self._clear_filter_shortcut = QShortcut(QKeySequence(Qt.Key_Escape), self)
        self._clear_filter_shortcut.setContext(Qt.WidgetWithChildrenShortcut)
        self._clear_filter_shortcut.activated.connect(self.context.filters.clear)

        self._bridge = QtEventBridge(self)
        self._bridge.event_received.connect(self._on_bridged_event)
        self._bridge.subscribe(context.event_bus, LibraryUpdatedEvent)
        self._bridge.subscribe(context.event_bus, FilterChangedEvent)
        self._bridge.subscribe(context.event_bus, SortChangedEvent)
        self._bridge.subscribe(context.event_bus, CoverSizeChangedEvent)
        self._bridge.subscribe(context.event_bus, ViewModeChangedEvent)

        self.reload()

    def _build_pagination_bar(self) -> QWidget:
        bar = QWidget(self)
        row = QHBoxLayout(bar)
        row.setContentsMargins(0, 6, 0, 0)
        row.setSpacing(6)
        colors = current_colors()
        # Flat text arrows and one filled "Đến" button, centred under the
        # grid -- quiet enough not to compete with the covers above.
        bar.setStyleSheet(
            f"QPushButton {{ border: none; background: transparent; color: {colors.muted_text};"
            f" padding: 4px 8px; font-size: 14px; }}"
            f" QPushButton:hover {{ color: {colors.accent}; }}"
            f" QPushButton:disabled {{ color: {colors.border}; }}"
            f" QPushButton#JumpButton {{ background: {colors.accent}; color: {colors.accent_text};"
            f" border-radius: 3px; padding: 4px 12px; font-weight: 600; }}"
            f" QLabel {{ color: {colors.muted_text}; }}"
            # White on light content areas (the original look); the theme's
            # surface on dark ones (Zen, Retro-Tech), where white would glare
            # and the content text color is light.
            f" QSpinBox {{ background: {'#ffffff' if _is_light(colors.content_bg) else colors.surface};"
            f" color: {colors.text}; border: 1px solid {colors.border}; border-radius: {min(colors.control_radius, 6)}px;"
            f" padding: 3px 6px; min-width: 48px; }}"
        )

        self.first_page_button = QPushButton("|<")
        self.prev_page_button = QPushButton("<")
        self.page_label = QLabel("Trang 1 / 1")
        self.next_page_button = QPushButton(">")
        self.last_page_button = QPushButton(">|")
        self.jump_spin = QSpinBox()
        self.jump_spin.setMinimum(1)
        self.jump_spin.setMaximum(1)
        self.jump_button = QPushButton("Đến")
        self.jump_button.setObjectName("JumpButton")
        self.jump_spin.setButtonSymbols(QSpinBox.NoButtons)
        self.jump_spin.setAlignment(Qt.AlignCenter)

        self.first_page_button.clicked.connect(lambda: self._go_to_page(0))
        self.prev_page_button.clicked.connect(lambda: self._go_to_page(self._current_page - 1))
        self.next_page_button.clicked.connect(lambda: self._go_to_page(self._current_page + 1))
        self.last_page_button.clicked.connect(lambda: self._go_to_page(self._total_pages - 1))
        self.jump_button.clicked.connect(lambda: self._go_to_page(self.jump_spin.value() - 1))

        row.addStretch(1)
        row.addWidget(self.first_page_button)
        row.addWidget(self.prev_page_button)
        row.addWidget(self.page_label)
        row.addWidget(self.next_page_button)
        row.addWidget(self.last_page_button)
        row.addSpacing(18)
        row.addWidget(QLabel("Đến:"))
        row.addWidget(self.jump_spin)
        row.addWidget(self.jump_button)
        row.addStretch(1)
        return bar

    def _go_to_page(self, page: int) -> None:
        page = max(0, min(page, self._total_pages - 1))
        if page == self._current_page:
            return
        self._current_page = page
        self.reload()

    def _update_pagination_ui(self, total: int) -> None:
        self.page_label.setText(f"Trang {self._current_page + 1} / {self._total_pages} ({total:,} tài liệu)")
        self.jump_spin.setMaximum(self._total_pages)
        at_first = self._current_page == 0
        at_last = self._current_page >= self._total_pages - 1
        self.first_page_button.setEnabled(not at_first)
        self.prev_page_button.setEnabled(not at_first)
        self.next_page_button.setEnabled(not at_last)
        self.last_page_button.setEnabled(not at_last)

    def set_view_mode(self, mode: str) -> None:
        self._view_mode = mode
        if mode == "list":
            self.view_stack.setCurrentWidget(self.table_view)
        else:
            self.view_stack.setCurrentWidget(self._grid_page)

    def _active_view(self) -> QAbstractItemView:
        return self.table_view if self._view_mode == "list" else self.list_view

    def _active_model(self):
        return self.table_model if self._view_mode == "list" else self.model

    def _grid_icon_size(self) -> QSize:
        return QSize(self._grid_icon_width, int(self._grid_icon_width * COVER_ASPECT))

    def _update_grid_size(self) -> None:
        icon_size = self._grid_icon_size()
        # The cover plus the gutter between cards across; below it the
        # card's two-line title + author block (see _GridStarDelegate) and
        # the gap to the next row.
        # Bigger covers get proportionally wider gutters, so a shelf of
        # large covers doesn't look crammed together.
        gutter = current_colors().card_gutter
        cell_width = icon_size.width() + max(gutter, round(icon_size.width() * 0.2))
        cell_height = _CARD_PAD + icon_size.height() + card_text_height(self.context.config.config) + 18
        self.list_view.setGridSize(QSize(cell_width, cell_height))

    def set_grid_icon_width(self, width: int) -> None:
        # list_view is now a persistent widget (just hidden, not
        # reconfigured, while table_view is the active one in the stack) --
        # always keep it current so switching back to grid mode later shows
        # the right size instead of a stale one from before the last switch.
        self._grid_icon_width = width
        self.list_view.setIconSize(self._grid_icon_size())
        self._update_grid_size()
        if self.featured_card is not None:
            self.featured_card.set_cover_width(width)

    def _is_starred(self, doc_id) -> bool:
        return doc_id in self._starred_ids

    def toggle_reading_list(self, doc_id: str) -> bool:
        """★ button handler: files the document into (or out of) the
        built-in "Sẽ đọc" collection. Updates the local star set and
        repaints straight away -- the sidebar's count catches up via the
        LibraryUpdatedEvent -- so the star flips instantly on click."""
        if not doc_id:
            return False
        starred = self.context.db.toggle_reading_list(doc_id)
        if starred:
            self._starred_ids.add(doc_id)
        else:
            self._starred_ids.discard(doc_id)
        self._active_view().viewport().update()
        self.context.event_bus.publish(LibraryUpdatedEvent())
        return starred

    @property
    def library_filter(self) -> LibraryFilter:
        """What the list is filtered by -- owned by FilterService, never copied here."""
        return self.context.filters.current

    def reload(self) -> None:
        flt = self.library_filter
        where_sql, params = self._build_combined_where(flt)
        query = flt.query
        total = self.context.db.count_documents_matching(fts_query=query, where_sql=where_sql, params=params)
        self._total_pages = max(1, math.ceil(total / PAGE_SIZE))
        self._current_page = min(self._current_page, self._total_pages - 1)

        documents = self.context.db.query_documents(
            fts_query=query,
            where_sql=where_sql,
            params=params,
            limit=PAGE_SIZE,
            offset=self._current_page * PAGE_SIZE,
            order_by=self._current_sort,
        )
        self._starred_ids = self.context.db.reading_list_ids()
        if self.featured_card is not None:
            self.featured_card.set_document(documents[0] if documents else None)
            self.model.set_documents(documents[1:])
        else:
            self.model.set_documents(documents)
        self.table_model.set_documents(documents)
        self._update_pagination_ui(total)

    def _build_combined_where(self, flt: LibraryFilter | None = None) -> tuple[str, tuple]:
        return self.context.db.filter_where(flt or self.library_filter)

    def classification_scope(self) -> ClassifyScope:
        """"The list I am looking at", for the smart-classify button: every
        document matching the current search + sidebar selection, not just the
        page on screen."""
        flt = self.library_filter
        where_sql, params = self._build_combined_where(flt)
        return ClassifyScope(
            fts_query=flt.query,
            where_sql=where_sql,
            params=params,
            description=self._describe_current_list(flt),
        )

    def _describe_current_list(self, flt: LibraryFilter | None = None) -> str:
        names = {row["id"]: row["name"] for row in self.context.db.list_collections()}
        return describe(flt or self.library_filter, names)

    def _request_smart_classify_for(self, docs: list[dict]) -> None:
        ids = [d["id"] for d in docs if d.get("id")]
        if ids:
            self.smart_classify_requested.emit(ids)

    def _on_bridged_event(self, event) -> None:
        if isinstance(event, LibraryUpdatedEvent):
            self._reload_timer.start()
        elif isinstance(event, FilterChangedEvent):
            self._current_page = 0  # the old page may not exist in the new result set
            self.reload()
        elif isinstance(event, SortChangedEvent):
            self._current_sort = event.order_by
            self._current_page = 0
            self.reload()
        elif isinstance(event, CoverSizeChangedEvent):
            self.set_grid_icon_width(event.size)
        elif isinstance(event, ViewModeChangedEvent):
            self.set_view_mode(event.mode)

    def _on_selection_changed(self) -> None:
        view = self._active_view()
        model = self._active_model()
        indexes = view.selectedIndexes()
        # Unique rows (table view emits one index per column per row).
        rows = sorted({idx.row() for idx in indexes})
        if rows and self.featured_card is not None:
            self.featured_card.set_selected(False)
        if not rows and self._featured_selected():
            return  # the featured book is the selection -- see _on_featured_clicked
        if len(rows) == 1:
            doc = model.document_at(rows[0])
            self.context.event_bus.publish(DocumentSelectedEvent(doc=doc))
        else:
            # Nothing selected, or multi-select → clear the detail panel.
            self.context.event_bus.publish(DocumentSelectedEvent(doc=None))

    def _open_selected(self, index: QModelIndex) -> None:
        # Double-click's default action is the in-app reader, not opening
        # externally -- "open with the OS's own app" moved to the
        # right-click menu ("Mở bằng ứng dụng khác").
        doc = self._active_model().document_at(index.row())
        if doc:
            open_reader(self.context, doc, self)

    def _show_context_menu(self, position) -> None:
        view = self._active_view()
        model = self._active_model()
        index = view.indexAt(position)
        if not index.isValid():
            return

        selected_rows = sorted({idx.row() for idx in view.selectedIndexes()})
        if index.row() not in selected_rows:
            # Right-clicking outside the current selection acts on just that item.
            view.setCurrentIndex(index)
            selected_rows = [index.row()]

        docs = [d for d in (model.document_at(row) for row in selected_rows) if d]
        if not docs:
            return

        menu = QMenu(self)
        if len(docs) == 1:
            self._show_single_document_menu(menu, docs[0], position)
        else:
            self._show_multi_document_menu(menu, docs, position)

    def _exec_menu(self, menu: QMenu, position):
        """Thin, plain-Python seam around QMenu.exec().

        Tests patch this method rather than QMenu.exec itself: menu.exec()
        opens a real modal loop that, in an offscreen/headless Qt platform,
        has no way to be dismissed by a simulated click and hangs forever.
        Patching the wrapper avoids ever entering that loop.
        """
        return menu.exec(self._active_view().viewport().mapToGlobal(position))

    def _show_column_picker(self, position) -> None:
        """Right-click the list view's header to toggle which optional
        columns are visible -- Title is always shown and not offered here."""
        menu = QMenu(self)
        actions = {}
        current = set(self.table_model.visible_optional_columns())
        for key in OPTIONAL_COLUMN_KEYS:
            action = menu.addAction(_COLUMN_LABELS[key])
            action.setCheckable(True)
            action.setChecked(key in current)
            actions[action] = key

        chosen = self._exec_menu(menu, self.table_view.horizontalHeader().mapTo(self, position))
        if chosen is None or chosen not in actions:
            return
        toggled_key = actions[chosen]
        new_columns = current ^ {toggled_key}  # symmetric difference: flip just this one
        ordered = [key for key in OPTIONAL_COLUMN_KEYS if key in new_columns]
        self.table_model.set_visible_columns(ordered)
        self._apply_column_widths()
        self.context.config.config.visible_columns = ordered
        self.context.config.save()

    def _apply_column_widths(self) -> None:
        """Title stretches to fill the table; every other column gets a
        width that fits its content (see _COLUMN_WIDTH_SAMPLES). Re-run
        whenever the visible column set changes, since a model reset
        rebuilds the header's sections."""
        header = self.table_view.horizontalHeader()
        header.setStretchLastSection(False)
        header.setMinimumSectionSize(48)
        # Cells render in the content font (LibraryTableModel's FontRole),
        # which is usually larger than the view's own chrome font.
        metrics = QFontMetrics(_content_font(self.context.config.config))
        header_metrics = header.fontMetrics()
        for section, key in enumerate(self.table_model.column_keys()):
            if key == "title":
                header.setSectionResizeMode(section, QHeaderView.Stretch)
                continue
            header.setSectionResizeMode(section, QHeaderView.Interactive)
            label_width = header_metrics.horizontalAdvance(_COLUMN_LABELS[key]) + _COLUMN_PADDING
            if key in _COLUMN_WIDTH_SAMPLES:
                content_width = metrics.horizontalAdvance(_COLUMN_WIDTH_SAMPLES[key]) + _COLUMN_PADDING
            else:
                content_width = _COLUMN_FIXED_WIDTHS.get(key, 120)
            header.resizeSection(section, max(label_width, content_width))

    # Sentinel stored as an action's collection id, meaning "ask for a name
    # and create one" rather than "add to this existing collection".
    NEW_COLLECTION = "__new__"

    def _build_add_to_collection_menu(self, parent_menu: QMenu) -> tuple[QMenu, dict]:
        submenu = QMenu("Thêm vào bộ sưu tập", parent_menu)
        actions: dict = {}
        collections = self.context.db.list_collections()
        for row in collections:
            action = submenu.addAction(row["name"])
            actions[action] = row["id"]
        if collections:
            submenu.addSeparator()
        # Without this, filing a document into a brand-new collection meant
        # leaving the menu, creating the collection in the sidebar, then
        # coming back and starting the whole right-click over.
        new_action = submenu.addAction("➕ Tạo bộ sưu tập mới...")
        actions[new_action] = self.NEW_COLLECTION
        parent_menu.addMenu(submenu)
        return submenu, actions

    def _add_documents_to_collection(self, collection_id: str, doc_ids: list[str]) -> None:
        """Files documents into an existing collection, or into a new one
        the user names on the spot (see NEW_COLLECTION)."""
        if collection_id == self.NEW_COLLECTION:
            name, accepted = QInputDialog.getText(self, "Tạo bộ sưu tập mới", "Tên bộ sưu tập:")
            name = name.strip()
            if not accepted or not name:
                return
            existing = {row["name"].strip().casefold() for row in self.context.db.list_collections()}
            if name.casefold() in existing:
                QMessageBox.warning(
                    self, "Bộ sưu tập đã tồn tại", f"Đã có bộ sưu tập tên \"{name}\". Vui lòng chọn tên khác."
                )
                return
            collection = VirtualCollection(name=name)
            self.context.db.save_collection(
                collection.id, collection.name, collection.to_json(), collection.logic, collection.created_at
            )
            collection_id = collection.id

        self.context.db.add_documents_to_collection(collection_id, doc_ids)
        self.context.event_bus.publish(LibraryUpdatedEvent())

    def _show_single_document_menu(self, menu: QMenu, doc: dict, position) -> None:
        read_action = menu.addAction("Đọc trong ứng dụng")
        open_action = menu.addAction("Mở bằng ứng dụng khác")
        reveal_action = menu.addAction("Mở vị trí file")
        edit_action = menu.addAction("Chỉnh sửa thông tin")
        review_action = menu.addAction("Xem / Viết đánh giá")
        cover_search_action = menu.addAction("Tìm ảnh bìa...")
        metadata_search_action = menu.addAction("🔎 Tìm metadata...")
        ai_summary_action = menu.addAction("🤖 Tóm tắt AI...")
        smart_classify_action = menu.addAction("✨ Phân loại thông minh")
        menu.addSeparator()
        copy_action = menu.addAction("📋 Sao chép")
        cut_action = menu.addAction("✂️ Cắt")
        menu.addSeparator()
        _submenu, collection_actions = self._build_add_to_collection_menu(menu)
        send_ereader_action = menu.addAction("📱 Gửi tới máy đọc sách...")
        menu.addSeparator()
        delete_action = menu.addAction("Xóa khỏi thư viện")

        chosen = self._exec_menu(menu, position)
        if chosen == open_action:
            self.file_actions.open_file(doc["file_path"])
        elif chosen == read_action:
            open_reader(self.context, doc, self)
        elif chosen == reveal_action:
            self.file_actions.show_in_file_manager(doc["file_path"])
        elif chosen == edit_action:
            self._edit_documents([doc])
        elif chosen == review_action:
            ReviewDialog(self.context, doc, self).exec()
        elif chosen == cover_search_action:
            CoverSearchDialog(self.context, doc, self).exec()
        elif chosen == metadata_search_action:
            MetadataSuggestDialog(self.context, doc, self).exec()
        elif chosen == ai_summary_action:
            AISummaryDialog(self.context, doc, self).exec()
        elif chosen == smart_classify_action:
            self._request_smart_classify_for([doc])
        elif chosen == copy_action:
            set_clipboard_files([doc["file_path"]] if doc.get("file_path") else [], cut=False)
        elif chosen == cut_action:
            set_clipboard_files([doc["file_path"]] if doc.get("file_path") else [], cut=True)
        elif chosen == send_ereader_action:
            self.send_selected_to_ereader()
        elif chosen in collection_actions:
            self._add_documents_to_collection(collection_actions[chosen], [doc["id"]])
            self.context.event_bus.publish(LibraryUpdatedEvent())
        elif chosen == delete_action:
            self._delete_documents_with_confirm([doc])

    def _show_multi_document_menu(self, menu: QMenu, docs: list[dict], position) -> None:
        count = len(docs)
        batch_edit_action = menu.addAction(f"Chỉnh sửa hàng loạt ({count} tài liệu)")
        smart_classify_action = menu.addAction(f"✨ Phân loại thông minh ({count} tài liệu)")
        menu.addSeparator()
        copy_action = menu.addAction("📋 Sao chép")
        cut_action = menu.addAction("✂️ Cắt")
        menu.addSeparator()
        _submenu, collection_actions = self._build_add_to_collection_menu(menu)
        send_ereader_action = menu.addAction("📱 Gửi tới máy đọc sách...")
        menu.addSeparator()
        delete_action = menu.addAction(f"Xóa {count} tài liệu khỏi thư viện")

        chosen = self._exec_menu(menu, position)
        if chosen == batch_edit_action:
            self._edit_documents(docs)
        elif chosen == smart_classify_action:
            self._request_smart_classify_for(docs)
        elif chosen == copy_action:
            set_clipboard_files([d["file_path"] for d in docs if d.get("file_path")], cut=False)
        elif chosen == cut_action:
            set_clipboard_files([d["file_path"] for d in docs if d.get("file_path")], cut=True)
        elif chosen == send_ereader_action:
            self.send_selected_to_ereader()
        elif chosen in collection_actions:
            self._add_documents_to_collection(collection_actions[chosen], [d["id"] for d in docs])
            self.context.event_bus.publish(LibraryUpdatedEvent())
        elif chosen == delete_action:
            self._delete_documents_with_confirm(docs)

    def _edit_documents(self, docs: list[dict]) -> None:
        if len(docs) == 1:
            MetadataEditorDialog(self.context, docs[0], self).exec()
        else:
            BatchEditorDialog(self.context, [d["id"] for d in docs], self).exec()

    def _delete_documents_with_confirm(self, docs: list[dict]) -> None:
        if not docs:
            return
        count = len(docs)
        message = (
            f"Xóa \"{docs[0].get('title')}\" khỏi thư viện? (File gốc trên đĩa sẽ không bị xóa.)"
            if count == 1
            else f"Xóa {count} tài liệu đã chọn khỏi thư viện? (File gốc trên đĩa sẽ không bị xóa.)"
        )
        confirm = QMessageBox.question(self, "Xóa khỏi thư viện", message)
        if confirm == QMessageBox.Yes:
            self.file_actions.delete_documents(
                [(d["id"], d.get("file_path")) for d in docs], delete_physical_file=False
            )

    # ── Edit-menu-facing operations (mirror the context menu -- see
    # main_window.py's Edit menu) ────────────────────────────────────

    def _selected_documents(self) -> list[dict]:
        view = self._active_view()
        model = self._active_model()
        rows = sorted({idx.row() for idx in view.selectedIndexes()})
        if not rows and self._featured_selected():
            return [self.featured_card.document()]
        return [d for d in (model.document_at(row) for row in rows) if d]

    def _featured_selected(self) -> bool:
        return (
            self._view_mode != "list"
            and self.featured_card is not None
            and self.featured_card.is_selected()
            and self.featured_card.document() is not None
        )

    def _on_featured_clicked(self, doc: dict) -> None:
        self.list_view.clearSelection()
        self.featured_card.set_selected(True)
        self.context.event_bus.publish(DocumentSelectedEvent(doc=doc))

    def _on_featured_context_menu(self, doc: dict, global_pos) -> None:
        menu = QMenu(self)
        # _exec_menu maps from the grid's viewport, so hand it the same spot
        # in those coordinates.
        self._show_single_document_menu(menu, doc, self.list_view.viewport().mapFromGlobal(global_pos))

    def clear_selection(self) -> None:
        self._active_view().clearSelection()

    def edit_selected(self) -> None:
        docs = self._selected_documents()
        if docs:
            self._edit_documents(docs)

    def delete_selected(self) -> None:
        self._delete_documents_with_confirm(self._selected_documents())

    def copy_selected(self) -> None:
        """Puts the selected documents' file paths on the system
        clipboard, the same way Explorer's own Ctrl+C does -- lets the
        user paste file references into Explorer (or anywhere else) that
        accepts them, not just drag files out."""
        paths = [d["file_path"] for d in self._selected_documents() if d.get("file_path")]
        set_clipboard_files(paths, cut=False)

    def cut_selected(self) -> None:
        paths = [d["file_path"] for d in self._selected_documents() if d.get("file_path")]
        set_clipboard_files(paths, cut=True)

    def paste_files(self) -> None:
        """Imports whatever files/folders are currently on the clipboard --
        works with files copied from Explorer, or cut/copied from this
        app's own library view."""
        if not self.import_manager:
            return
        paths = get_clipboard_file_paths()
        if not paths:
            return
        file_paths = [p for p in paths if Path(p).is_file()]
        folder_paths = [p for p in paths if Path(p).is_dir()]
        if file_paths:
            self.import_manager.add_files(file_paths)
        for folder in folder_paths:
            self.import_manager.scan_folder(folder)

    def send_selected_to_ereader(self) -> None:
        """Copies the selected documents' files into the e-reader's book
        folder (see file_actions.FileActionEngine.send_to_ereader). If no
        folder has been set up yet -- or the previously remembered one is
        no longer there, e.g. a different device is connected now -- asks
        for one and remembers it for next time."""
        paths = [d["file_path"] for d in self._selected_documents() if d.get("file_path")]
        if not paths:
            QMessageBox.information(self, "Gửi tới máy đọc sách", "Chưa chọn tài liệu nào.")
            return

        target = self.context.config.config.ereader_folder_path
        if not target or not Path(target).is_dir():
            target = QFileDialog.getExistingDirectory(self, "Chọn thư mục sách trên máy đọc sách")
            if not target:
                return
            self.context.config.config.ereader_folder_path = target
            self.context.config.save()

        succeeded, failed = self.file_actions.send_to_ereader(paths, target)
        if failed:
            QMessageBox.warning(
                self,
                "Gửi tới máy đọc sách",
                f"Đã gửi {len(succeeded)}/{len(paths)} file tới \"{target}\".\n"
                f"{len(failed)} file gửi thất bại (xem log để biết chi tiết).",
            )
        else:
            QMessageBox.information(
                self, "Gửi tới máy đọc sách", f"Đã gửi {len(succeeded)} file tới \"{target}\"."
            )


if __name__ == "__main__":
    import sys
    import tempfile
    from pathlib import Path

    from PySide6.QtWidgets import QApplication

    from smartdoc.core.app_context import AppContext

    with tempfile.TemporaryDirectory() as tmp:
        context = AppContext.create_in_memory(Path(tmp))
        context.db.add_or_update_document(
            "doc1", {"title": "Demo Book", "author": "Someone", "file_path": __file__, "created_at": 0.0}
        )

        app = QApplication(sys.argv)
        from smartdoc.presentation.theme import apply_light_theme

        apply_light_theme(app)
        widget = LibraryListWidget(context)
        widget.resize(600, 400)
        widget.show()
        sys.exit(app.exec())


def _paint_glow(painter, rect: QRectF, radius: float, color: QColor, level: float) -> None:
    """A soft halo around `rect` -- Qt's stand-in for CSS
    `box-shadow: 0 0 18px <color>`: stacked, expanding, fading outlines."""
    painter.save()
    painter.setBrush(Qt.NoBrush)
    steps = 7
    for i in range(steps, 0, -1):
        halo = QColor(color)
        halo.setAlphaF(max(0.0, min(1.0, level * 0.07 * (steps - i + 1) / steps * 2)))
        pen = QPen(halo)
        pen.setWidthF(2.0)
        painter.setPen(pen)
        grow = i * 2.2
        painter.drawRoundedRect(rect.adjusted(-grow, -grow, grow, grow), radius + grow, radius + grow)
    painter.restore()


def _is_light(hex_color: str) -> bool:
    return QColor(hex_color).lightnessF() > 0.5
