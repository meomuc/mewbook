# SPDX-License-Identifier: AGPL-3.0-or-later
"""The community fan page is one click away from the Help menu, Help -> About and Settings -> "Cập nhật", and opening it is
only ever the user's click on a plain https address."""
from __future__ import annotations

from PySide6.QtGui import QDesktopServices

from smartdoc import APP_COMMUNITY_URL
from smartdoc.presentation import about_dialog, community, update_panel
from smartdoc.presentation.about_dialog import AboutDialog
from smartdoc.presentation.main_window import MainWindow
from smartdoc.presentation.update_panel import UpdatePanel

PAGE = "https://www.facebook.com/meomuc.mewbook/"


def _capture(monkeypatch) -> list[str]:
    opened: list[str] = []
    monkeypatch.setattr(QDesktopServices, "openUrl", lambda url: opened.append(url.toString()) or True)
    return opened


def test_the_configured_page_is_the_projects_fan_page():
    assert APP_COMMUNITY_URL == PAGE
    assert community.community_url() == PAGE


def test_only_a_plain_https_address_is_ever_opened(monkeypatch):
    opened = _capture(monkeypatch)
    assert community.open_community_page() is True and opened == [PAGE]
    for bad in ("", "http://www.facebook.com/x", "javascript:alert(1)", "file:///C:/Windows/notepad.exe"):
        monkeypatch.setattr(community, "APP_COMMUNITY_URL", bad)
        assert community.community_url() == "" and community.open_community_page() is False
    assert opened == [PAGE]


def test_the_help_menu_opens_the_page(qapp, app_context, monkeypatch):
    opened = _capture(monkeypatch)
    window = MainWindow(app_context)
    help_menu = next(a.menu() for a in window.menuBar().actions() if a.menu() and a.text().endswith("Help"))
    action = next(a for a in help_menu.actions() if "Fanpage" in a.text())
    action.trigger()
    assert opened == [PAGE]
    window.hide()
    window.deleteLater()


def test_about_links_to_the_page(qapp):
    label = AboutDialog().community_label
    assert not label.isHidden()  # a page is configured, so the line exists
    assert PAGE in label.text() and label.openExternalLinks()


def test_about_omits_the_line_when_no_page_is_configured(qapp, monkeypatch):
    monkeypatch.setattr(about_dialog, "community_url", lambda: "")
    label = AboutDialog().community_label
    assert label.isHidden() and "href" not in label.text()


def test_the_update_tab_has_a_button_that_opens_the_page_even_without_a_release_feed(qapp, app_context, monkeypatch):
    opened = _capture(monkeypatch)
    panel = UpdatePanel(app_context)  # the shipped build has no APP_UPDATE_FEED_URL yet
    assert not panel.check_button.isEnabled()
    assert panel.community_button.isEnabled()
    assert "fanpage" in panel.status_label.text()
    panel.community_button.click()
    assert opened == [PAGE]


def test_the_update_tab_button_is_disabled_without_a_page(qapp, app_context, monkeypatch):
    monkeypatch.setattr(update_panel, "community_url", lambda: "")
    panel = UpdatePanel(app_context)
    assert not panel.community_button.isEnabled() and "fanpage" not in panel.status_label.text()


# --- the official website, opened the same way ---

SITE = "https://meomuc.github.io/"


def test_the_official_website_is_configured_and_opened_only_when_plain_https(monkeypatch):
    from smartdoc import APP_WEBSITE_URL

    opened = _capture(monkeypatch)
    assert APP_WEBSITE_URL == SITE and community.website_url() == SITE
    assert community.open_website() is True and opened == [SITE]
    for bad in ("", "http://meomuc.github.io/", "javascript:alert(1)", "file:///C:/Windows/notepad.exe"):
        monkeypatch.setattr(community, "APP_WEBSITE_URL", bad)
        assert community.website_url() == "" and community.open_website() is False
    assert opened == [SITE]


def test_the_help_menu_lists_the_website_before_the_fan_page_and_opens_it(qapp, app_context, monkeypatch):
    opened = _capture(monkeypatch)
    window = MainWindow(app_context)
    help_menu = next(a.menu() for a in window.menuBar().actions() if a.menu() and a.text().endswith("Help"))
    texts = [a.text() for a in help_menu.actions()]
    website_at = next(i for i, t in enumerate(texts) if "Trang web chính thức" in t)
    assert website_at < next(i for i, t in enumerate(texts) if "Fanpage" in t)
    help_menu.actions()[website_at].trigger()
    assert opened == [SITE]
    window.hide()
    window.deleteLater()


def test_about_names_the_website(qapp):
    label = AboutDialog().website_label
    assert not label.isHidden() and SITE in label.text() and label.openExternalLinks()
    assert "Trang web chính thức" in label.text()


def test_about_omits_the_website_line_when_none_is_configured(qapp, monkeypatch):
    monkeypatch.setattr(about_dialog, "website_url", lambda: "")
    label = AboutDialog().website_label
    assert label.isHidden() and "href" not in label.text()


def test_the_update_tab_has_a_website_button(qapp, app_context, monkeypatch):
    opened = _capture(monkeypatch)
    panel = UpdatePanel(app_context)
    assert panel.website_button.isEnabled()
    panel.website_button.click()
    assert opened == [SITE]
