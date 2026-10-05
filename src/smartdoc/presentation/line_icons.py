# SPDX-License-Identifier: AGPL-3.0-or-later
"""Small line icons drawn with QPainter, in the colour the theme asks for.

Why drawn, not files: the design uses one thin outline style in every theme (and in the status bar's badges, where a
*shape* carries the state), so an icon must take any colour token and stay sharp at any DPI. Nothing is bundled and
there is no emoji, which renders differently on every machine. Each icon is a function drawing on a 16x16 grid.
"""
from __future__ import annotations

from collections.abc import Callable
from functools import lru_cache

from PySide6.QtCore import QPointF, QRectF, Qt
from PySide6.QtGui import QColor, QIcon, QPainter, QPainterPath, QPen, QPixmap

from smartdoc.presentation.theme_manager import theme_manager

_GRID = 16.0


def _p(x: float, y: float) -> QPointF:
    return QPointF(x, y)


def _plus(p: QPainter) -> None:
    p.drawLine(_p(8, 3), _p(8, 13))
    p.drawLine(_p(3, 8), _p(13, 8))


def _search(p: QPainter) -> None:
    p.drawEllipse(QRectF(2.5, 2.5, 8, 8))
    p.drawLine(_p(9, 9), _p(13.5, 13.5))


def _grid(p: QPainter) -> None:
    for x in (2.5, 9):
        for y in (2.5, 9):
            p.drawRoundedRect(QRectF(x, y, 4.5, 4.5), 1, 1)


def _table(p: QPainter) -> None:
    for y in (4, 8, 12):
        p.drawLine(_p(2.5, y), _p(13.5, y))


def _sort(p: QPainter) -> None:
    p.drawLine(_p(5, 3), _p(5, 13))
    p.drawLine(_p(5, 13), _p(3, 11))
    p.drawLine(_p(5, 13), _p(7, 11))
    p.drawLine(_p(10, 4), _p(14, 4))
    p.drawLine(_p(10, 8), _p(13, 8))
    p.drawLine(_p(10, 12), _p(12, 12))


def _tools(p: QPainter) -> None:
    p.drawLine(_p(3, 13), _p(9, 7))
    p.drawEllipse(QRectF(8, 2, 5, 5))
    p.drawLine(_p(3, 13), _p(4.5, 13.5))


def _panel(p: QPainter) -> None:
    p.drawRoundedRect(QRectF(2, 3, 12, 10), 1.5, 1.5)
    p.drawLine(_p(10, 3), _p(10, 13))


def _gear(p: QPainter) -> None:
    p.drawEllipse(QRectF(5.5, 5.5, 5, 5))
    for i in range(8):
        p.save()
        p.translate(8, 8)
        p.rotate(45 * i)
        p.drawLine(_p(0, -5.5), _p(0, -7))
        p.restore()


def _pen(p: QPainter) -> None:
    p.drawLine(_p(3, 13), _p(4, 9.5))
    p.drawLine(_p(4, 9.5), _p(10.5, 3))
    p.drawLine(_p(10.5, 3), _p(13, 5.5))
    p.drawLine(_p(13, 5.5), _p(6.5, 12))
    p.drawLine(_p(6.5, 12), _p(3, 13))


def _book(p: QPainter) -> None:
    p.drawRoundedRect(QRectF(3, 2.5, 10, 11), 1, 1)
    p.drawLine(_p(6, 2.5), _p(6, 13.5))
    p.drawLine(_p(8, 6), _p(11, 6))


def _star(p: QPainter) -> None:
    p.drawPath(_star_path())


def _star_fill(p: QPainter) -> None:
    p.setBrush(p.pen().color())
    p.drawPath(_star_path())


def _star_path() -> QPainterPath:
    import math

    path = QPainterPath()
    for i in range(10):
        radius = 6 if i % 2 == 0 else 2.6
        angle = -math.pi / 2 + i * math.pi / 5
        point = _p(8 + radius * math.cos(angle), 8.4 + radius * math.sin(angle))
        path.moveTo(point) if i == 0 else path.lineTo(point)
    path.closeSubpath()
    return path


