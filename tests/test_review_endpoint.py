# SPDX-License-Identifier: AGPL-3.0-or-later
"""Community reviews: the connection is the app's own and always defined; the person's switch (on by default) decides whether it
runs. Two questions, answered separately."""
from __future__ import annotations

import pytest

from smartdoc.application.review_endpoint import (
    STATE_NO_SERVER,
    STATE_OFF,
    STATE_ON,
    resolve_review_endpoint,
    review_state,
)
from smartdoc.core.config import AppConfig

BUILTIN = ("https://project.supabase.co/", "sb_publishable_abc")


def test_a_new_install_has_the_feature_on_and_no_hand_set_connection():
    config = AppConfig()
    assert config.community_reviews_enabled is True  # active by default
    assert config.supabase_url is None and config.supabase_anon_key is None  # nothing for the person to configure


def test_the_apps_own_connection_is_used_when_nothing_was_set_by_hand():
    endpoint = resolve_review_endpoint(AppConfig(), BUILTIN)
    assert endpoint is not None and endpoint.url == "https://project.supabase.co" and endpoint.anon_key == "sb_publishable_abc"
    assert review_state(AppConfig(), BUILTIN) == STATE_ON


def test_a_connection_set_by_hand_overrides_the_default_for_a_self_hosted_server():
    config = AppConfig(supabase_url="https://mine.example.org/", supabase_anon_key="k")
    assert resolve_review_endpoint(config, BUILTIN).url == "https://mine.example.org"
    half = AppConfig(supabase_url="https://mine.example.org/")  # incomplete: ignored, the default stays
    assert resolve_review_endpoint(half, BUILTIN).url == "https://project.supabase.co"


def test_the_persons_switch_alone_decides_whether_it_runs():
    assert review_state(AppConfig(community_reviews_enabled=False), BUILTIN) == STATE_OFF  # off even though a server exists
    assert review_state(AppConfig(community_reviews_enabled=True), BUILTIN) == STATE_ON


def test_a_build_without_a_server_says_so_instead_of_pretending():
    assert resolve_review_endpoint(AppConfig(), ("", "")) is None
    assert review_state(AppConfig(), ("", "")) == STATE_NO_SERVER
    assert review_state(AppConfig(community_reviews_enabled=False), ("", "")) == STATE_OFF  # off wins


@pytest.mark.parametrize("url", ["http://example.org", "ftp://x", "not a url", ""])
def test_only_https_or_this_computer_is_accepted(url):
    assert resolve_review_endpoint(AppConfig(), (url, "key")) is None
    assert resolve_review_endpoint(AppConfig(), ("http://127.0.0.1:54321", "key")) is not None  # a local test server


def test_the_shipped_defaults_are_declared_and_fall_back_to_the_error_report_project(monkeypatch):
    import smartdoc
    from smartdoc.application import review_endpoint as module

    assert hasattr(smartdoc, "APP_REVIEWS_URL") and hasattr(smartdoc, "APP_REVIEWS_ANON_KEY")
    monkeypatch.setattr(module, "APP_REVIEWS_URL", "")
    monkeypatch.setattr(module, "APP_REVIEWS_ANON_KEY", "")
    monkeypatch.setattr(module, "APP_ERROR_REPORT_URL", "https://same-project.supabase.co")
    monkeypatch.setattr(module, "APP_ERROR_REPORT_ANON_KEY", "sb_publishable_x")
    assert resolve_review_endpoint(AppConfig()).url == "https://same-project.supabase.co"
    monkeypatch.setattr(module, "APP_REVIEWS_URL", "https://reviews.supabase.co")
    monkeypatch.setattr(module, "APP_REVIEWS_ANON_KEY", "sb_publishable_r")
    assert resolve_review_endpoint(AppConfig()).url == "https://reviews.supabase.co"  # its own beats the shared one


# -- the screens follow the two answers --------------------------------------------------------------------------------------

@pytest.fixture
def with_server(monkeypatch):
    from smartdoc.application import review_endpoint as module

    monkeypatch.setattr(module, "APP_REVIEWS_URL", "https://project.supabase.co")
    monkeypatch.setattr(module, "APP_REVIEWS_ANON_KEY", "sb_publishable_abc")


def test_the_review_dialog_is_connected_by_default_without_any_setting(qapp, app_context, with_server, monkeypatch):
    from smartdoc.presentation import review_dialog

    monkeypatch.setattr(review_dialog.ReviewDialog, "_load_reviews_async", lambda self: None)
    dialog = review_dialog.ReviewDialog(app_context, {"id": "d1", "title": "Sách"})
    assert dialog._configured is True and dialog._sync.supabase_url == "https://project.supabase.co"
    dialog.deleteLater()


def test_switched_off_the_dialog_does_not_open(qapp, app_context, with_server, monkeypatch):
    from PySide6.QtWidgets import QMessageBox

    from smartdoc.presentation import review_dialog

    app_context.config.config.community_reviews_enabled = False
    told = []
    monkeypatch.setattr(QMessageBox, "information", staticmethod(lambda *a, **k: told.append(a[2])))

    def must_not_open(*_a, **_k):
        raise AssertionError("must not open")

    monkeypatch.setattr(review_dialog, "ReviewDialog", must_not_open)
    review_dialog.open_review_dialog(app_context, {"id": "d1", "title": "x"})
    assert told and "đang tắt" in told[0]


def test_the_rating_sync_refuses_when_off_and_uses_the_default_otherwise(app_context, with_server, monkeypatch):
    from smartdoc.application import rating_sync
    from smartdoc.application.cloud_reviews import CloudReviewError

    app_context.config.config.community_reviews_enabled = False
    with pytest.raises(CloudReviewError, match="tắt"):
        rating_sync.sync_all_rating_stats(app_context)
    app_context.config.config.community_reviews_enabled = True
    seen = []
    monkeypatch.setattr(rating_sync.SupabaseReviewSync, "fetch_all_rating_stats", lambda self: seen.append(self.supabase_url) or {})
    rating_sync.sync_all_rating_stats(app_context)
    assert seen == ["https://project.supabase.co"]


def test_the_status_bar_says_which_of_the_three_situations_it_is(qapp, app_context, with_server, monkeypatch):
    from smartdoc.application import review_endpoint as module
    from smartdoc.presentation.status_bar_panel import StatusBarPanel

    bar = StatusBarPanel(app_context)
    assert bar._cloud_configured() and "đang bật" in bar.cloud_label.toolTip()
    app_context.config.config.community_reviews_enabled = False
    bar._refresh_cloud()
    assert not bar._cloud_configured() and "bạn đã tắt" in bar.cloud_label.toolTip()
    app_context.config.config.community_reviews_enabled = True
    monkeypatch.setattr(module, "APP_REVIEWS_URL", "")
    monkeypatch.setattr(module, "APP_REVIEWS_ANON_KEY", "")
    monkeypatch.setattr(module, "APP_ERROR_REPORT_URL", "")
    bar._refresh_cloud()
    assert "chưa có máy chủ" in bar.cloud_label.toolTip()
    bar.deleteLater()


def test_settings_shows_the_switch_on_by_default_and_the_server_line(qapp, app_context, with_server):
    from smartdoc.presentation.settings_dialog import SettingsDialog

    dialog = SettingsDialog(app_context)
    assert dialog.community_reviews_check.isChecked() and "máy chủ của MewBook" in dialog.reviews_server_label.text()
    dialog.community_reviews_check.setChecked(False)
    assert "Đã tắt" in dialog.reviews_server_label.text()
    dialog.deleteLater()
