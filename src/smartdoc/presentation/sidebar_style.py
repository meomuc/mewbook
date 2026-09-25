"""Shared look for the sidebar's lists (collections, facet tree).

Rows keep their plain "Name (12)" text -- that's what the rest of the code
and the tests read back -- and this delegate only changes how it's drawn:
the name on the left, the count right-aligned and muted, the selected row
as a tinted band with an accent stripe down its left edge. A facet
category root ("Tác giả", "Hashtag", ...) is drawn as a small upper-case
section heading instead of as a row.
"""
from __future__ import annotations

import re

from PySide6.QtCore import QPointF, QRect, QRectF, QSize, Qt
from PySide6.QtGui import QColor, QFont, QFontMetrics, QPainter, QPainterPath, QPen, QPolygonF
from PySide6.QtWidgets import QLabel, QStyle, QStyledItemDelegate, QStyleOptionViewItem, QWidget

from smartdoc.presentation.line_icons import icon_pixmap
from smartdoc.presentation.theme import current_colors, item_text, section_text
from smartdoc.presentation.theme_manager import theme_manager

_COUNT_RE = re.compile(r"^(.*) \((\d+)\)$", re.DOTALL)
ROW_HEIGHT = 32
TALL_ROW_HEIGHT = 44  # Walnut Library's roomier rows
SECTION_ROW_HEIGHT = 38
_STRIPE = 3
SECTION_ITEM_ID = "__section__"  # a non-selectable heading row inside a pill list ("BỘ SƯU TẬP  +")
PILL_ROW_HEIGHT = 36  # a 30 px pill and 3 px of air above and below
_ICON_SIZE = 15

# What leading icon a row gets (see CountRowDelegate's `icon_for`).
ICON_ALL = "all"
ICON_FOLDER = "folder"
ICON_STAR = "star"


def split_count(text: str) -> tuple[str, str]:
    match = _COUNT_RE.match(text or "")
    if not match:
        return text or "", ""
    return match.group(1), match.group(2)


def section_font(base: QFont | None = None) -> QFont:
    """Group labels: 10 px, semi-bold, wide-spaced capitals in the display face (design rule: only group labels,
    column headings and pills use this style). Code-style themes keep them as quiet comments."""
    colors = current_colors()
    font = QFont(base) if base is not None else QFont()
    font.setFamily(theme_manager().font_family("disp"))
    font.setPixelSize(10)
    code = colors.label_style == "code"
    font.setWeight(QFont.Normal if code else QFont.DemiBold)
    font.setLetterSpacing(QFont.AbsoluteSpacing, 0.0 if code else 1.6)
    return font


def section_label(text: str, parent: QWidget | None = None) -> QLabel:
    """A small section heading in the theme's style ("BỘ SƯU TẬP", or
    "// bộ_sưu_tập" for code-style themes)."""
    label = QLabel(section_text(text), parent)
    label.setFont(section_font(label.font()))
    label.setStyleSheet(f"color: {current_colors().muted_text}; background: transparent;")
    return label


