# SPDX-License-Identifier: AGPL-3.0-or-later
"""Theme ornaments: the optional decoration a theme package asks for in its `ornaments` block (theme standard v1).

Every style is implemented ONCE here, shared by all themes and driven only by the parameters in `theme.json`; a widget
never asks "which theme is this?" -- it asks `theme_manager().ornament("shelf")` (through the helpers below) and paints
what comes back. A block that is missing, or a style that is not recognised, means the flat default (the look every
theme had before ornaments existed) plus a one-time warning -- never a broken window.

  shelf        flat | wood | glass  (+ brackets)   the board under each row of books
  frame        none | wood                          group labels of the sidebar, the detail panel header
  notice       card | chalkboard                    import summary, missing-files strip
  cover_frame  none | wood | line                   the border around the big cover in the detail panel
"""
from __future__ import annotations

import logging

from PySide6.QtCore import QRect, QRectF, Qt
from PySide6.QtGui import QColor, QLinearGradient, QPainter, QPen

from smartdoc.presentation.theme_manager import ThemeManager, parse_color

logger = logging.getLogger(__name__)

DEFAULT_SHELF_THICKNESS = 6
_STYLES = {
    "shelf": ("flat", "wood", "glass"),
    "frame": ("none", "wood"),
    "notice": ("card", "chalkboard"),
    "cover_frame": ("none", "wood", "line"),
}
_DEFAULT_STYLE = {"shelf": "flat", "frame": "none", "notice": "card", "cover_frame": "none"}
_warned: set[tuple[str, str]] = set()


def spec(tm: ThemeManager, block: str) -> dict:
    """The block's parameters with an unknown style replaced by the flat default (warned about once)."""
    params = tm.ornament(block)
    style = str(params.get("style", _DEFAULT_STYLE[block]))
    if style not in _STYLES[block]:
        if (block, style) not in _warned:
            _warned.add((block, style))
            logger.warning("Theme %s: unknown %s style %r, using the flat default", tm.key, block, style)
        params["style"] = _DEFAULT_STYLE[block]
    else:
        params["style"] = style
    return params


def _mix(a: QColor, b: QColor, amount: float) -> QColor:
    """`a` moved `amount` (0-1) of the way to `b`."""
    return QColor(round(a.red() + (b.red() - a.red()) * amount), round(a.green() + (b.green() - a.green()) * amount),
                  round(a.blue() + (b.blue() - a.blue()) * amount))


# -- shelf --------------------------------------------------------------------------------------------------------


def shelf_thickness(tm: ThemeManager) -> int:
    """The board's height in px (the layout of the shelf view uses it too)."""
    return int(spec(tm, "shelf").get("thickness", DEFAULT_SHELF_THICKNESS))


def paint_shelf(painter: QPainter, rect: QRect, tm: ThemeManager) -> None:
    """The board itself. `rect.height()` is the thickness; the soft shadow underneath belongs to the caller."""
    p = spec(tm, "shelf")
    top, body = tm.color("shelftop"), tm.color("shelf")
    style = p["style"]
    if style == "glass":
        painter.fillRect(rect, QColor(body.red(), body.green(), body.blue(), round(255 * 0.6)))
        painter.fillRect(QRect(rect.left(), rect.top(), rect.width(), 1), top)
    else:
        board = QLinearGradient(0, rect.top(), 0, rect.bottom() + 1)
        board.setColorAt(0, top)
        board.setColorAt(1, body)
        painter.fillRect(rect, board)
        if style == "wood":
            painter.fillRect(QRect(rect.left(), rect.top(), rect.width(), max(1, round(rect.height() * 0.28))),
                             _mix(body, top, 0.6))  # the lit top face (28%)
            grain = QColor(parse_color(str(p["grain"]))) if p.get("grain") else _mix(body, QColor("#000000"), 0.25)
            grain.setAlpha(46)  # faint, running along the board
            painter.setPen(QPen(grain, 1))
            for y in range(rect.top() + 2, rect.bottom(), 3):
                painter.drawLine(rect.left(), y, rect.right(), y)
    if p.get("edge"):
        painter.fillRect(QRect(rect.left(), rect.bottom(), rect.width(), 1), parse_color(str(p["edge"])))
    if p.get("brackets"):
        color = parse_color(str(p.get("bracket_color") or p.get("edge") or tm.token("ink3")))
        for x in (rect.left() + 18, rect.right() - 18 - 7):  # two 7x11 supports, 18 px in from each end
            painter.fillRect(QRect(x, rect.bottom() + 1, 7, 11), color)


