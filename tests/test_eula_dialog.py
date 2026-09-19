from PySide6.QtWidgets import QDialog

from smartdoc.presentation.eula_dialog import EULA_TEXT, EulaDialog


def test_full_text_is_shown_in_scrollable_area(qapp):
    dialog = EulaDialog()
    assert dialog.text_area.toPlainText() == EULA_TEXT
    assert dialog.text_area.isReadOnly()


def test_clicking_agree_accepts_the_dialog(qapp):
    dialog = EulaDialog()
    dialog.accept()
    assert dialog.result() == QDialog.Accepted


def test_closing_without_agreeing_does_not_accept(qapp):
    dialog = EulaDialog()
    dialog.reject()
    assert dialog.result() == QDialog.Rejected