class CountRowDelegate(QStyledItemDelegate):
    """See the module docstring. `section_roots=True` (the facet tree)
    draws top-level rows as section headings."""

    def __init__(
        self, parent=None, *, section_roots: bool = False, icon_for=None, tall: bool = False, code_names: bool = False,
        pill: bool = False,
    ) -> None:
        """`icon_for(index)` -> ICON_ALL / ICON_FOLDER / ICON_STAR / None
        turns on leading line icons and a pill-shaped count on the selected
        row (Walnut Library); `tall` uses its roomier row height."""
        super().__init__(parent)
        self._section_roots = section_roots
        self._icon_for = icon_for
        self._tall = tall
        # Show names in the theme's code style ("tâm_lý_học") -- only for
        # collection names, never for authors/tags (real people and words).
        self._code_names = code_names
        # Design "pill" rows: a 30 px bordered rounded button per row, upper-case display face; the selected one is
        # filled with the accent. `icon_for(index)` then returns a line_icons name (or None).
        self._pill = pill

    def _is_section(self, index) -> bool:
        return self._section_roots and not index.parent().isValid()

    def sizeHint(self, option, index) -> QSize:  # noqa: N802 -- Qt override
        size = super().sizeHint(option, index)
        if self._is_section(index):
            return QSize(size.width(), SECTION_ROW_HEIGHT)
        if self._pill:
            return QSize(size.width(), 30 if index.data(Qt.UserRole + 1) == SECTION_ITEM_ID else PILL_ROW_HEIGHT)
        return QSize(size.width(), TALL_ROW_HEIGHT if self._tall else ROW_HEIGHT)

    def paint(self, painter, option, index) -> None:
        opt = QStyleOptionViewItem(option)
        self.initStyleOption(opt, index)
        colors = current_colors()
        rect = opt.rect
        text = index.data(Qt.DisplayRole) or ""

        if self._pill:
            self._paint_pill(painter, opt, index)
            return

        painter.save()
        if self._is_section(index):
            painter.setFont(section_font(opt.font))
            painter.setPen(QColor(colors.muted_text))
            text_rect = QRect(rect.x() + 4, rect.y() + 10, rect.width() - 8, rect.height() - 10)
            painter.drawText(text_rect, Qt.AlignLeft | Qt.AlignVCenter, section_text(text, colors))
            painter.restore()
            return

        # "Selected" is either the view's own selection (collections list)
        # or a row the facet panel painted as active via its background
        # role (the facet tree has no native selection -- see
        # facet_panel.FacetPanel).
        selected = bool(opt.state & QStyle.State_Selected) or index.data(Qt.BackgroundRole) is not None
        hovered = bool(opt.state & QStyle.State_MouseOver)
        style = colors.selection_style
        if selected:
            _paint_selected_row(painter, rect, colors, style)
        elif hovered and style != "underline":
            hover = QColor(colors.selected_bg)
            hover.setAlpha(110)
            if style == "stripe":
                painter.fillRect(rect, hover)
            else:
                painter.setRenderHint(QPainter.Antialiasing)
                painter.setPen(Qt.NoPen)
                painter.setBrush(hover)
                painter.drawRoundedRect(QRectF(rect).adjusted(2, 2, -2, -2), 12, 12)

        name, count = split_count(text)
        if self._code_names:
            name = item_text(name, colors)
        text_color = QColor(colors.selected_text if selected else colors.sidebar_text)
        count_color = QColor(colors.selected_text if selected else colors.muted_text)

        pill = self._icon_for is not None and selected
        count_width = 0
        if count:
            count_font = QFont(opt.font)
            count_font.setPointSizeF(max(6.0, opt.font.pointSizeF() * 0.86))
            metrics = QFontMetrics(count_font)
            shown_count = f"{int(count):,}".replace(",", ".")
            count_width = metrics.horizontalAdvance(shown_count) + 12
            count_rect = QRect(rect.right() - count_width - 4, rect.y(), count_width, rect.height())
            if pill:
                # The selected row's count as a small tinted pill.
                pill_width = metrics.horizontalAdvance(shown_count) + 16
                pill_height = metrics.height() + 4
                count_rect = QRect(
                    rect.right() - pill_width - 10, rect.center().y() - pill_height // 2, pill_width, pill_height
                )
                count_width = pill_width + 6
                fill = QColor(colors.accent)
                fill.setAlpha(34)
                painter.setRenderHint(QPainter.Antialiasing)
                painter.setPen(Qt.NoPen)
                painter.setBrush(fill)
                painter.drawRoundedRect(QRectF(count_rect), pill_height / 2, pill_height / 2)
                count_color = QColor(colors.accent)
            painter.setFont(count_font)
            painter.setPen(count_color)
            painter.drawText(count_rect, Qt.AlignCenter if pill else Qt.AlignRight | Qt.AlignVCenter, shown_count)

        name_left = rect.x() + 12
        icon_kind = self._icon_for(index) if self._icon_for is not None else None
        if icon_kind:
            icon_rect = QRectF(rect.x() + 14, rect.center().y() - _ICON_SIZE / 2, _ICON_SIZE, _ICON_SIZE)
            _paint_line_icon(painter, icon_kind, icon_rect, QColor(colors.accent if selected else colors.muted_text))
            name_left = int(icon_rect.right()) + 10

        name_font = QFont(opt.font)
        if selected and colors.font_weight >= 400:
            name_font.setWeight(QFont.DemiBold)
        painter.setFont(name_font)
        painter.setPen(text_color)
        name_rect = QRect(name_left, rect.y(), rect.right() - name_left - count_width - 8, rect.height())
        shown = QFontMetrics(name_font).elidedText(name, Qt.ElideRight, name_rect.width())
        painter.drawText(name_rect, Qt.AlignLeft | Qt.AlignVCenter, shown)
        if selected and style == "underline":
            # A thin accent rule under just the name (Japandi): no band.
            metrics = QFontMetrics(name_font)
            text_width = metrics.horizontalAdvance(shown)
            baseline_y = rect.center().y() + metrics.height() // 2 + 3
            painter.fillRect(QRect(name_left, baseline_y, text_width, 1), QColor(colors.selected_border))
        painter.restore()


    def _paint_pill(self, painter, opt, index) -> None:
        tm = theme_manager()
        if index.data(Qt.UserRole + 1) == SECTION_ITEM_ID:
            painter.save()
            font = section_font(opt.font)
            painter.setFont(font)
            painter.setPen(QColor(tm.token("ink3")))
            area = QRectF(opt.rect).adjusted(4, 8, -4, 0)
            painter.drawText(area, Qt.AlignLeft | Qt.AlignVCenter, section_text(index.data(Qt.DisplayRole) or ""))
            painter.drawPixmap(QPointF(area.right() - 14, area.center().y() - 7), icon_pixmap("plus", tm.token("ink2"), 14))
            painter.restore()
            return
        selected = bool(opt.state & QStyle.State_Selected)
        hovered = bool(opt.state & QStyle.State_MouseOver)
        rect = QRectF(opt.rect).adjusted(0, 2, -1, -2)  # 30 px pill inside the 34 px row
        painter.save()
        painter.setRenderHint(QPainter.Antialiasing)
        border = QColor(tm.token("accent") if selected or hovered else tm.token("line2"))
        painter.setPen(QPen(border, 1))
        painter.setBrush(QColor(tm.token("accent")) if selected else Qt.NoBrush)
        painter.drawRoundedRect(rect.adjusted(0.5, 0.5, -0.5, -0.5), 6, 6)
        fg = QColor(tm.token("accentink") if selected else tm.token("ink"))
        faint = QColor(tm.token("accentink") if selected else tm.token("ink3"))
        name, count = split_count(index.data(Qt.DisplayRole) or "")
        left = rect.x() + 12
        icon_name = self._icon_for(index) if self._icon_for is not None else None
        if icon_name:
            pixmap = icon_pixmap(icon_name, fg, 12)
            painter.drawPixmap(QPointF(left, rect.center().y() - 6), pixmap)
            left += 18
        right = rect.right() - 10
        if count:
            count_font = QFont(opt.font)
            count_font.setPixelSize(11)
            painter.setFont(count_font)
            painter.setPen(faint)
            shown = f"{int(count):,}".replace(",", ".")
            width = QFontMetrics(count_font).horizontalAdvance(shown)
            painter.drawText(QRectF(right - width, rect.y(), width, rect.height()), Qt.AlignRight | Qt.AlignVCenter, shown)
            right -= width + 8
        font = section_font(opt.font)
        font.setPixelSize(11)  # pills read a little larger than group labels
        painter.setFont(font)
        painter.setPen(fg)
        label = item_text(name, current_colors()).upper()
        elided = QFontMetrics(font).elidedText(label, Qt.ElideRight, max(10, int(right - left)))
        painter.drawText(QRectF(left, rect.y(), right - left, rect.height()), Qt.AlignLeft | Qt.AlignVCenter, elided)
        painter.restore()