def _cloud(p: QPainter) -> None:
    path = QPainterPath()
    path.moveTo(4.5, 12)
    path.cubicTo(1.5, 12, 1.5, 7.5, 5, 7.5)
    path.cubicTo(5.5, 4, 11, 4, 11.5, 7.5)
    path.cubicTo(14.5, 7.5, 14.5, 12, 11.5, 12)
    path.closeSubpath()
    p.drawPath(path)


def _bot(p: QPainter) -> None:
    p.drawRoundedRect(QRectF(3, 5, 10, 8), 2, 2)
    p.drawLine(_p(8, 5), _p(8, 2.5))
    p.drawPoint(_p(6, 9))
    p.drawPoint(_p(10, 9))


def _globe(p: QPainter) -> None:
    p.drawEllipse(QRectF(2.5, 2.5, 11, 11))
    p.drawEllipse(QRectF(5.5, 2.5, 5, 11))
    p.drawLine(_p(2.5, 8), _p(13.5, 8))


def _chevron_down(p: QPainter) -> None:
    p.drawPolyline([_p(4, 6), _p(8, 10), _p(12, 6)])


def _chevron_right(p: QPainter) -> None:
    p.drawPolyline([_p(6, 4), _p(10, 8), _p(6, 12)])


def _chevron_left(p: QPainter) -> None:
    p.drawPolyline([_p(10, 4), _p(6, 8), _p(10, 12)])


def _close(p: QPainter) -> None:
    p.drawLine(_p(4, 4), _p(12, 12))
    p.drawLine(_p(12, 4), _p(4, 12))


def _refresh(p: QPainter) -> None:
    p.drawArc(QRectF(3, 3, 10, 10), 40 * 16, 270 * 16)
    p.drawPolyline([_p(11.5, 1.5), _p(12, 4.5), _p(9, 5)])


def _image(p: QPainter) -> None:
    p.drawRoundedRect(QRectF(2.5, 3, 11, 10), 1.5, 1.5)
    p.drawPolyline([_p(3, 12), _p(7, 8), _p(10, 11), _p(13, 8)])


def _send(p: QPainter) -> None:
    p.drawLine(_p(3, 8), _p(13, 3))
    p.drawLine(_p(13, 3), _p(9, 13))
    p.drawLine(_p(9, 13), _p(7.5, 9))
    p.drawLine(_p(7.5, 9), _p(3, 8))


def _check(p: QPainter) -> None:
    p.drawPolyline([_p(3.5, 8.5), _p(6.5, 11.5), _p(12.5, 4.5)])


def _folder(p: QPainter) -> None:
    p.drawPolyline([_p(2.5, 12.5), _p(2.5, 4), _p(6.5, 4), _p(8, 5.5), _p(13.5, 5.5), _p(13.5, 12.5), _p(2.5, 12.5)])


def _warn(p: QPainter) -> None:
    p.drawPolygon([_p(8, 2.5), _p(14, 13), _p(2, 13)])
    p.drawLine(_p(8, 6.5), _p(8, 9.5))
    p.drawPoint(_p(8, 11.3))


def _question(p: QPainter) -> None:
    path = QPainterPath()
    path.moveTo(5, 5.5)
    path.cubicTo(5, 2.3, 11, 2.3, 11, 5.8)
    path.cubicTo(11, 8.3, 8, 8, 8, 10.5)
    p.drawPath(path)
    p.drawPoint(_p(8, 13.2))


def _filter(p: QPainter) -> None:
    p.drawPolygon([_p(2.5, 3.5), _p(13.5, 3.5), _p(9.5, 8.5), _p(9.5, 13), _p(6.5, 11.5), _p(6.5, 8.5)])


