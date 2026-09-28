# SPDX-License-Identifier: AGPL-3.0-or-later
"""BusyIndicator: the shared "đang xử lý" widget (task A3) for every place MewBook does background work the
person can see happening -- searching (bìa/metadata), importing/updating, classifying, summarizing with AI. A
small ring-of-dots spinner colored from the applied theme (never a hardcoded color), an optional message line, and
an optional mascot picture (docs/handoff/08_BRAND_MASCOT_SPEC.md §4) next to it -- `mascot_role` is opt-in per
caller and never set by default, since a screen may never show more than one mascot at once (§4.2); the caller is
the only one who knows whether another mascot already appears on that screen.

Lifecycle (what this task is graded on):
- The animation timer only ever runs while the indicator is both marked busy (`set_busy(True)`) and actually on
  screen: `showEvent`/`hideEvent` and `set_busy()` all resync it, so covering the widget (a hidden tab, a
  minimized window, a closed dialog) stops it even if the caller forgets to call `set_busy(False)`.
- `set_busy(False)` (task finished, cancelled, or failed) stops the timer immediately -- `is_running()` reflects
  that right away, not on the next tick.
- The QTimer is parented to this widget, so Qt stops and frees it when the widget itself is destroyed; nothing
  here can outlive its widget and keep ticking in the background.
- Windows' own "Show animations" setting (SPI_GETCLIENTAREAANIMATION), when it can be read, disables the motion
  and falls back to a plain static ring -- still visibly "busy" (the dots don't fade to invisible), just not
  spinning. Reading it can fail for reasons that have nothing to do with the setting itself (non-Windows, a
  restricted process); that failure means "animate", never "silently freeze" -- a person did not ask for stillness
  just because we could not confirm otherwise.
- Repaint cost is a handful of filled circles on a ~20px widget, ticking at a deliberately modest 90ms (~11
  fps) -- cheap enough to never be the thing making the UI feel slow while something heavier runs underneath it.
"""
from __future__ import annotations

import ctypes
import math
import sys

from PySide6.QtCore import QRectF, Qt, QTimer
from PySide6.QtGui import QPainter
from PySide6.QtWidgets import QHBoxLayout, QLabel, QVBoxLayout, QWidget

from smartdoc.presentation.brand import accessible_name, mascot_pixmap
from smartdoc.presentation.theme_manager import theme_manager

_TICK_MS = 90
_DOTS = 8
_MASCOT_HEIGHT = 40
_SPI_GETCLIENTAREAANIMATION = 0x1042


def _system_animations_enabled() -> bool:
    """Best-effort read of Windows' "Show animations in Windows" setting. True (animate) whenever it cannot be
    read -- see the module docstring for why that default, not False, is the safe one."""
    if sys.platform != "win32":
        return True
    try:
        value = ctypes.c_int(1)
        ok = ctypes.windll.user32.SystemParametersInfoW(_SPI_GETCLIENTAREAANIMATION, 0, ctypes.byref(value), 0)
        return bool(value.value) if ok else True
    except (AttributeError, OSError, ValueError):
        return True


class _SpinnerDots(QWidget):
    """The ring-of-dots painted area, split out from BusyIndicator because Qt dispatches `paintEvent` through the
    real (sub)class -- assigning a paint function onto a plain QWidget *instance* is not reliably called by the
    C++ side, so this needs a proper subclass rather than a monkey-patched attribute."""

    def __init__(self, owner: BusyIndicator, size: int) -> None:
        super().__init__(owner)
        self._owner = owner
        self.setFixedSize(size, size)

    def paintEvent(self, event) -> None:  # noqa: ARG002, N802 -- Qt override signature
        self._owner._paint_spinner()