# -- frame / notice: style sheet snippets -----------------------------------------------------------------------------


def frame_qss(tm: ThemeManager) -> str:
    """Declarations (no selector) for a label that sits on the theme's frame; "" when the theme has none."""
    p = spec(tm, "frame")
    if p["style"] != "wood" or not (p.get("light") and p.get("dark")):
        return ""
    ink = p.get("ink") or tm.token("ink")
    return (f"color: {ink}; padding: 2px 8px; border-radius: 3px; border: 1px solid {p['dark']}; "
            f"background: qlineargradient(x1:0, y1:0, x2:0, y2:1, stop:0 {p['light']}, stop:1 {p['dark']});")


def frame_ink(tm: ThemeManager) -> str | None:
    """The text colour that goes on the frame, or None when the theme has no wood frame."""
    p = spec(tm, "frame")
    if p["style"] != "wood" or not (p.get("light") and p.get("dark")):
        return None
    return str(p.get("ink") or tm.token("ink"))


def paint_frame_band(painter: QPainter, rect: QRect, tm: ThemeManager) -> QColor | None:
    """A full-width frame band (for group headings painted by a delegate); returns the text colour to use on it, or
    None (and paints nothing) when the theme has no frame."""
    ink = frame_ink(tm)
    if ink is None:
        return None
    p = spec(tm, "frame")
    gradient = QLinearGradient(0, rect.top(), 0, rect.bottom() + 1)
    gradient.setColorAt(0, parse_color(str(p["light"])))
    gradient.setColorAt(1, parse_color(str(p["dark"])))
    painter.save()
    painter.setRenderHint(QPainter.Antialiasing)
    painter.setPen(QPen(parse_color(str(p["dark"])), 1))
    painter.setBrush(gradient)
    painter.drawRoundedRect(QRectF(rect).adjusted(0.5, 0.5, -0.5, -0.5), 3, 3)
    painter.restore()
    return parse_color(ink)


def notice_qss(tm: ThemeManager, selector: str) -> str:
    """Style sheet rules turning `selector` (a QFrame) into a chalkboard notice; "" for the ordinary card."""
    p = spec(tm, "notice")
    if p["style"] != "chalkboard" or not (p.get("bg") and p.get("frame")):
        return ""
    ink = p.get("ink") or tm.token("ink")
    return (f"{selector} {{ background: {p['bg']}; border: 7px solid {p['frame']}; border-radius: 4px; }}"
            f" {selector} QLabel {{ color: {ink}; background: transparent; }}")


# -- cover frame --------------------------------------------------------------------------------------------------------


def cover_frame_width(tm: ThemeManager) -> int:
    p = spec(tm, "cover_frame")
    return int(p.get("width", 0)) if p["style"] != "none" else 0


def paint_cover_frame(painter: QPainter, rect: QRect, tm: ThemeManager) -> None:
    """The border of `cover_frame_width()` px just inside `rect`; the cover is painted inside what is left."""
    p = spec(tm, "cover_frame")
    width = cover_frame_width(tm)
    if width <= 0:
        return
    if p["style"] == "line":
        painter.setPen(QPen(tm.color("line2"), width))
        painter.setBrush(Qt.NoBrush)
        half = width / 2
        painter.drawRect(QRectF(rect).adjusted(half, half, -half, -half))
        return
    frame = spec(tm, "frame")  # wood: the frame colours if the theme has them, else the shelf's
    light = parse_color(str(frame["light"])) if frame.get("light") else tm.color("shelftop")
    dark = parse_color(str(frame["dark"])) if frame.get("dark") else tm.color("shelf")
    gradient = QLinearGradient(0, rect.top(), 0, rect.bottom() + 1)
    gradient.setColorAt(0, light)
    gradient.setColorAt(1, dark)
    painter.setPen(Qt.NoPen)
    painter.setBrush(gradient)
    painter.drawRect(rect)
    painter.setPen(QPen(dark, 1))
    painter.setBrush(Qt.NoBrush)
    painter.drawRect(rect.adjusted(0, 0, -1, -1))
