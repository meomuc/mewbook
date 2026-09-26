"""TDD-013 (with the pagination/sort/cover-size Milestone D upgrades applied).

Qt Model/View so the widget cost stays flat regardless of library size —
QListView only ever calls data() for rows currently on screen, no matter
how many documents are loaded into the model. Grouping is not implemented
yet.
"""
from __future__ import annotations

import math
import os
from datetime import datetime
from pathlib import Path

from PySide6.QtCore import (
    QAbstractListModel,
    QAbstractTableModel,
    QEvent,
    QModelIndex,
    QRect,
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
)
from PySide6.QtWidgets import (
    QAbstractItemView,
    QApplication,
    QComboBox,
    QFileDialog,
    QHBoxLayout,
    QHeaderView,
    QInputDialog,
    QLabel,
    QMenu,
    QMessageBox,
    QPushButton,
    QStackedWidget,
    QStyle,
    QStyledItemDelegate,
    QStyleOptionViewItem,
    QTableView,
    QToolButton,
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
from smartdoc.presentation.design_dialog import confirm_danger
from smartdoc.presentation.ereader_dialog import EreaderSendDialog
from smartdoc.presentation.cover_loader import CoverLoader
from smartdoc.presentation.line_icons import line_icon
from smartdoc.presentation.shelf_view import ShelfView
from smartdoc.presentation.theme_manager import theme_manager
from smartdoc.presentation.cover_placeholder import gradient_pixmap
from smartdoc.presentation.cover_search_dialog import CoverSearchDialog
from smartdoc.presentation.file_actions import FileActionEngine
from smartdoc.presentation.format_utils import human_size
from smartdoc.presentation.metadata_editor import BatchEditorDialog, MetadataEditorDialog
from smartdoc.presentation.metadata_suggest_dialog import MetadataSuggestDialog
from smartdoc.presentation.qt_event_bridge import QtEventBridge
from smartdoc.presentation.reader_manager import open_reader
from smartdoc.presentation.review_dialog import open_review_dialog
from smartdoc.presentation.state_view import StateView
from smartdoc.presentation.theme import current_colors

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
PAGE_SIZE = 24  # books per page unless the user chose another size (AppConfig.page_size)
PAGE_SIZES = (12, 24, 48, 96)

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

    _ICON_KB = 160  # about what one decoded cover icon costs in memory

    def _trim_icon_cache(self) -> None:
        """Keeps the decoded covers inside Settings > Hiệu năng > "Bộ nhớ đệm ảnh bìa": the oldest are dropped first and
        simply decoded again when they come back on screen."""
        context = getattr(self, "_context", None)
        megabytes = (context.config.config.cover_cache_mb if context is not None else 0) or 300
        limit = max(60, megabytes * 1024 // self._ICON_KB)
        while len(self._icon_cache) > limit:
            self._icon_cache.pop(next(iter(self._icon_cache)))

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
        self._trim_icon_cache()
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
            self._trim_icon_cache()
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


class ShelfModel(LibraryModel):
    """LibraryModel for the shelf: the icon is the plain cover (ShelfView paints the format chip, star and the
    "no cover" placeholder itself), and `cover_state` says whether a real cover is decoded, still loading, or absent."""

    _EMPTY = None  # a 1x1 transparent pixmap, made on first use (a QPixmap cannot exist before the QApplication)
    _MAX_COVER_H = 480  # a decoded cover is kept at most this tall: a shelf never shows one bigger than ~300 px

    def _cover_key_suffix(self, doc: dict) -> str:
        return ""

    def _build_cover_icon(self, pixmap: QPixmap, doc: dict) -> QIcon:
        if pixmap.height() > self._MAX_COVER_H:
            pixmap = pixmap.scaledToHeight(self._MAX_COVER_H, Qt.SmoothTransformation)
        return QIcon(pixmap)

    def _gradient_for(self, doc: dict) -> QPixmap:
        if ShelfModel._EMPTY is None:
            ShelfModel._EMPTY = QPixmap(1, 1)
            ShelfModel._EMPTY.fill(Qt.transparent)
        return ShelfModel._EMPTY

    def cover_state(self, row: int) -> tuple[str, QPixmap | None]:
        doc = self.document_at(row)
        if doc is None:
            return "none", None
        icon = self._cover_decoration(doc)  # asks the loader for the real image when it is not decoded yet
        path = doc.get("cover_path")
        if not path or path in self._failed_covers:
            return "none", None
        if (path, "") in self._icon_cache:
            sizes = icon.availableSizes()
            return "ready", icon.pixmap(sizes[0]) if sizes else None
        return "loading", None


# (column key, header label). "title" is mandatory and always the first
# column; the rest are optional, user-chosen (right-click the list view's
# header -> see LibraryListWidget._show_column_picker), persisted in
# AppConfig.visible_columns.
COLUMN_DEFS: list[tuple[str, str]] = [
    ("title", "Tên sách"),
    ("author", "Tác giả"),
    ("format", "Định dạng"),
    ("pub_year", "Năm"),
    ("avg_rating", "Đánh giá"),
    ("tags", "Hashtag"),
    ("created_at", "Ngày thêm"),
    ("file_size", "Dung lượng"),
    ("review_count", "Số đánh giá"),
    ("updated_at", "Ngày sửa"),
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
    "avg_rating": "★ 4,5",
    "pub_year": "2026",
    "review_count": "9999",
    "created_at": "31/12/2026",
    "updated_at": "31/12/2026 23:59",
}
_COLUMN_FIXED_WIDTHS = {"author": 190, "tags": 170}
_COLUMN_PADDING = 28
_COLUMN_ALIGNMENT = {
    "format": Qt.AlignCenter,
    "file_size": Qt.AlignRight | Qt.AlignVCenter,
    "avg_rating": Qt.AlignCenter,
    "pub_year": Qt.AlignCenter,
    "review_count": Qt.AlignCenter,
    "created_at": Qt.AlignCenter,
    "updated_at": Qt.AlignCenter,
}


# The sort dropdown's ORDER BY -> (column heading to mark, descending). None = the default, newest first.
_SORTED_COLUMN = {
    "documents.created_at DESC": ("created_at", True),
    "documents.title ASC": ("title", False),
    "documents.author ASC": ("author", False),
    "documents.file_size DESC": ("file_size", True),
    "documents.avg_rating DESC": ("avg_rating", True),
}


def _format_datetime(value, with_time: bool = True) -> str:
    if not value:
        return "—"
    try:
        return datetime.fromtimestamp(value).strftime("%d/%m/%Y %H:%M" if with_time else "%d/%m/%Y")
    except (TypeError, ValueError, OSError):
        return "—"


def _author_unknown(doc: dict) -> bool:
    author = (doc.get("author") or "").strip()
    return not author or author in ("Unknown", "Không rõ")


def _format_cell(doc: dict, key: str) -> str:
    if key == "title":
        return doc.get("title", "")
    if key == "author":
        return "" if _author_unknown(doc) else doc.get("author", "")
    if key == "pub_year":
        return str(doc.get("pub_year")) if doc.get("pub_year") else "—"
    if key == "format":
        return (doc.get("extension") or "").upper() or "—"
    if key == "file_size":
        return human_size(doc.get("file_size", 0))
    if key == "tags":
        return doc.get("tags", "") or "—"
    if key == "avg_rating":
        value = doc.get("avg_rating")
        return f"★ {value:.1f}".replace(".", ",") if value is not None else "—"
    if key == "review_count":
        return str(doc.get("review_count") or 0)
    if key == "created_at":
        return _format_datetime(doc.get(key), with_time=False)
    if key == "updated_at":
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
            if index.column() == 0:  # one accent bar at the row's left end, not one per cell
                painter.fillRect(option.rect.x(), option.rect.y(), self._BORDER_WIDTH, option.rect.height(),
                                 QColor(colors.selected_border))
            painter.restore()
            # QPalette.Text is an enum on the class: PySide6 has no such attribute on an
            # instance, and painting raised (repeatedly) as soon as a row got selected.
            option.palette.setColor(QPalette.Text, QColor(colors.selected_text))
            # The native style would otherwise also paint its own solid
            # Highlight fill on top of what was just drawn above -- clearing
            # the selected state here means only this delegate's own look
            # (the tint + stripe above) ends up on screen.
            option.state &= ~QStyle.State_Selected
        star = self._star_rect(option, index)
        if star is not None:  # keep the title text clear of the star at the end of the cell
            option.rect = option.rect.adjusted(0, 0, -(_STAR_SIZE + 10), 0)
        super().paint(painter, option, index)
        option.rect = option.rect.adjusted(0, 0, _STAR_SIZE + 10, 0) if star is not None else option.rect
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
        self._sorted: tuple[str, bool] | None = None  # (column key, descending) the list is ordered by
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

    def set_sorted(self, key: str | None, descending: bool = False) -> None:
        """Marks the column the list is sorted by (bold heading and an arrow); None clears the mark."""
        self._sorted = (key, descending) if key else None
        if self._columns:
            self.headerDataChanged.emit(Qt.Horizontal, 0, len(self._columns) - 1)

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
        marked = self._sorted is not None and self._sorted[0] == key
        if role == Qt.DisplayRole:
            arrow = (" ↓" if self._sorted[1] else " ↑") if marked else ""
            return _COLUMN_LABELS[key].upper() + arrow  # small capitals (QSS has no text-transform)
        if role == Qt.FontRole and marked:
            font = QFont()
            font.setBold(True)
            return font
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
            if column_key == "author" and _author_unknown(doc):
                return "Chưa rõ tác giả"
            return _format_cell(doc, column_key)
        if role == Qt.DecorationRole and column_key == "title":
            return self._cover_icon(doc)
        if role == Qt.TextAlignmentRole and column_key in _COLUMN_ALIGNMENT:
            return int(_COLUMN_ALIGNMENT[column_key])
        unknown_author = column_key == "author" and _author_unknown(doc)
        if role == Qt.FontRole and self._context:
            font = _content_font(self._context.config.config)
            font.setPixelSize(max(9, self._context.config.config.content_font_size))  # px like the rest of the design
            font.setItalic(unknown_author)  # "Chưa rõ tác giả" is set in italics and dimmed
            return font
        if role == Qt.ForegroundRole:
            if unknown_author:
                return QColor(theme_manager().token("ink3"))
            if self._context:
                color = _content_color(self._context.config.config)
                if color is not None:
                    return color
        if role == DocumentRole:
            return doc
        return None


class LibraryListWidget(QWidget):
    # "Phân loại thông minh" from the right-click menu: the ids of the selected documents.
    smart_classify_requested = Signal(list)
    add_files_requested = Signal()  # the empty-library state's "Thêm sách"
    add_folder_requested = Signal()  # ... and "Thêm thư mục…"

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

        self.model = ShelfModel(self, context=context)
        # Reading-list stars: one set lookup per painted cover, refreshed once per reload() (see _starred_ids).
        self._starred_ids: set[str] = set()
        self.list_view = ShelfView(self, is_starred=self._is_starred, on_toggle=self.toggle_reading_list)
        self.list_view.setModel(self.model)
        self.list_view.setIconSize(ICON_SIZE)
        self.list_view.setContextMenuPolicy(Qt.CustomContextMenu)
        self.list_view.customContextMenuRequested.connect(self._show_context_menu)
        self.list_view.doubleClicked.connect(self._open_selected)

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
        row_height = int(theme_manager().metric("table_row_height", 0))  # the layout's own row height, if it has one
        self.table_view.verticalHeader().setDefaultSectionSize(max(TABLE_THUMB_SIZE.height() + 8, row_height))
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

        self._grid_page: QWidget = self.list_view

        self.view_stack = QStackedWidget(self)
        self.view_stack.addWidget(self._grid_page)
        self.view_stack.addWidget(self.table_view)
        self.state_view = StateView(self)  # empty library / nothing found / error, in the middle of the area
        self.state_view.hide()

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
        layout.addWidget(self.state_view, 1)
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

    @property
    def page_size(self) -> int:
        return self.context.config.config.page_size or PAGE_SIZE

    def _build_pagination_bar(self) -> QWidget:
        """"Trang ‹ 1 2 3 › ............ 24 mỗi trang": the picked page is boxed; the size is a plain choice."""
        bar = QWidget(self)
        bar.setObjectName("PaginationBar")
        self.pagination_bar = bar
        row = QHBoxLayout(bar)
        row.setContentsMargins(16, 8, 16, 8)
        row.setSpacing(4)
        self.page_label = QLabel("Trang")
        self.prev_page_button = QToolButton()
        self.prev_page_button.setToolTip("Trang trước")
        self.next_page_button = QToolButton()
        self.next_page_button.setToolTip("Trang sau")
        self.prev_page_button.clicked.connect(lambda: self._go_to_page(self._current_page - 1))
        self.next_page_button.clicked.connect(lambda: self._go_to_page(self._current_page + 1))
        self._numbers_layout = QHBoxLayout()
        self._numbers_layout.setContentsMargins(0, 0, 0, 0)
        self._numbers_layout.setSpacing(4)
        self.page_buttons: dict[int, QPushButton] = {}
        self.page_size_combo = QComboBox()
        for size in PAGE_SIZES:
            self.page_size_combo.addItem(f"{size} mỗi trang", size)
        self.page_size_combo.activated.connect(self._on_page_size_chosen)
        row.addWidget(self.page_label)
        row.addSpacing(8)
        row.addWidget(self.prev_page_button)
        row.addLayout(self._numbers_layout)
        row.addWidget(self.next_page_button)
        row.addStretch(1)
        row.addWidget(self.page_size_combo)
        self._restyle_pagination()
        theme_manager().themeChanged.connect(self._restyle_pagination)
        return bar

    def _restyle_pagination(self, _key: str = "") -> None:
        tm = theme_manager()
        self.pagination_bar.setStyleSheet(
            f"#PaginationBar {{ background: {tm.token(tm.layout.content_surface)}; }}"
            f" QLabel {{ color: {tm.token('ink2')}; font-size: 13px; }}"
            f" QToolButton {{ border: 1px solid transparent; border-radius: 6px; min-width: 26px; min-height: 26px;"
            f" color: {tm.token('ink')}; background: transparent; font-size: 13px; }}"
            f" QToolButton:hover {{ border-color: {tm.token('line2')}; }}"
            f" QToolButton:disabled {{ color: {tm.token('ink3')}; }}"
            f" QPushButton {{ border: 1px solid transparent; border-radius: 6px; min-width: 26px; max-width: 40px;"
            f" min-height: 26px; padding: 0 4px; color: {tm.token('ink')}; background: transparent; }}"
            f" QPushButton:hover {{ border-color: {tm.token('line2')}; }}"
            f" QPushButton:checked {{ border: 1px solid {tm.token('accent')}; font-weight: 600; }}"
            f" QComboBox {{ border: none; background: transparent; color: {tm.token('ink2')}; }}"
        )
        self.prev_page_button.setIcon(line_icon("chevron_left", tm.token("ink2")))
        self.next_page_button.setIcon(line_icon("chevron_right", tm.token("ink2")))

    def _on_page_size_chosen(self, index: int) -> None:
        size = self.page_size_combo.itemData(index)
        if size and size != self.page_size:
            self.context.config.config.page_size = size
            self.context.config.save()
            self._current_page = 0
            self.reload()

    def _go_to_page(self, page: int) -> None:
        page = max(0, min(page, self._total_pages - 1))
        if page == self._current_page:
            return
        self._current_page = page
        self.reload()

    @staticmethod
    def page_window(current: int, total: int, width: int = 7) -> list[int | None]:
        """Page numbers (0-based) to show as buttons; None is an "…" gap. Always the first and last page."""
        if total <= width:
            return list(range(total))
        pages = {0, total - 1, current, current - 1, current + 1}
        pages = sorted(p for p in pages if 0 <= p < total)
        shown: list[int | None] = []
        for page in pages:
            if shown and page - shown[-1] > 1:  # type: ignore[operator]
                shown.append(None)
            shown.append(page)
        return shown

    def _update_pagination_ui(self, total: int) -> None:
        while self._numbers_layout.count():
            item = self._numbers_layout.takeAt(0)
            widget = item.widget()
            if widget is not None:
                widget.setParent(None)
                widget.deleteLater()
        self.page_buttons = {}
        for page in self.page_window(self._current_page, self._total_pages):
            if page is None:
                gap = QLabel("…")
                self._numbers_layout.addWidget(gap)
                continue
            button = QPushButton(str(page + 1))
            button.setCheckable(True)
            button.setChecked(page == self._current_page)
            button.setToolTip(f"{total:,} tài liệu".replace(",", ".") if page == self._current_page else f"Trang {page + 1}")
            button.clicked.connect(lambda _c=False, p=page: self._go_to_page(p))
            self._numbers_layout.addWidget(button)
            self.page_buttons[page] = button
        self.prev_page_button.setEnabled(self._current_page > 0)
        self.next_page_button.setEnabled(self._current_page < self._total_pages - 1)
        index = self.page_size_combo.findData(self.page_size)
        if index < 0:  # a size typed by hand into settings.json: show it too
            self.page_size_combo.addItem(f"{self.page_size} mỗi trang", self.page_size)
            index = self.page_size_combo.count() - 1
        self.page_size_combo.setCurrentIndex(index)

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

    def set_grid_icon_width(self, width: int) -> None:
        # list_view is a persistent widget (just hidden, not reconfigured, while table_view is the active one in the
        # stack) -- always keep it current so switching back to the shelf later shows the right size.
        self._grid_icon_width = width
        self.list_view.setIconSize(self._grid_icon_size())

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
        self._total_pages = max(1, math.ceil(total / self.page_size))
        self._current_page = min(self._current_page, self._total_pages - 1)

        documents = self.context.db.query_documents(
            fts_query=query,
            where_sql=where_sql,
            params=params,
            limit=self.page_size,
            offset=self._current_page * self.page_size,
            order_by=self._current_sort,
        )
        self._starred_ids = self.context.db.reading_list_ids()
        self.list_view.set_order_by(self._current_sort)
        self.model.set_documents(documents)
        self.table_model.set_documents(documents)
        self.table_model.set_sorted(*_SORTED_COLUMN.get(self._current_sort, ("created_at", True)))
        self._update_pagination_ui(total)
        self._show_state_or_view(total)

    def _show_state_or_view(self, total: int) -> None:
        """Nothing on the shelf: say why in the middle of the area instead of showing an empty grid."""
        self.view_stack.setVisible(total > 0)
        self.state_view.setVisible(total == 0)
        self.pagination_bar.setVisible(total > 0)
        if total > 0:
            return
        if self.library_filter.is_empty():
            self.state_view.show_empty_library(self.add_files_requested.emit, self.add_folder_requested.emit)
        else:
            self.state_view.show_no_match(self.context.filters.clear)

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
        cell_font = _content_font(self.context.config.config)
        cell_font.setPixelSize(max(9, self.context.config.config.content_font_size))
        metrics = QFontMetrics(cell_font)
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
        new_action = submenu.addAction("Tạo bộ sưu tập mới...")
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
        metadata_search_action = menu.addAction("Tìm thông tin sách...")
        ai_summary_action = menu.addAction("Tóm tắt AI...")
        smart_classify_action = menu.addAction("Phân loại thông minh")
        menu.addSeparator()
        copy_action = menu.addAction("Sao chép")
        cut_action = menu.addAction("Cắt")
        menu.addSeparator()
        _submenu, collection_actions = self._build_add_to_collection_menu(menu)
        send_ereader_action = menu.addAction("Gửi tới máy đọc sách...")
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
            open_review_dialog(self.context, doc, self)
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
        smart_classify_action = menu.addAction(f"Phân loại thông minh ({count} tài liệu)")
        menu.addSeparator()
        copy_action = menu.addAction("Sao chép")
        cut_action = menu.addAction("Cắt")
        menu.addSeparator()
        _submenu, collection_actions = self._build_add_to_collection_menu(menu)
        send_ereader_action = menu.addAction("Gửi tới máy đọc sách...")
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
        names = [f"{d.get('title') or '(không có tên)'}" for d in docs[:8]]
        if count > len(names):
            names.append(f"… và {count - len(names)} sách khác")
        if not confirm_danger(
            self, title=f"Xóa {count} sách khỏi thư viện?", subtitle="Bước xác nhận cuối",
            message=(f"<b>{count} sách</b> sẽ biến mất khỏi thư viện MewBook, kèm hashtag, đánh giá và ghi chú bạn đã gắn."),
            items=names,
            safe_text="<b>Không bị đụng tới:</b> file sách trên máy. Bạn có thể thêm lại sách vào thư viện bất cứ lúc nào.",
            ack_text=f"Tôi hiểu {count} sách sẽ bị gỡ khỏi thư viện", action_text=f"Xóa {count} sách khỏi thư viện",
            cancel_text="Giữ lại",
        ):
            return
        self.file_actions.delete_documents([(d["id"], d.get("file_path")) for d in docs], delete_physical_file=False)

    # ── Edit-menu-facing operations (mirror the context menu -- see
    # main_window.py's Edit menu) ────────────────────────────────────

    def _selected_documents(self) -> list[dict]:
        view = self._active_view()
        model = self._active_model()
        rows = sorted({idx.row() for idx in view.selectedIndexes()})
        return [d for d in (model.document_at(row) for row in rows) if d]

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

        docs = [d for d in self._selected_documents() if d.get("file_path")]
        dialog = EreaderSendDialog(self.context, docs, self.file_actions, target, self)
        dialog.exec()
        dialog.deleteLater()


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


def _is_light(hex_color: str) -> bool:
    return QColor(hex_color).lightnessF() > 0.5
