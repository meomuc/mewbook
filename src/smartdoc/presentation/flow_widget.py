"""A widget that lays its children out left to right and wraps to a new line
when the row is full -- what a cloud of filter chips needs.

Deliberately a plain QWidget placing children itself, not a QLayout subclass:
a Python QLayout hands layout items back to C++ on removal and PySide then
frees them twice, which crashed when chips were removed. Parent layouts still
give it the right height for its width through heightForWidth.
"""
from __future__ import annotations

from PySide6.QtCore import QEvent, QRect, QSize
from PySide6.QtWidgets import QSizePolicy, QWidget


class FlowWidget(QWidget):
    def __init__(self, parent: QWidget | None = None, *, h_spacing: int = 6, v_spacing: int = 6) -> None:
        super().__init__(parent)
        self._h_spacing = h_spacing
        self._v_spacing = v_spacing
        self._items: list[QWidget] = []
        policy = QSizePolicy(QSizePolicy.Preferred, QSizePolicy.Preferred)
        policy.setHeightForWidth(True)
        self.setSizePolicy(policy)

    def set_widgets(self, widgets: list[QWidget]) -> None:
        """The children to show, in order. Children not listed stay where they are
        but are ignored -- the caller hides or deletes them."""
        self._items = list(widgets)
        self._relayout()
        self.updateGeometry()

    def hasHeightForWidth(self) -> bool:  # noqa: N802 -- Qt override
        return True

    def heightForWidth(self, width: int) -> int:  # noqa: N802 -- Qt override
        return self._arrange(width, apply=False)

    def sizeHint(self) -> QSize:  # noqa: N802 -- Qt override
        width = self.width() if self.width() > 0 else 240
        return QSize(width, self.heightForWidth(width))

    def minimumSizeHint(self) -> QSize:  # noqa: N802 -- Qt override
        widest = max((w.sizeHint().width() for w in self._items if not w.isHidden()), default=0)
        return QSize(widest, self.heightForWidth(max(widest, 1)))

    def resizeEvent(self, event) -> None:  # noqa: N802 -- Qt override
        super().resizeEvent(event)
        self._relayout()
        self.updateGeometry()

    def event(self, event) -> bool:  # noqa: N802 -- Qt override
        # A child's text changed (its size hint with it): place everything again.
        if event.type() == QEvent.LayoutRequest:
            self._relayout()
        return super().event(event)

    def _relayout(self) -> None:
        self._arrange(self.width(), apply=True)

    def _arrange(self, width: int, *, apply: bool) -> int:
        x = y = line_height = 0
        for widget in self._items:
            if widget.isHidden():
                continue
            hint = widget.sizeHint()
            if x > 0 and x + hint.width() > width:
                x = 0
                y += line_height + self._v_spacing
                line_height = 0
            if apply:
                widget.setGeometry(QRect(x, y, hint.width(), hint.height()))
            x += hint.width() + self._h_spacing
            line_height = max(line_height, hint.height())
        return y + line_height


if __name__ == "__main__":
    import sys

    from PySide6.QtWidgets import QApplication, QPushButton

    app = QApplication(sys.argv)
    flow = FlowWidget()
    flow.set_widgets([QPushButton(label, flow) for label in ("Tiểu thuyết", "Truyện ngắn", "Lịch sử", "Tâm lý", "Khoa học")])
    flow.resize(220, 120)
    flow.show()
    sys.exit(app.exec())
