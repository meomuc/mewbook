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


def test_info_page_states_licence_and_no_warranty(qapp):
    from smartdoc import APP_LICENSE_ID

    text = AboutDialog().license_label.text()
    assert APP_LICENSE_ID in text
    assert "KHÔNG kèm bất kỳ bảo hành" in text


def test_source_url_is_tied_to_the_version():
    from smartdoc.presentation.about_dialog import source_url

    assert source_url("https://example.org/mewbook/tree/v{version}", "1.2.3") == "https://example.org/mewbook/tree/v1.2.3"
    assert source_url("", "1.2.3") == ""


def test_source_line_is_a_link_once_a_template_is_configured(qapp, monkeypatch):
    from smartdoc import __version__
    from smartdoc.presentation import about_dialog

    monkeypatch.setattr(about_dialog, "APP_SOURCE_URL_TEMPLATE", "https://example.org/mewbook/tree/v{version}")
    label = about_dialog.AboutDialog().source_label
    assert f"https://example.org/mewbook/tree/v{__version__}" in label.text()
    assert label.openExternalLinks()


def test_source_line_falls_back_to_text_without_a_template(qapp, monkeypatch):
    from smartdoc.presentation import about_dialog

    monkeypatch.setattr(about_dialog, "APP_SOURCE_URL_TEMPLATE", "")
    label = about_dialog.AboutDialog().source_label
    assert "href" not in label.text()
    assert not label.openExternalLinks()


def test_legal_tabs_show_licence_and_third_party_notices(qapp):
    dialog = AboutDialog()
    dialog.legal_button.click()

    dialog.license_tab.click()
    assert dialog.legal_text_area.toPlainText().lstrip().startswith("GNU AFFERO GENERAL PUBLIC LICENSE")

    dialog.notices_tab.click()
    assert "PyMuPDF" in dialog.legal_text_area.toPlainText()

    dialog.privacy_tab.click()
    assert dialog.legal_text_area.toPlainText() == EULA_TEXT


def test_missing_legal_file_points_to_the_official_licence(qapp, monkeypatch, tmp_path):
    from smartdoc import APP_LICENSE_URL
    from smartdoc.presentation import about_dialog

    monkeypatch.setattr(about_dialog, "legal_file_path", lambda name: tmp_path / name)
    assert APP_LICENSE_URL in about_dialog.read_legal_file("LICENSE")
