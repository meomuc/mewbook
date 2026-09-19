# SPDX-License-Identifier: AGPL-3.0-or-later
from __future__ import annotations

import time

import pytest
import requests

from smartdoc import __version__
from smartdoc.application import update_checker as uc
from smartdoc.core.event_bus import UpdateAvailableEvent
from smartdoc.presentation.settings_dialog import SettingsDialog
from smartdoc.presentation.status_bar_panel import StatusBarPanel
from smartdoc.presentation.update_panel import UpdatePanel

FEED = "https://api.example.org/repos/o/r/releases/latest"


class _Response:
    def __init__(self, data=None, status=200, bad_json=False):
        self._data, self.status_code, self._bad_json = data, status, bad_json

    def raise_for_status(self):
        if self.status_code >= 400:
            raise requests.HTTPError(f"HTTP {self.status_code}")

    def json(self):
        if self._bad_json:
            raise ValueError("not json")
        return self._data


def _checker(app_context, feed=FEED):
    return uc.UpdateChecker(app_context.config, app_context.event_bus, feed_url=feed)


def _serve(monkeypatch, response):
    calls = []

    def fake_get(url, **kwargs):
        calls.append((url, kwargs))
        if isinstance(response, Exception):
            raise response
        return response

    monkeypatch.setattr(uc.requests, "get", fake_get)
    return calls


def test_version_parsing_and_ordering():
    assert uc.is_newer("v1.0.1", "1.0.0") and uc.is_newer("2.0.0", "1.9.9") and uc.is_newer("1.10.0", "1.9.0")
    assert not uc.is_newer("1.0.0", "1.0.0") and not uc.is_newer("0.9.0", "1.0.0")
    assert uc.is_newer("1.1.0", "1.1.0-beta.1") and not uc.is_newer("1.1.0-beta.1", "1.1.0")  # a release beats its pre-release
    assert not uc.is_newer("latest", "1.0.0") and not uc.is_newer("", "1.0.0")  # never guess from junk
    assert uc.parse_version("nightly") is None


def test_the_check_is_off_by_default(app_context):
    assert app_context.config.config.update_check_enabled is False


def test_the_request_carries_nothing_that_identifies_the_installation(app_context, monkeypatch):
    calls = _serve(monkeypatch, _Response({"tag_name": "v9.9.9", "html_url": "https://example.org/r/v9.9.9"}))

    _checker(app_context).check()

    ((url, kwargs),) = calls
    assert url == FEED and set(kwargs["headers"]) == {"User-Agent", "Accept"}
    assert kwargs["headers"]["User-Agent"] == f"MewBook/{__version__}"
    assert not {"params", "cookies", "data", "json", "auth"} & set(kwargs)
    assert app_context.identity.token not in repr(calls) and app_context.identity.short_id not in repr(calls)


def test_a_newer_release_is_reported_and_announced(app_context, monkeypatch):
    _serve(monkeypatch, _Response({"tag_name": "v99.0.0", "html_url": "https://example.org/r/v99", "body": "Notes"}))
    heard = []
    app_context.event_bus.subscribe(UpdateAvailableEvent, heard.append)

    info = _checker(app_context).check_and_announce()

    assert (info.version, info.url, info.notes) == ("99.0.0", "https://example.org/r/v99", "Notes")
    assert [(e.version, e.url) for e in heard] == [("99.0.0", "https://example.org/r/v99")]
    assert app_context.config.config.update_last_checked > 0


def test_the_current_version_is_not_news(app_context, monkeypatch):
    _serve(monkeypatch, _Response({"tag_name": f"v{__version__}", "html_url": "https://example.org/r"}))
    heard = []
    app_context.event_bus.subscribe(UpdateAvailableEvent, heard.append)
    assert _checker(app_context).check_and_announce() is None and heard == []


@pytest.mark.parametrize(
    "response",
    [
        _Response(status=500),
        _Response(bad_json=True),
        _Response({"tag_name": "not-a-version", "html_url": "https://example.org/r"}),
        _Response({"tag_name": "v99.0.0", "html_url": "http://insecure.example.org/r"}),  # only https links are ever opened
        _Response({"tag_name": "v99.0.0"}),
        requests.ConnectionError("offline"),
    ],
)
def test_a_bad_answer_or_no_network_is_a_plain_error(app_context, monkeypatch, response):
    _serve(monkeypatch, response)
    with pytest.raises(uc.UpdateCheckError):
        _checker(app_context).check()


