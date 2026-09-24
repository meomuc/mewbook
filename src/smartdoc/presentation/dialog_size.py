"""Keeps every popup window inside the screen it opens on.

Qt sizes a dialog from its layout's size hint, and a few things in this app
blow that hint far past anything sensible: a long single-line file path, a
message box quoting a raw API error, a list with hundreds of rows, a tab
full of instructions. The result was dialogs taller/wider than the display,
with their buttons pushed off-screen where they can't be clicked at all.

Capping each dialog individually (setMaximumSize with hardcoded pixels)
was both fragile -- every new dialog has to remember to do it -- and wrong
on any screen that isn't the one those numbers were picked on. Instead,
one application-wide event filter catches *any* dialog as it is shown
(including Qt's own QMessageBox/QFileDialog, which this app never
constructs directly and so could never have capped by hand) and constrains
it relative to that screen's available geometry.

A dialog that already set its own smaller maximum (e.g. a fixed-size QR
popup) keeps it -- this only ever tightens the bound, never loosens it.
"""
from __future__ import annotations

from PySide6.QtCore import QEvent, QObject, QRect
from PySide6.QtWidgets import QApplication, QDialog, QLabel, QLayout

# Fractions of the *available* screen area (i.e. excluding the taskbar).
# Not 100%: a popup that exactly fills the screen reads as a broken
# maximized window rather than as a dialog.
_MAX_WIDTH_RATIO = 0.80
_MAX_HEIGHT_RATIO = 0.85


def constrain_to_screen(widget) -> None:
    """Caps `widget` to a fraction of its screen, and shrinks it on the
    spot if it is already larger than that.

    setMaximumSize alone is not enough, which is why the naive version of
    this didn't work: a layout's *minimum* size wins over the widget's
    maximum, and one long unwrapped QLabel (a file path, a raw API error)
    pushes that layout minimum past any cap. So this also turns the
    offending labels into wrapping ones and drops the layout's
    minimum-size constraint, which is what actually lets the cap bind.
    """
    screen = widget.screen() or QApplication.primaryScreen()
    if screen is None:
        return
    available = screen.availableGeometry()
    max_width = int(available.width() * _MAX_WIDTH_RATIO)
    max_height = int(available.height() * _MAX_HEIGHT_RATIO)

    if widget.sizeHint().width() > max_width:
        _wrap_long_labels(widget, max_width)

    layout = widget.layout()
    if layout is not None and layout.minimumSize().width() > max_width:
        # SetDefaultConstraint (the default) forces the widget's minimum
        # size up to the layout's -- which is exactly what was overriding
        # the cap below.
        layout.setSizeConstraint(QLayout.SetNoConstraint)
        widget.setMinimumSize(min(widget.minimumWidth(), max_width), min(widget.minimumHeight(), max_height))

    widget.setMaximumSize(
        min(widget.maximumWidth(), max_width),
        min(widget.maximumHeight(), max_height),
    )
    if widget.width() > max_width or widget.height() > max_height:
        widget.resize(min(widget.width(), max_width), min(widget.height(), max_height))


# Room kept for the window's own frame (title bar and borders) when Qt cannot tell yet how big it is -- a window
# that was never shown has no frame measured. Generous on purpose: too small a window is harmless, one over
# the taskbar is not.
_DEFAULT_FRAME_WIDTH = 16
_DEFAULT_FRAME_HEIGHT = 48


def _usable_area(window) -> QRect:
    """The part of the window's screen the taskbar does not cover (a seam so tests can pose as any display)."""
    screen = window.screen() or QApplication.primaryScreen()
    return screen.availableGeometry() if screen is not None else QRect(0, 0, 1280, 720)


def fit_window_to_screen(window) -> None:
    """Keeps a top-level window (main window, reader) inside the usable area of its screen: shrinks it if its
    size, frame included, is larger than that area, and moves it back if any part sits over the taskbar.
    A window that already fits is left exactly as it is."""
    area = _usable_area(window)
    frame, geometry = window.frameGeometry(), window.geometry()
    extra_w = frame.width() - geometry.width() or _DEFAULT_FRAME_WIDTH
    extra_h = frame.height() - geometry.height() or _DEFAULT_FRAME_HEIGHT
    width = min(window.width(), area.width() - extra_w)
    height = min(window.height(), area.height() - extra_h)
    if (width, height) != (window.width(), window.height()):
        window.setMinimumSize(min(window.minimumWidth(), width), min(window.minimumHeight(), height))
        window.resize(width, height)

    frame = window.frameGeometry()
    frame_w, frame_h = max(frame.width(), width + extra_w), max(frame.height(), height + extra_h)
    x = min(max(frame.x(), area.left()), area.right() + 1 - frame_w)
    y = min(max(frame.y(), area.top()), area.bottom() + 1 - frame_h)
    if (x, y) != (frame.x(), frame.y()):
        window.move(x, y)


def _wrap_long_labels(widget, max_width: int) -> None:
    """Turns on word wrap for any non-wrapping label wide enough to be
    what's forcing the dialog oversize -- wrapped text keeps the dialog
    readable, where simply clipping it would hide half the message."""
    for label in widget.findChildren(QLabel):
        if not label.wordWrap() and label.sizeHint().width() > max_width // 2:
            label.setWordWrap(True)


class DialogSizeGuard(QObject):
    """Application-wide event filter -- install once on the QApplication
    (see app.py) and every dialog shown from then on is constrained."""

    def eventFilter(self, watched, event) -> bool:  # noqa: N802 -- Qt override
        # Cheap int compare first: this filter sees every event in the
        # app, and Show events are a vanishingly small fraction of them.
        if event.type() == QEvent.Show and isinstance(watched, QDialog):
            constrain_to_screen(watched)
        return False  # never consume the event -- this only observes


if __name__ == "__main__":
    import sys

    from PySide6.QtWidgets import QLabel, QVBoxLayout

    app = QApplication(sys.argv)
    guard = DialogSizeGuard()
    app.installEventFilter(guard)

    dialog = QDialog()
    layout = QVBoxLayout(dialog)
    # A deliberately absurd size hint, the kind a long unwrapped label produces.
    layout.addWidget(QLabel("x" * 4000, dialog))
    dialog.show()
    app.processEvents()

    screen_size = app.primaryScreen().availableGeometry()
    print(f"screen: {screen_size.width()}x{screen_size.height()}, dialog: {dialog.width()}x{dialog.height()}")
    assert dialog.width() <= int(screen_size.width() * _MAX_WIDTH_RATIO)
    print("DialogSizeGuard OK")