def _paint_line_icon(painter, kind: str, rect: QRectF, color: QColor) -> None:
    """Small outline icons for the sidebar rows -- drawn rather than emoji,
    so they take the row's colour (muted, or accent when selected)."""
    painter.save()
    painter.setRenderHint(QPainter.Antialiasing)
    pen = QPen(color)
    pen.setWidthF(1.4)
    pen.setJoinStyle(Qt.RoundJoin)
    painter.setPen(pen)
    painter.setBrush(Qt.NoBrush)
    x, y, w, h = rect.x(), rect.y(), rect.width(), rect.height()
    if kind == ICON_ALL:
        painter.drawRoundedRect(QRectF(x + 1, y + 2, w - 2, h - 4), 2, 2)
    elif kind == ICON_STAR:
        import math

        cx, cy = x + w / 2, y + h / 2 + 0.5
        points = []
        for i in range(10):
            radius = (w / 2) if i % 2 == 0 else (w / 4.4)
            angle = math.radians(-90 + i * 36)
            points.append(QPointF(cx + radius * math.cos(angle), cy + radius * math.sin(angle)))
        painter.drawPolygon(QPolygonF(points))
    else:  # folder
        path = QPainterPath()
        top, bottom = y + 3, y + h - 2
        path.moveTo(x + 1, bottom)
        path.lineTo(x + 1, top)
        path.lineTo(x + w * 0.38, top)
        path.lineTo(x + w * 0.5, top + 2.5)
        path.lineTo(x + w - 1, top + 2.5)
        path.lineTo(x + w - 1, bottom)
        path.closeSubpath()
        painter.drawPath(path)
    painter.restore()


def _paint_selected_row(painter, rect: QRect, colors, style: str) -> None:
    """The selected-row background in the theme's selection_style."""
    if style == "underline":
        return  # drawn under the name text instead
    if style == "stripe":
        painter.fillRect(rect, QColor(colors.selected_bg))
        painter.fillRect(QRect(rect.x(), rect.y(), _STRIPE, rect.height()), QColor(colors.selected_border))
        return
    painter.setRenderHint(QPainter.Antialiasing)
    inner = QRectF(rect).adjusted(2, 2, -2, -2)
    if style == "fill":
        painter.setPen(Qt.NoPen)
        painter.setBrush(QColor(colors.selected_bg))
        painter.drawRoundedRect(inner, 12, 12)
    else:  # outline
        pen = QPen(QColor(colors.selected_border))
        pen.setWidthF(1.0)
        painter.setPen(pen)
        painter.setBrush(QColor(colors.selected_bg))
        painter.drawRect(inner.adjusted(0.5, 0.5, -0.5, -0.5))
