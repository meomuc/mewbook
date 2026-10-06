# SPDX-License-Identifier: AGPL-3.0-or-later
"""ShelfView: the cover grid drawn as bookshelves ("Kệ sách").

Why a custom view rather than a QListView with a delegate: a shelf needs things a list cell cannot draw -- a labelled
group per shelf (the label follows the sort: "HÔM NAY", "A", "5★"), a wooden board under each row, covers standing on
it at their *real* proportions with their bottoms aligned, and a lift + ring on the selected one. It is a
QAbstractItemView, so the model, selection model, `clicked` / `doubleClicked` signals, keyboard navigation and context
menu all work exactly as they do for the list it replaces; only the geometry and painting are ours.

Model contract (see library_view.ShelfModel): `document_at(row) -> dict | None` and
`cover_state(row) -> ("ready" | "loading" | "none", QPixmap | None)`. Nothing here reads a file or the database.
Colours come from ThemeManager, so a theme switch (which rebuilds the window) restyles it; nothing is hard-coded.

A layout whose metrics ask for it (`grid_cover_height` > 0, the "Tối giản" look) turns the same view into a plain
captioned grid: no boards, no group labels, no lift -- each cover has its stars, title and author underneath and a
ring when selected. Geometry and painting branch on that one metric, never on a layout or theme id.
"""
from __future__ import annotations

from collections import OrderedDict
from dataclasses import dataclass, field

from PySide6.QtCore import QModelIndex, QPoint, QPointF, QRect, QRectF, QSize, Qt
from PySide6.QtGui import (
    QColor,
    QFont,
    QFontMetrics,
    QLinearGradient,
    QPainter,
    QPainterPath,
    QPen,
    QPixmap,
    QRegion,
    QTextLayout,
    QTextOption,
)
from PySide6.QtWidgets import QAbstractItemView, QFrame

from smartdoc.presentation.line_icons import icon_pixmap
from smartdoc.presentation.ornaments import paint_backdrop, paint_shelf, shelf_thickness
from smartdoc.presentation.shelf_groups import shelf_for
from smartdoc.presentation.theme_manager import theme_manager

DOC_ROLE = Qt.UserRole + 1  # library_view.DocumentRole: the whole document dict

LABEL_W = 88  # the shelf label column
LEFT_PAD = 16
UNDER_H = 34  # the soft shadow below the board
GAP = 18  # between covers
BOARD_INSET = 24  # board edge -> first cover
TOP_PAD = 30  # above the tallest cover: room for the lift and the hint line
LIFT = 6
RING_GAP, RING_W = 3, 2.5
MAX_ASPECT = 1.5  # a cover taller than this (height/width) is fitted, not stretched
PLACEHOLDER_ASPECT = 1.4
COVER_RADIUS = 3
STAR = 22
HINT_TEXT = "Bấm để xem · bấm đúp để đọc"
CAPTION_H = 70  # captioned grid: stars + two title lines + author under a cover
CAPTION_TOP = 22  # from the bottom of a cover box to the stars (room for the selection ring)


@dataclass
class _Shelf:
    top: int
    height: int
    label: tuple[str, str] | None  # (title, subtitle) on the first shelf of a group, else None
    rows: list[int] = field(default_factory=list)
    line_y: int = 0  # y of the board's top edge, in content coordinates


