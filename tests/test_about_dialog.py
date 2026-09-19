from smartdoc.presentation.about_dialog import AboutDialog
from smartdoc.presentation.eula_dialog import EULA_TEXT


def test_starts_on_info_page(qapp):
    dialog = AboutDialog()
    assert dialog.stack.currentWidget() is dialog._info_page


def test_legal_button_shows_full_eula_text(qapp):
    dialog = AboutDialog()
    dialog.legal_button.click()

    assert dialog.stack.currentWidget() is dialog._legal_page
    assert dialog.legal_text_area.toPlainText() == EULA_TEXT


def test_back_button_returns_to_info_page(qapp):
    dialog = AboutDialog()
    dialog.legal_button.click()
    dialog.back_button.click()

    assert dialog.stack.currentWidget() is dialog._info_page



def test_shows_version_and_copies_support_info(qapp, app_context):
    from PySide6.QtWidgets import QApplication

    from smartdoc import __version__

    dialog = AboutDialog(identity=app_context.identity)
    assert __version__ in dialog.version_label.text()

    dialog.copy_support_button.click()

    copied = QApplication.clipboard().text()
    assert __version__ in copied
    assert app_context.identity.short_id in copied
    assert app_context.identity.token not in copied  # the secret never leaves via support info