def _bolt(p: QPainter) -> None:
    p.drawPolyline([_p(9, 2), _p(4, 9), _p(8, 9), _p(7, 14), _p(12, 6.5), _p(8, 6.5), _p(9, 2)])


def _link(p: QPainter) -> None:
    p.drawRoundedRect(QRectF(2, 6, 7, 4), 2, 2)
    p.drawRoundedRect(QRectF(7, 6, 7, 4), 2, 2)


def _lock(p: QPainter) -> None:
    p.drawRoundedRect(QRectF(3.5, 7, 9, 6.5), 1.5, 1.5)
    p.drawArc(QRectF(5, 2.5, 6, 6), 0, 180 * 16)


def _wifi(p: QPainter) -> None:
    p.drawArc(QRectF(2, 3, 12, 12), 45 * 16, 90 * 16)
    p.drawArc(QRectF(4.5, 6, 7, 7), 45 * 16, 90 * 16)
    p.drawPoint(_p(8, 12))


def _user(p: QPainter) -> None:
    p.drawEllipse(QRectF(5.5, 2.5, 5, 5))
    p.drawArc(QRectF(3, 9, 10, 8), 0, 180 * 16)


def _tag(p: QPainter) -> None:
    p.drawPolygon([_p(2.5, 8), _p(8, 2.5), _p(13.5, 2.5), _p(13.5, 8), _p(8, 13.5)])
    p.drawPoint(_p(11, 5))


def _file(p: QPainter) -> None:
    p.drawPolyline([_p(4, 2.5), _p(10, 2.5), _p(12.5, 5), _p(12.5, 13.5), _p(4, 13.5), _p(4, 2.5)])
    p.drawPolyline([_p(10, 2.5), _p(10, 5), _p(12.5, 5)])


def _eye(p: QPainter) -> None:
    path = QPainterPath()
    path.moveTo(1.5, 8)
    path.cubicTo(4, 3.5, 12, 3.5, 14.5, 8)
    path.cubicTo(12, 12.5, 4, 12.5, 1.5, 8)
    p.drawPath(path)
    p.drawEllipse(QRectF(6, 6, 4, 4))


def _palette(p: QPainter) -> None:
    p.drawEllipse(QRectF(2, 2, 12, 12))
    for x, y in ((5.5, 6), (8, 4.5), (10.5, 6)):
        p.drawPoint(_p(x, y))


def _archive(p: QPainter) -> None:
    p.drawRoundedRect(QRectF(2, 3, 12, 3), 1, 1)
    p.drawPolyline([_p(3, 6), _p(3, 13), _p(13, 13), _p(13, 6)])
    p.drawLine(_p(6.5, 9), _p(9.5, 9))


def _download(p: QPainter) -> None:
    p.drawLine(_p(8, 2.5), _p(8, 10))
    p.drawPolyline([_p(5, 7.5), _p(8, 10.5), _p(11, 7.5)])
    p.drawPolyline([_p(3, 11.5), _p(3, 13.5), _p(13, 13.5), _p(13, 11.5)])


def _shield(p: QPainter) -> None:
    path = QPainterPath()
    path.moveTo(8, 2)
    path.lineTo(13, 4)
    path.lineTo(13, 8)
    path.cubicTo(13, 11, 10.5, 13, 8, 14)
    path.cubicTo(5.5, 13, 3, 11, 3, 8)
    path.lineTo(3, 4)
    path.closeSubpath()
    p.drawPath(path)


def _expand(p: QPainter) -> None:
    for x, y, dx, dy in ((2.5, 2.5, 1, 1), (13.5, 2.5, -1, 1), (2.5, 13.5, 1, -1), (13.5, 13.5, -1, -1)):
        p.drawPolyline([_p(x + 3.5 * dx, y), _p(x, y), _p(x, y + 3.5 * dy)])