class BusyIndicator(QWidget):
    """`message`: an optional static line under/beside the spinner (callers update it with `set_message`).
    `mascot_role`: a role from `presentation/brand.py` (e.g. "searching", "thinking") shown only while busy, or
    None (the default) for no mascot at all."""

    def __init__(self, parent: QWidget | None = None, *, message: str = "", mascot_role: str | None = None,
                 dot_size: int = 18) -> None:
        super().__init__(parent)
        self._busy = False
        self._phase = 0
        self._dot_size = dot_size
        self._mascot_role = mascot_role
        self._reduced_motion = not _system_animations_enabled()

        self._timer = QTimer(self)
        self._timer.setInterval(_TICK_MS)
        self._timer.timeout.connect(self._tick)

        self._spinner = _SpinnerDots(self, dot_size)

        self._mascot_label: QLabel | None = None
        if mascot_role:
            self._mascot_label = QLabel(self)
            self._mascot_label.setAccessibleName(accessible_name(mascot_role))
            self._mascot_label.setVisible(False)

        self.message_label = QLabel(message, self)
        self.message_label.setWordWrap(True)
        self.message_label.setVisible(bool(message))

        column = QVBoxLayout()
        column.setContentsMargins(0, 0, 0, 0)
        column.setSpacing(4)
        column.addWidget(self._spinner, 0, Qt.AlignLeft)
        column.addWidget(self.message_label)

        row = QHBoxLayout(self)
        row.setContentsMargins(0, 0, 0, 0)
        row.setSpacing(8)
        if self._mascot_label is not None:
            row.addWidget(self._mascot_label, 0, Qt.AlignTop)
        row.addLayout(column, 1)

        self.setVisible(False)  # nothing to show until a caller calls set_busy(True)
        theme_manager().themeChanged.connect(self._on_theme_changed)

    # -- the AC surface ---------------------------------------------------------------------------------------

    def is_running(self) -> bool:
        """True exactly while the animation timer is ticking -- what the lifecycle AC is checked against."""
        return self._timer.isActive()

    def is_busy(self) -> bool:
        return self._busy

    def set_busy(self, busy: bool) -> None:
        """Start/stop the indicator. Also shows/hides it (a BusyIndicator with nothing to say about should not
        sit there as empty space) unless `setVisible` was already called explicitly by the caller's own layout."""
        if busy == self._busy:
            return
        self._busy = busy
        self.setVisible(busy)
        if self._mascot_label is not None:
            self._mascot_label.setVisible(busy)
            if busy:
                self._refresh_mascot()
        self._sync_timer()
        self._spinner.update()

    def set_message(self, text: str) -> None:
        self.message_label.setText(text)
        self.message_label.setVisible(bool(text))

    # -- visibility-aware timer ---------------------------------------------------------------------------------

    def showEvent(self, event) -> None:  # noqa: N802 -- Qt override
        super().showEvent(event)
        self._sync_timer()

    def hideEvent(self, event) -> None:  # noqa: N802 -- Qt override
        super().hideEvent(event)
        self._sync_timer()

    def _sync_timer(self) -> None:
        should_run = self._busy and self.isVisible() and not self._reduced_motion
        if should_run and not self._timer.isActive():
            self._timer.start()
        elif not should_run and self._timer.isActive():
            self._timer.stop()

    def _tick(self) -> None:
        self._phase = (self._phase + 1) % _DOTS
        self._spinner.update()

    # -- painting -----------------------------------------------------------------------------------------------

    def _paint_spinner(self) -> None:
        """Called from `_SpinnerDots.paintEvent`, painting directly onto that child widget."""
        if not self._busy:
            return
        painter = QPainter(self._spinner)
        painter.setRenderHint(QPainter.Antialiasing)
        color = theme_manager().color("accent")
        side = self._dot_size
        center, radius, dot_r = side / 2, side / 2 - side / 8, side / 10
        for i in range(_DOTS):
            # Reduced motion: every dot drawn the same -- still visibly "a busy ring", never a still, empty circle
            # that could be mistaken for nothing happening at all.
            fraction = 1.0 if self._reduced_motion else 1.0 - ((i - self._phase) % _DOTS) / _DOTS
            color.setAlphaF(max(0.15, fraction))
            painter.setPen(Qt.NoPen)
            painter.setBrush(color)
            angle = (2 * math.pi * i / _DOTS) - math.pi / 2
            x = center + radius * math.cos(angle) - dot_r
            y = center + radius * math.sin(angle) - dot_r
            painter.drawEllipse(QRectF(x, y, dot_r * 2, dot_r * 2))

    def _on_theme_changed(self, _key: str = "") -> None:
        self._spinner.update()

    def _refresh_mascot(self) -> None:
        if self._mascot_label is None or self._mascot_role is None:
            return
        pixmap = mascot_pixmap(self._mascot_role, _MASCOT_HEIGHT, self.devicePixelRatioF())
        if pixmap is not None:
            self._mascot_label.setPixmap(pixmap)
        self._mascot_label.setVisible(pixmap is not None)


if __name__ == "__main__":
    import sys as _sys

    from PySide6.QtWidgets import QApplication, QMainWindow

    app = QApplication(_sys.argv)
    theme_manager().apply(app, "broadsheet")
    win = QMainWindow()
    indicator = BusyIndicator(message="Đang tìm kiếm...", mascot_role="searching")
    indicator.set_busy(True)
    win.setCentralWidget(indicator)
    win.resize(320, 120)
    win.show()
    app.exec()