class ShelfView(QAbstractItemView):
    def __init__(self, parent=None, *, context=None, is_starred=None, on_toggle=None) -> None:
        super().__init__(parent)
        self._context = context
        self._is_starred = is_starred or (lambda _doc_id: False)
        self._on_toggle = on_toggle or (lambda _doc_id: None)
        self._icon_size = QSize(120, int(120 * 1.42))
        self._order_by: str | None = None
        self._shelves: list[_Shelf] = []
        self._rects: dict[int, QRect] = {}  # row -> cover box in content coordinates (before the lift)
        self._content_h = 0
        self._scaled: OrderedDict[tuple[int, int, int], QPixmap] = OrderedDict()
        self._star_pressed = -1
        self.setFrameShape(QFrame.NoFrame)
        self.setSelectionMode(QAbstractItemView.ExtendedSelection)
        self.setEditTriggers(QAbstractItemView.NoEditTriggers)
        self.setMouseTracking(True)
        self.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        self.verticalScrollBar().setSingleStep(40)
        self.setAutoFillBackground(False)
        self.viewport().setAutoFillBackground(False)

    # -- QListView-compatible sizing API (tests and LibraryListWidget use these) ---------------------------------------
    def iconSize(self) -> QSize:  # noqa: N802 -- Qt naming
        return QSize(self._icon_size)

    def setIconSize(self, size: QSize) -> None:  # noqa: N802 -- Qt naming
        self._icon_size = QSize(size)
        self._scaled.clear()
        self._relayout()

    def gridSize(self) -> QSize:  # noqa: N802 -- Qt naming
        """One cover's cell: the cover plus its gutter across, and a shelf row's height down."""
        return QSize(self._icon_size.width() + GAP, self._row_height())

    def set_order_by(self, order_by: str | None) -> None:
        """The current sort (a shelf_groups.SORT_* fragment): decides how books are grouped on shelves."""
        if order_by != self._order_by:
            self._order_by = order_by
            self._relayout()

    # -- geometry --------------------------------------------------------------------------------------------------
    def _captioned(self) -> bool:
        """The layout wants a captioned grid without shelves (see the module docstring)."""
        return theme_manager().metric("grid_cover_height", 0) > 0

    def _grid_gap(self) -> int:
        return int(theme_manager().metric("grid_gap", GAP))

    def _box_h(self) -> int:
        return int(self._icon_size.height())

    def _row_height(self) -> int:
        if self._captioned():
            return 10 + self._box_h() + CAPTION_TOP + CAPTION_H + self._grid_gap() // 2
        return TOP_PAD + self._box_h() + shelf_thickness(theme_manager()) + UNDER_H // 2

    def _board_rect_x(self) -> tuple[int, int]:
        width = self.viewport().width()
        if self._captioned():
            return LEFT_PAD, max(LEFT_PAD + 40, width - LEFT_PAD)
        left = LEFT_PAD + LABEL_W
        return left, max(left + 40, width - LEFT_PAD)

    def _per_row(self) -> int:
        left, right = self._board_rect_x()
        if self._captioned():
            return max(1, (right - left + self._grid_gap()) // (self._icon_size.width() + self._grid_gap()))
        usable = right - left - 2 * BOARD_INSET
        return max(1, (usable + GAP) // (self._icon_size.width() + GAP))

    def _column_x(self, slot: int, per_row: int, left: int, right: int, width: int) -> int:
        """x of column `slot` in the captioned grid: the free width is shared out between the columns, up to a limit."""
        if per_row <= 1:
            return left
        spare = (right - left - per_row * width) // (per_row - 1)
        return left + slot * (width + max(self._grid_gap(), min(spare, 2 * self._grid_gap())))

    def _relayout(self) -> None:
        self._shelves = []
        self._rects = {}
        model = self.model()
        count = model.rowCount() if model is not None else 0
        per_row = self._per_row()
        left, _right = self._board_rect_x()
        width, box_h = self._icon_size.width(), self._box_h()
        row_h = self._row_height()
        y = 0
        if self._captioned():
            _left, right = self._board_rect_x()
            for start in range(0, count, per_row):
                chunk = list(range(start, min(count, start + per_row)))
                shelf = _Shelf(top=y, height=row_h, label=None, rows=chunk)
                for slot, row in enumerate(chunk):
                    self._rects[row] = QRect(self._column_x(slot, per_row, left, right, width), y + 10, width, box_h)
                self._shelves.append(shelf)
                y += row_h
            self._content_h = y + 12
            self.updateGeometries()
            self.viewport().update()
            return
        # First pass: which shelf (group) each book stands on, in order.
        groups: list[tuple[str, tuple[str, str], list[int]]] = []
        titles: dict[str, object] = {}
        for row in range(count):
            doc = model.document_at(row) or {}
            shelf = shelf_for(doc, self._order_by)
            titles[shelf.key] = shelf
            if not groups or groups[-1][0] != shelf.key:
                groups.append((shelf.key, (shelf.title, ""), []))
            groups[-1][2].append(row)
        for key, (title, _sub), rows in groups:
            shelf_def = titles[key]
            for chunk_start in range(0, len(rows), per_row):
                chunk = rows[chunk_start : chunk_start + per_row]
                label = (title, shelf_def.subtitle(len(rows))) if chunk_start == 0 else None
                shelf = _Shelf(top=y, height=row_h, label=label, rows=chunk)
                shelf.line_y = y + TOP_PAD + box_h
                for slot, row in enumerate(chunk):
                    x = left + BOARD_INSET + slot * (width + GAP)
                    self._rects[row] = QRect(x, y + TOP_PAD, width, box_h)
                self._shelves.append(shelf)
                y += row_h
        self._content_h = y + 12
        self.updateGeometries()
        self.viewport().update()

    def updateGeometries(self) -> None:  # noqa: N802 -- Qt override
        viewport = self.viewport().size()
        bar = self.verticalScrollBar()
        bar.setRange(0, max(0, self._content_h - viewport.height()))
        bar.setPageStep(viewport.height())
        super().updateGeometries()

    def resizeEvent(self, event) -> None:  # noqa: N802 -- Qt override
        super().resizeEvent(event)
        self._relayout()

    def reset(self) -> None:
        super().reset()
        self._scaled.clear()
        self._relayout()

    def rowsInserted(self, parent, start, end) -> None:  # noqa: N802 -- Qt override
        super().rowsInserted(parent, start, end)
        self._relayout()

    def rowsAboutToBeRemoved(self, parent, start, end) -> None:  # noqa: N802 -- Qt override
        super().rowsAboutToBeRemoved(parent, start, end)
        self._relayout()

    # -- QAbstractItemView virtuals ----------------------------------------------------------------------------------
    def _offset(self) -> int:
        return self.verticalScrollBar().value()

    def verticalOffset(self) -> int:  # noqa: N802 -- Qt override
        return self._offset()

    def horizontalOffset(self) -> int:  # noqa: N802 -- Qt override
        return 0

    def isIndexHidden(self, index) -> bool:  # noqa: N802 -- Qt override
        return False

    def _hit_rect(self, row: int) -> QRect:
        """Where the row's cover is now (with the lift if selected), in viewport coordinates."""
        rect = self._rects.get(row)
        if rect is None:
            return QRect()
        rect = rect.translated(0, -self._offset())
        if self._is_selected_row(row) and not self._captioned():
            rect = rect.translated(0, -LIFT)
        return rect

    def visualRect(self, index) -> QRect:  # noqa: N802 -- Qt override
        return self._hit_rect(index.row()) if index.isValid() else QRect()

    def indexAt(self, point) -> QModelIndex:  # noqa: N802 -- Qt override
        model = self.model()
        if model is None:
            return QModelIndex()
        position = QPoint(point)
        for row in self._rows_near(position.y()):
            if self._hit_rect(row).contains(position):
                return model.index(row, 0)
        return QModelIndex()

    def _rows_near(self, y: int):
        """Rows on the shelves that could contain viewport y (cheap: only the shelf it falls on, and its neighbours)."""
        content_y = y + self._offset()
        for shelf in self._shelves:
            if shelf.top - LIFT <= content_y <= shelf.top + shelf.height + LIFT:
                yield from shelf.rows

    def scrollTo(self, index, hint=QAbstractItemView.EnsureVisible) -> None:  # noqa: N802 -- Qt override
        rect = self._rects.get(index.row())
        if rect is None:
            return
        bar = self.verticalScrollBar()
        top = rect.top() - TOP_PAD
        bottom = rect.bottom() + (CAPTION_TOP + CAPTION_H if self._captioned() else shelf_thickness(theme_manager()) + 8)
        if top < bar.value():
            bar.setValue(top)
        elif bottom > bar.value() + self.viewport().height():
            bar.setValue(bottom - self.viewport().height())

    def _shelf_of(self, row: int) -> int:
        for i, shelf in enumerate(self._shelves):
            if row in shelf.rows:
                return i
        return -1

    def moveCursor(self, action, modifiers) -> QModelIndex:  # noqa: N802 -- Qt override
        model = self.model()
        if model is None or model.rowCount() == 0:
            return QModelIndex()
        current = self.currentIndex().row() if self.currentIndex().isValid() else -1
        last = model.rowCount() - 1
        if current < 0:
            return model.index(0, 0)
        if action in (QAbstractItemView.MoveRight, QAbstractItemView.MoveNext):
            target = min(last, current + 1)
        elif action in (QAbstractItemView.MoveLeft, QAbstractItemView.MovePrevious):
            target = max(0, current - 1)
        elif action == QAbstractItemView.MoveHome:
            target = 0
        elif action == QAbstractItemView.MoveEnd:
            target = last
        elif action in (QAbstractItemView.MoveUp, QAbstractItemView.MoveDown, QAbstractItemView.MovePageUp,
                        QAbstractItemView.MovePageDown):
            steps = 1 if action in (QAbstractItemView.MoveUp, QAbstractItemView.MoveDown) else max(
                1, self.viewport().height() // max(1, self._row_height()))
            direction = 1 if action in (QAbstractItemView.MoveDown, QAbstractItemView.MovePageDown) else -1
            shelf_index = self._shelf_of(current)
            wanted = max(0, min(len(self._shelves) - 1, shelf_index + direction * steps))
            centre = self._rects[current].center().x()
            row_choices = self._shelves[wanted].rows
            target = min(row_choices, key=lambda r: abs(self._rects[r].center().x() - centre))
        else:
            target = current
        return model.index(target, 0)

    def setSelection(self, rect, command) -> None:  # noqa: N802 -- Qt override
        model = self.model()
        if model is None:
            return
        area = QRect(rect).normalized()
        from PySide6.QtCore import QItemSelection

        selection = QItemSelection()
        for row in range(model.rowCount()):
            if self._hit_rect(row).intersects(area):
                index = model.index(row, 0)
                selection.select(index, index)
        self.selectionModel().select(selection, command)

    def visualRegionForSelection(self, selection) -> QRegion:  # noqa: N802 -- Qt override
        region = QRegion()
        for index in selection.indexes():
            region += self.visualRect(index)
        return region

    def _is_selected_row(self, row: int) -> bool:
        model, selection = self.model(), self.selectionModel()
        return model is not None and selection is not None and selection.isSelected(model.index(row, 0))

    # -- stars ---------------------------------------------------------------------------------------------------------
    def _star_rect(self, row: int) -> QRect:
        cover = self._hit_rect(row)
        return QRect(cover.right() - STAR - 4, cover.top() + 4, STAR, STAR)

    def _star_at(self, position) -> int:
        for row in self._rows_near(position.y()):
            if self._star_rect(row).contains(position):
                return row
        return -1

    def mousePressEvent(self, event) -> None:  # noqa: N802 -- Qt override
        row = self._star_at(event.position().toPoint()) if event.button() == Qt.LeftButton else -1
        if row >= 0:
            self._star_pressed = row  # a press on the star never changes the selection or opens the reader
            return
        super().mousePressEvent(event)

    def mouseReleaseEvent(self, event) -> None:  # noqa: N802 -- Qt override
        if self._star_pressed >= 0:
            row, self._star_pressed = self._star_pressed, -1
            if self._star_at(event.position().toPoint()) == row:
                doc = self.model().document_at(row) or {}
                if doc.get("id"):
                    self._on_toggle(doc["id"])
                self.viewport().update()
            return
        super().mouseReleaseEvent(event)

    def mouseDoubleClickEvent(self, event) -> None:  # noqa: N802 -- Qt override
        if self._star_at(event.position().toPoint()) >= 0:
            return
        super().mouseDoubleClickEvent(event)

    def mouseMoveEvent(self, event) -> None:  # noqa: N802 -- Qt override
        over_star = self._star_at(event.position().toPoint()) >= 0
        self.viewport().setCursor(Qt.PointingHandCursor if over_star or self.indexAt(event.position().toPoint()).isValid()
                                  else Qt.ArrowCursor)
        super().mouseMoveEvent(event)

    def selectionChanged(self, selected, deselected) -> None:  # noqa: N802 -- Qt override
        super().selectionChanged(selected, deselected)
        self.viewport().update()  # the lift moves covers, so repaint whole shelves rather than just their rects

    # -- painting ------------------------------------------------------------------------------------------------------
    def _scaled_pixmap(self, source: QPixmap, size: QSize) -> QPixmap:
        dpr = self.devicePixelRatioF()
        key = (source.cacheKey(), size.width(), size.height())
        cached = self._scaled.get(key)
        if cached is not None:
            self._scaled.move_to_end(key)  # LRU: promote to most-recently used
            return cached
        scaled = source.scaled(int(size.width() * dpr), int(size.height() * dpr), Qt.IgnoreAspectRatio,
                               Qt.SmoothTransformation)
        scaled.setDevicePixelRatio(dpr)
        # Evict the 50 oldest entries instead of clearing everything — avoids
        # a full-miss repaint after a scroll.
        while len(self._scaled) >= 300:
            self._scaled.popitem(last=False)
        self._scaled[key] = scaled
        return scaled

    def paintEvent(self, event) -> None:  # noqa: N802 -- Qt override
        painter = QPainter(self.viewport())
        painter.setRenderHint(QPainter.Antialiasing)
        painter.setRenderHint(QPainter.SmoothPixmapTransform)
        tm = theme_manager()
        offset = self._offset()
        visible = QRect(0, 0, self.viewport().width(), self.viewport().height())
        painter.fillRect(visible, QColor(tm.token(tm.layout.content_surface)))  # the ground the layout puts covers on
        paint_backdrop(painter, visible, tm)  # the theme's faint landscape: fixed to the view, behind shelves and covers
        model = self.model()
        captioned = self._captioned()
        selection = self.selectionModel()
        single = selection is not None and len(selection.selectedIndexes()) == 1
        current_row = selection.selectedIndexes()[0].row() if single else -1
        for shelf in self._shelves:
            top = shelf.top - offset
            if top > visible.bottom() or top + shelf.height < visible.top():
                continue
            if not captioned:
                self._paint_shelf(painter, shelf, offset, tm)
            for row in shelf.rows:
                self._paint_cover(painter, model, row, tm, show_hint=row == current_row and not captioned)
                if captioned:
                    self._paint_caption(painter, model, row, tm)
        painter.end()

    def _paint_shelf(self, painter: QPainter, shelf: _Shelf, offset: int, tm) -> None:
        left, right = self._board_rect_x()
        line_y = shelf.line_y - offset
        if shelf.label is not None:
            title, subtitle = shelf.label
            title_font = QFont(tm.font_family("disp"))
            title_font.setPixelSize(10)
            title_font.setWeight(QFont.DemiBold)
            title_font.setLetterSpacing(QFont.AbsoluteSpacing, 1.6)
            painter.setFont(title_font)
            painter.setPen(QColor(tm.token("ink3")))
            metrics = QFontMetrics(title_font)
            label_w = LABEL_W - 4
            painter.drawText(QRect(LEFT_PAD, line_y - 92, label_w, metrics.height()), Qt.AlignLeft | Qt.AlignVCenter,
                             metrics.elidedText(title, Qt.ElideRight, label_w))
            sub_font = QFont(tm.font_family("content"))
            sub_font.setPixelSize(12)
            sub_font.setItalic(True)
            painter.setFont(sub_font)
            painter.setPen(QColor(tm.token("ink3")))
            sub_rect = QRect(LEFT_PAD, line_y - 92 + metrics.height() + 2, label_w, 40)
            painter.drawText(sub_rect, Qt.AlignLeft | Qt.AlignTop | Qt.TextWordWrap, subtitle)
        # The shadow below the board, then the board (its look comes from the theme's `shelf` ornament).
        board_h = shelf_thickness(tm)
        shadow = QLinearGradient(0, line_y + board_h, 0, line_y + board_h + UNDER_H)
        under = tm.color("under")
        shadow.setColorAt(0, under)
        end = QColor(under)
        end.setAlpha(0)
        shadow.setColorAt(1, end)
        painter.fillRect(QRect(left, line_y + board_h, right - left, UNDER_H), shadow)
        paint_shelf(painter, QRect(left, line_y, right - left, board_h), tm)

    def _paint_cover(self, painter: QPainter, model, row: int, tm, *, show_hint: bool) -> None:
        doc = model.document_at(row) or {}
        base = self._rects[row].translated(0, -self._offset())
        selected = self._is_selected_row(row)
        state, pixmap = model.cover_state(row)
        # Real covers keep their own proportions (fitted inside the box, bottom on the board); a book with no cover
        # gets the standard placeholder shape.
        if state == "ready" and pixmap is not None and not pixmap.isNull():
            aspect = min(MAX_ASPECT, pixmap.height() / max(1, pixmap.width()))
            height = min(base.height(), int(base.width() * aspect))
            width = base.width() if height == int(base.width() * aspect) else int(height / aspect)
        else:
            height, width = min(base.height(), int(base.width() * PLACEHOLDER_ASPECT)), base.width()
        cover = QRect(base.x() + (base.width() - width) // 2, base.bottom() - height + 1, width, height)
        if selected and not self._captioned():
            cover.translate(0, -LIFT)
        cover_f = QRectF(cover)

        # Soft drop shadow (the board's own shadow does the rest).
        painter.setPen(Qt.NoPen)
        shadow = tm.color("shadow")
        for spread, alpha_scale in ((4, 0.10), (2, 0.16), (1, 0.24)):
            tone = QColor(shadow)
            tone.setAlpha(int(shadow.alpha() * alpha_scale))
            painter.setBrush(tone)
            painter.drawRoundedRect(cover_f.adjusted(-spread + 1, -spread + 3, spread - 1, spread + 2),
                                    COVER_RADIUS + 1, COVER_RADIUS + 1)

        clip = QPainterPath()
        clip.addRoundedRect(cover_f, COVER_RADIUS, COVER_RADIUS)
        painter.save()
        painter.setClipPath(clip)
        if state == "ready" and pixmap is not None and not pixmap.isNull():
            painter.drawPixmap(cover.topLeft(), self._scaled_pixmap(pixmap, cover.size()))
        else:
            painter.fillRect(cover, QColor(tm.token("surface2")))
        painter.restore()
        if state == "none":
            self._paint_placeholder(painter, cover, doc, tm)

        self._paint_format_chip(painter, cover, doc)
        self._paint_rating_badge(painter, cover, doc)
        self._paint_star(painter, cover, doc, tm)
        if doc.get("file_status") == "missing":
            self._paint_missing(painter, cover, tm)
        elif doc.get("file_status") == "trashed":
            self._paint_trashed(painter, cover, tm)
        if selected:
            ring = QPen(QColor(tm.token("accent")), RING_W)
            painter.setPen(ring)
            painter.setBrush(Qt.NoBrush)
            gap = 4 if self._captioned() else RING_GAP
            painter.drawRoundedRect(cover_f.adjusted(-(gap + RING_W / 2), -(gap + RING_W / 2),
                                                     gap + RING_W / 2, gap + RING_W / 2),
                                    COVER_RADIUS + 3, COVER_RADIUS + 3)
        if show_hint:
            font = QFont(tm.font_family("content"))
            font.setPixelSize(11)
            font.setItalic(True)
            painter.setFont(font)
            painter.setPen(QColor(tm.token("ink3")))
            hint_rect = QRect(cover.left() - 10, cover.top() - 24, max(cover.width() + 60, 190), 14)
            painter.drawText(hint_rect, Qt.AlignLeft | Qt.AlignVCenter, HINT_TEXT)

    def _paint_caption(self, painter: QPainter, model, row: int, tm) -> None:
        """Under a cover of the captioned grid: the rating stars, the title (two lines at most) and the author."""
        doc = model.document_at(row) or {}
        box = self._rects[row].translated(0, -self._offset())
        x, width, top = box.x(), box.width(), box.bottom() + CAPTION_TOP - 6
        painter.save()
        rating = doc.get("avg_rating")
        if rating:
            stars = max(0, min(5, round(float(rating))))
            star_font = QFont(tm.font_family("ui"))
            star_font.setPixelSize(10)
            painter.setFont(star_font)
            painter.setPen(QColor(tm.token("accent")))
            painter.drawText(QRect(x, top, width, 12), Qt.AlignLeft | Qt.AlignVCenter, "★" * stars + "☆" * (5 - stars))
            top += 14
        title_font = QFont(tm.font_family("ui"))
        title_font.setPixelSize(13)
        title_font.setWeight(QFont.DemiBold)
        metrics = QFontMetrics(title_font)
        painter.setFont(title_font)
        painter.setPen(QColor(tm.token("ink")))
        for line_no, line in enumerate(self._two_lines(doc.get("title") or "", title_font, width)):
            painter.drawText(QRect(x, top + line_no * metrics.lineSpacing(), width, metrics.lineSpacing()),
                             Qt.AlignLeft | Qt.AlignVCenter, line)
        author_font = QFont(tm.font_family("ui"))
        author_font.setPixelSize(12)
        painter.setFont(author_font)
        painter.setPen(QColor(tm.token("ink2")))
        author = doc.get("author") or ""
        if author and author.strip().lower() != "unknown":
            painter.drawText(QRect(x, top + metrics.lineSpacing() * 2 + 2, width, 16), Qt.AlignLeft | Qt.AlignVCenter,
                             QFontMetrics(author_font).elidedText(author, Qt.ElideRight, width))
        painter.restore()

    @staticmethod
    def _two_lines(text: str, font: QFont, width: int) -> list[str]:
        """`text` wrapped to `width` px and cut to two lines; the second ends in an ellipsis if there was more."""
        layout = QTextLayout(text, font)
        option = QTextOption()
        option.setWrapMode(QTextOption.WordWrap)
        layout.setTextOption(option)
        layout.beginLayout()
        lines: list[tuple[int, int]] = []
        while True:
            line = layout.createLine()
            if not line.isValid():
                break
            line.setLineWidth(width)
            lines.append((line.textStart(), line.textLength()))
        layout.endLayout()
        pieces = [text[start:start + length].strip() for start, length in lines]
        if len(pieces) <= 2:
            return pieces
        rest = " ".join(pieces[1:])
        return [pieces[0], QFontMetrics(font).elidedText(rest, Qt.ElideRight, width)]

    def _paint_placeholder(self, painter: QPainter, cover: QRect, doc: dict, tm) -> None:
        """No cover: dashed outline, a book icon, the title, and "Chưa có bìa" -- the title stays readable."""
        painter.save()
        pen = QPen(QColor(tm.token("line2")), 1, Qt.DashLine)
        painter.setPen(pen)
        painter.setBrush(Qt.NoBrush)
        painter.drawRoundedRect(QRectF(cover).adjusted(0.5, 0.5, -0.5, -0.5), COVER_RADIUS, COVER_RADIUS)
        icon = icon_pixmap("book", tm.token("ink3"), 20)
        painter.drawPixmap(QPointF(cover.center().x() - 10, cover.top() + cover.height() * 0.22), icon)
        title_font = QFont(tm.font_family("content"))
        title_font.setPixelSize(max(9, min(13, cover.width() // 9)))
        title_font.setWeight(QFont.DemiBold)
        painter.setFont(title_font)
        painter.setPen(QColor(tm.token("ink")))
        text_rect = QRect(cover.left() + 8, int(cover.top() + cover.height() * 0.22) + 28, cover.width() - 16,
                          int(cover.height() * 0.4))
        painter.drawText(text_rect, Qt.AlignHCenter | Qt.AlignTop | Qt.TextWordWrap, doc.get("title") or "")
        small = QFont(tm.font_family("ui"))
        small.setPixelSize(10)
        painter.setFont(small)
        painter.setPen(QColor(tm.token("ink3")))
        painter.drawText(QRect(cover.left(), cover.bottom() - 26, cover.width(), 16), Qt.AlignCenter, "Chưa có bìa")
        painter.restore()

    def _paint_format_chip(self, painter: QPainter, cover: QRect, doc: dict) -> None:
        extension = (doc.get("extension") or "").upper()
        if not extension:
            return
        font = QFont(theme_manager().font_family("ui"))
        font.setPixelSize(10)
        font.setWeight(QFont.Bold)
        metrics = QFontMetrics(font)
        chip = QRect(cover.left() + 5, cover.top() + 5, metrics.horizontalAdvance(extension) + 10, 15)
        painter.save()
        painter.setPen(Qt.NoPen)
        painter.setBrush(QColor(0, 0, 0, 150))
        painter.drawRoundedRect(chip, 3, 3)
        painter.setFont(font)
        painter.setPen(QColor(255, 255, 255))
        painter.drawText(chip, Qt.AlignCenter, extension)
        painter.restore()

    def _paint_rating_badge(self, painter: QPainter, cover: QRect, doc: dict) -> None:
        """Small ★ avg_rating pill at the bottom-right of the cover when the setting is on.
        Dark semi-transparent background (same overlay pattern as the format chip) ensures
        readability regardless of cover art colour."""
        if self._context is None or not self._context.config.config.show_community_rating_badge:
            return
        rating = doc.get("avg_rating")
        if not rating:
            return
        badge_text = f"★ {float(rating):.1f}"
        font = QFont(theme_manager().font_family("ui"))
        font.setPixelSize(10)
        font.setWeight(QFont.DemiBold)
        metrics = QFontMetrics(font)
        pad_x, pad_y = 5, 2
        badge_w = metrics.horizontalAdvance(badge_text) + pad_x * 2
        badge_h = metrics.height() + pad_y * 2
        chip = QRect(cover.right() - badge_w - 5, cover.bottom() - badge_h - 5, badge_w, badge_h)
        painter.save()
        painter.setPen(Qt.NoPen)
        painter.setBrush(QColor(0, 0, 0, 150))  # semi-transparent overlay; not themed — must contrast any cover
        painter.drawRoundedRect(chip, 3, 3)
        painter.setFont(font)
        painter.setPen(QColor(255, 255, 255))   # white on dark overlay is always readable
        painter.drawText(chip, Qt.AlignCenter, badge_text)
        painter.restore()

    def _paint_star(self, painter: QPainter, cover: QRect, doc: dict, tm) -> None:
        starred = bool(self._is_starred(doc.get("id")))
        rect = QRect(cover.right() - STAR - 4, cover.top() + 4, STAR, STAR)
        painter.save()
        painter.setPen(QPen(QColor(tm.token("line2")), 1))
        painter.setBrush(QColor(tm.token("panel")))
        painter.drawEllipse(rect)
        accent = tm.token("accent") if starred else tm.token("ink2")
        painter.drawPixmap(QPointF(rect.x() + (STAR - 12) / 2, rect.y() + (STAR - 12) / 2),
                           icon_pixmap("star_fill" if starred else "star", accent, 12))
        painter.restore()

    def _paint_missing(self, painter: QPainter, cover: QRect, tm) -> None:
        font = QFont(tm.font_family("ui"))
        font.setPixelSize(10)
        font.setWeight(QFont.DemiBold)
        metrics = QFontMetrics(font)
        text = "Không thấy file"
        width = min(cover.width() - 8, metrics.horizontalAdvance(text) + 30)
        chip = QRect(cover.left() + (cover.width() - width) // 2, cover.bottom() - 26, width, 18)
        painter.save()
        painter.setPen(QPen(QColor(tm.token("warn")), 1))
        painter.setBrush(QColor(tm.token("surface")))
        painter.drawRoundedRect(chip, 3, 3)
        painter.drawPixmap(QPointF(chip.left() + 5, chip.center().y() - 6), icon_pixmap("warn", tm.token("warn"), 12))
        painter.setFont(font)
        painter.setPen(QColor(tm.token("ink")))
        painter.drawText(chip.adjusted(20, 0, -2, 0), Qt.AlignVCenter | Qt.AlignLeft,
                         metrics.elidedText(text, Qt.ElideRight, chip.width() - 22))
        painter.restore()

    def _paint_trashed(self, painter: QPainter, cover: QRect, tm) -> None:
        font = QFont(tm.font_family("ui"))
        font.setPixelSize(10)
        font.setWeight(QFont.DemiBold)
        metrics = QFontMetrics(font)
        text = "Đã xóa"
        width = min(cover.width() - 8, metrics.horizontalAdvance(text) + 30)
        chip = QRect(cover.left() + (cover.width() - width) // 2, cover.bottom() - 26, width, 18)
        painter.save()
        painter.setOpacity(0.85)
        painter.setPen(QPen(QColor(tm.token("err")), 1))
        painter.setBrush(QColor(tm.token("surface")))
        painter.drawRoundedRect(chip, 3, 3)
        painter.drawPixmap(QPointF(chip.left() + 5, chip.center().y() - 6), icon_pixmap("trash", tm.token("err"), 12))
        painter.setFont(font)
        painter.setPen(QColor(tm.token("ink")))
        painter.drawText(chip.adjusted(20, 0, -2, 0), Qt.AlignVCenter | Qt.AlignLeft,
                         metrics.elidedText(text, Qt.ElideRight, chip.width() - 22))
        painter.restore()


if __name__ == "__main__":
    import sys

    from PySide6.QtCore import QAbstractListModel
    from PySide6.QtWidgets import QApplication

    class _DemoModel(QAbstractListModel):
        def rowCount(self, parent=QModelIndex()) -> int:  # noqa: B008
            return 0 if parent.isValid() else 14

        def data(self, index, role=Qt.DisplayRole):
            return None

        def document_at(self, row):
            return {"id": f"d{row}", "title": f"Sách {row}", "extension": "pdf", "created_at": 1.0 * row}

        def cover_state(self, row):
            return "none", None

    demo = QApplication(sys.argv)
    theme_manager().apply(demo, "broadsheet")
    view = ShelfView()
    view.setModel(_DemoModel())
    view.resize(900, 640)
    view.show()
    sys.exit(demo.exec())