def _trash(p: QPainter) -> None:
    p.drawRoundedRect(QRectF(4, 5, 8, 9), 1, 1)
    p.drawLine(_p(2.5, 5), _p(13.5, 5))
    p.drawLine(_p(6, 3), _p(10, 3))
    p.drawLine(_p(6.5, 7.5), _p(6.5, 12))
    p.drawLine(_p(9.5, 7.5), _p(9.5, 12))


def _facebook(p: QPainter) -> None:
    """Line-art nod to the Facebook mark (a rounded badge + its lower-case "f"), not the brand's own coloured logo --
    every icon here is a monoline glyph recoloured by the theme, and a literal blue "f" would fight that."""
    p.drawRoundedRect(QRectF(2, 2, 12, 12), 3, 3)
    path = QPainterPath()
    path.moveTo(10.3, 5.3)
    path.cubicTo(9, 5.3, 8.4, 6, 8.4, 7.3)
    path.lineTo(8.4, 12.3)
    p.drawPath(path)
    p.drawLine(_p(7, 8.5), _p(9.8, 8.5))


_DRAWERS: dict[str, Callable[[QPainter], None]] = {
    "plus": _plus, "search": _search, "grid": _grid, "table": _table, "sort": _sort, "tools": _tools,
    "panel": _panel, "gear": _gear, "pen": _pen, "book": _book, "star": _star, "star_fill": _star_fill,
    "cloud": _cloud, "bot": _bot, "globe": _globe, "chevron_down": _chevron_down, "chevron_right": _chevron_right, "chevron_left": _chevron_left,
    "close": _close, "refresh": _refresh, "image": _image, "send": _send, "check": _check, "folder": _folder,
    "warn": _warn, "question": _question, "filter": _filter, "user": _user, "tag": _tag, "file": _file, "bolt": _bolt, "link": _link, "lock": _lock, "wifi": _wifi,
    "eye": _eye, "expand": _expand, "palette": _palette, "archive": _archive, "download": _download, "shield": _shield,
    "trash": _trash, "facebook": _facebook,
}
ICON_NAMES = tuple(_DRAWERS)


@lru_cache(maxsize=512)
def _render(name: str, rgba: int, size: int, scale: float) -> QPixmap:
    pixmap = QPixmap(int(size * scale), int(size * scale))
    pixmap.setDevicePixelRatio(scale)
    pixmap.fill(Qt.transparent)
    painter = QPainter(pixmap)
    painter.setRenderHint(QPainter.Antialiasing)
    painter.scale(size / _GRID, size / _GRID)
    pen = QPen(QColor.fromRgba(rgba), 1.4)
    pen.setCapStyle(Qt.RoundCap)
    pen.setJoinStyle(Qt.RoundJoin)
    painter.setPen(pen)
    painter.setBrush(Qt.NoBrush)
    _DRAWERS[name](painter)
    painter.end()
    return pixmap


def icon_pixmap(name: str, color: QColor | str | None = None, size: int = 16, scale: float = 2.0) -> QPixmap:
    """The icon as a pixmap; `color` is a QColor / hex string, or the theme's `ink2` when omitted."""
    if name not in _DRAWERS:
        raise KeyError(f"unknown icon {name!r}")
    qcolor = QColor(color) if color is not None else theme_manager().color("ink2")
    return _render(name, qcolor.rgba(), size, scale)


def line_icon(name: str, color: QColor | str | None = None, size: int = 16) -> QIcon:
    return QIcon(icon_pixmap(name, color, size))


if __name__ == "__main__":
    import sys

    from PySide6.QtWidgets import QApplication, QHBoxLayout, QLabel, QWidget

    demo_app = QApplication(sys.argv)
    box = QWidget()
    row = QHBoxLayout(box)
    for icon_name in ICON_NAMES:
        label = QLabel()
        label.setPixmap(icon_pixmap(icon_name, "#2F4F7F", 24))
        row.addWidget(label)
    box.show()
    sys.exit(demo_app.exec())
