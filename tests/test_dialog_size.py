from PySide6.QtWidgets import QDialog, QLabel, QVBoxLayout

from smartdoc.presentation.dialog_size import DialogSizeGuard, constrain_to_screen


def _screen_limits(qapp):
    available = qapp.primaryScreen().availableGeometry()
    return available.width(), available.height()


def _dialog_with_huge_label(text_length: int = 4000) -> QDialog:
    """A long, non-wrapping label is the real-world cause of a runaway
    dialog (a raw API error, a long file path): its minimum size hint
    pushes the whole layout -- and with it the dialog -- past the screen."""
    dialog = QDialog()
    layout = QVBoxLayout(dialog)
    layout.addWidget(QLabel("x" * text_length, dialog))
    return dialog


def test_oversized_dialog_is_capped_to_the_screen(qapp):
    screen_width, screen_height = _screen_limits(qapp)
    dialog = _dialog_with_huge_label()

    dialog.show()
    qapp.processEvents()
    assert dialog.width() > screen_width  # sanity: this really would overflow without help

    constrain_to_screen(dialog)
    qapp.processEvents()

    assert dialog.width() <= screen_width
    assert dialog.height() <= screen_height
    dialog.close()


def test_a_dialog_thats_too_tall_but_not_too_wide_is_capped_too(qapp):
    """Regression (task A2): the layout's SetNoConstraint relaxation used to trigger on width overflow only, so a
    dialog with many stacked rows (no single long label, so never wide) kept refusing to shrink below its content
    height -- the cap on maximumHeight had no effect because the layout kept forcing the widget back up."""
    screen_width, screen_height = _screen_limits(qapp)
    dialog = QDialog()
    layout = QVBoxLayout(dialog)
    tall = QLabel("", dialog)
    tall.setMinimumHeight(screen_height + 2000)  # tall, not wide -- unlike _dialog_with_huge_label
    layout.addWidget(tall)

    dialog.show()
    qapp.processEvents()
    assert dialog.height() > screen_height  # sanity: this really would overflow without help
    assert dialog.width() <= screen_width  # sanity: and it is NOT also too wide

    constrain_to_screen(dialog)
    qapp.processEvents()

    assert dialog.height() <= screen_height
    dialog.close()


def test_a_dialogs_own_explicit_minimum_size_is_lowered_too(qapp):
    """Regression (task A2): a dialog that sets its OWN floor directly (`self.setMinimumSize(...)`, e.g.
    SettingsDialog) never showed up in the layout's minimumSize() at all -- that only reflects the layout's
    children, not an explicit widget-level override on top of it -- so the floor was left untouched. The cap's
    maximumSize then ended up *below* that floor, and Qt honours the larger minimum, so the dialog stayed oversized."""
    screen_width, screen_height = _screen_limits(qapp)
    dialog = QDialog()
    QVBoxLayout(dialog).addWidget(QLabel("ngắn"))  # a short, harmless label -- the layout's own minimum stays tiny
    dialog.setMinimumSize(screen_width + 400, screen_height + 400)

    dialog.show()
    qapp.processEvents()
    assert dialog.width() > screen_width and dialog.height() > screen_height  # sanity

    constrain_to_screen(dialog)
    qapp.processEvents()

    assert dialog.width() <= screen_width
    assert dialog.height() <= screen_height
    dialog.close()


def test_guard_caps_every_dialog_as_it_is_shown(qapp):
    screen_width, _ = _screen_limits(qapp)
    guard = DialogSizeGuard()
    qapp.installEventFilter(guard)
    try:
        dialog = _dialog_with_huge_label()
        dialog.show()
        qapp.processEvents()
        assert dialog.width() <= screen_width
        dialog.close()
    finally:
        qapp.removeEventFilter(guard)


def test_long_label_gets_wrapped_rather_than_clipped(qapp):
    dialog = _dialog_with_huge_label()
    label = dialog.findChild(QLabel)
    assert not label.wordWrap()

    dialog.show()
    qapp.processEvents()
    constrain_to_screen(dialog)

    assert label.wordWrap()  # text stays readable instead of being cut off
    dialog.close()


def test_a_dialogs_own_smaller_maximum_is_never_loosened(qapp):
    dialog = QDialog()
    dialog.setFixedSize(320, 420)  # e.g. the donate QR popup

    dialog.show()
    qapp.processEvents()
    constrain_to_screen(dialog)

    assert dialog.maximumWidth() == 320
    assert dialog.maximumHeight() == 420
    dialog.close()


# --- a dialog opens fully on screen (its top was cut off above the display) ---


def test_a_tall_dialog_is_brought_fully_onto_the_screen(qapp, monkeypatch):
    from PySide6.QtCore import QRect
    from PySide6.QtWidgets import QDialog, QVBoxLayout, QWidget

    from smartdoc.presentation import dialog_size

    area = QRect(0, 0, 1400, 700)
    monkeypatch.setattr(dialog_size, "_usable_area", lambda window: area)
    guard = DialogSizeGuard()
    qapp.installEventFilter(guard)
    try:
        dialog = QDialog()
        QVBoxLayout(dialog).addWidget(QWidget())
        dialog.resize(600, 900)  # taller than the screen ...
        dialog.move(300, -120)  # ... and started with its top above the display
        dialog.show()
        qapp.processEvents()
        frame = dialog.frameGeometry()
        assert frame.top() >= area.top() and frame.bottom() <= area.bottom(), frame
    finally:
        qapp.removeEventFilter(guard)
        dialog.deleteLater()


def test_a_dialog_that_grows_after_it_is_shown_is_brought_back_on_screen(qapp, monkeypatch):
    """Regression: the Settings dialog grew a moment after opening and its top edge (title bar and tabs) ended up above the display."""
    from PySide6.QtCore import QRect

    from smartdoc.presentation import dialog_size

    area = QRect(0, 0, 1400, 800)
    monkeypatch.setattr(dialog_size, "_usable_area", lambda window: area)
    guard = DialogSizeGuard()
    qapp.installEventFilter(guard)
    try:
        dialog = QDialog()
        QVBoxLayout(dialog).addWidget(QLabel("x"))
        dialog.resize(500, 300)
        dialog.show()
        qapp.processEvents()
        dialog.move(300, 250)
        dialog.resize(500, 780)  # the late growth: now 250 + 780 runs below the usable area
        for _ in range(3):
            qapp.processEvents()
        frame = dialog.frameGeometry()
        assert frame.top() >= area.top() and frame.bottom() <= area.bottom(), frame
    finally:
        qapp.removeEventFilter(guard)
        dialog.deleteLater()
