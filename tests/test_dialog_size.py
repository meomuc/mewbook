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