def test_without_a_configured_feed_nothing_is_requested(app_context, monkeypatch):
    calls = _serve(monkeypatch, _Response({}))
    with pytest.raises(uc.UpdateCheckError, match="Chưa cấu hình"):
        _checker(app_context, feed="").check()
    assert calls == []


def test_the_startup_check_needs_opt_in_a_feed_and_a_day_since_the_last_one(app_context, monkeypatch):
    calls = _serve(monkeypatch, _Response({"tag_name": "v99.0.0", "html_url": "https://example.org/r"}))
    checker = _checker(app_context)
    config = app_context.config.config

    assert checker.maybe_check_on_startup() is None and calls == []  # not enabled

    config.update_check_enabled = True
    config.update_last_checked = time.time() - 3600
    assert checker.maybe_check_on_startup() is None and calls == []  # checked an hour ago

    config.update_last_checked = time.time() - 2 * uc.CHECK_INTERVAL_SECONDS
    assert checker.maybe_check_on_startup().version == "99.0.0" and len(calls) == 1

    assert _checker(app_context, feed="").maybe_check_on_startup() is None and len(calls) == 1  # no feed configured


def test_a_failing_startup_check_never_raises(app_context, monkeypatch):
    _serve(monkeypatch, requests.ConnectionError("offline"))
    app_context.config.config.update_check_enabled = True
    assert _checker(app_context).maybe_check_on_startup() is None


def _wait(qapp, panel, timeout=10.0):
    deadline = time.time() + timeout
    while panel._busy and time.time() < deadline:
        qapp.processEvents()
        time.sleep(0.01)
    qapp.processEvents()
    assert not panel._busy


def test_the_panel_is_inert_while_no_feed_is_configured(qapp, app_context):
    panel = UpdatePanel(app_context)  # the shipped build has an empty APP_UPDATE_FEED_URL
    assert not panel.check_button.isEnabled() and not panel.enable_check.isEnabled()
    assert "Chưa cấu hình" in panel.status_label.text()


def test_check_now_shows_the_link_and_the_setting_is_saved(qapp, app_context, monkeypatch):
    app_context.updates.feed_url = FEED
    _serve(monkeypatch, _Response({"tag_name": "v99.0.0", "html_url": "https://example.org/r/v99"}))
    dialog = SettingsDialog(app_context)
    panel = dialog.update_panel

    panel.check_button.click()
    _wait(qapp, panel)
    panel.enable_check.setChecked(True)
    dialog._on_save()

    assert "99.0.0" in panel.status_label.text() and "https://example.org/r/v99" in panel.status_label.text()
    assert app_context.config.config.update_check_enabled is True


def test_check_now_says_when_you_are_current_and_when_it_failed(qapp, app_context, monkeypatch):
    app_context.updates.feed_url = FEED
    panel = UpdatePanel(app_context)
    _serve(monkeypatch, _Response({"tag_name": f"v{__version__}", "html_url": "https://example.org/r"}))
    panel.check_button.click()
    _wait(qapp, panel)
    assert "mới nhất" in panel.status_label.text()

    _serve(monkeypatch, requests.ConnectionError("offline"))
    panel.check_button.click()
    _wait(qapp, panel)
    assert "⚠️" in panel.status_label.text() and panel.check_button.isEnabled()


def test_the_status_bar_offers_the_release_page_only_over_https(qapp, app_context, monkeypatch):
    from PySide6.QtGui import QDesktopServices

    opened = []
    monkeypatch.setattr(QDesktopServices, "openUrl", lambda url: opened.append(url.toString()) or True)
    bar = StatusBarPanel(app_context)
    assert bar.update_label.isHidden()

    app_context.event_bus.publish(UpdateAvailableEvent(version="99.0.0", url="https://example.org/r/v99"))
    qapp.processEvents()
    assert not bar.update_label.isHidden() and "99.0.0" in bar.update_label.text()
    bar.update_label.clicked.emit()
    assert opened == ["https://example.org/r/v99"]

    app_context.event_bus.publish(UpdateAvailableEvent(version="99.0.1", url="http://insecure.example.org/"))
    qapp.processEvents()
    bar.update_label.clicked.emit()
    assert opened == ["https://example.org/r/v99"]  # the insecure link was not opened
