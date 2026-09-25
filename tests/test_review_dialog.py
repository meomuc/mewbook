import time

import pytest

from PySide6.QtCore import Qt

from smartdoc.application.cloud_reviews import CloudReviewError
from smartdoc.presentation.review_dialog import ReviewDialog


def _pump_until(qapp, predicate, timeout: float = 3.0) -> bool:
    deadline = time.time() + timeout
    while time.time() < deadline:
        qapp.processEvents()
        if predicate():
            return True
        time.sleep(0.02)
    qapp.processEvents()
    return predicate()


def _doc():
    return {"id": "doc1", "title": "Sample Book"}


@pytest.fixture(autouse=True)
def _nicknames_free(monkeypatch):
    monkeypatch.setattr(
        "smartdoc.presentation.review_dialog.SupabaseReviewSync.nickname_status", lambda self, nick, h: "free"
    )


@pytest.fixture(autouse=True)
def _flags_unknown(monkeypatch):
    """The dialog reads the server's switches on a thread; unless a test says otherwise they cannot be read."""
    monkeypatch.setattr("smartdoc.presentation.review_dialog.SupabaseReviewSync.flags", lambda self, force=False: None)


def _configure(app_context):
    app_context.config.config.supabase_url = "https://fake.supabase.co"
    app_context.config.config.supabase_anon_key = "fake-key"


def test_missing_service_account_shows_message_and_does_not_hit_network(qapp, app_context, monkeypatch):
    app_context.config.config.supabase_url = None
    app_context.config.config.supabase_anon_key = None
    called = []
    monkeypatch.setattr(
        "smartdoc.presentation.review_dialog.SupabaseReviewSync.fetch_reviews",
        lambda self, doc_id: called.append(doc_id) or [],
    )

    dialog = ReviewDialog(app_context, _doc())

    assert called == []
    assert "chưa được bật" in dialog.status_label.text()


def test_loads_existing_reviews_on_open(qapp, app_context, monkeypatch):
    app_context.config.config.supabase_url = "https://fake.supabase.co"
    app_context.config.config.supabase_anon_key = "fake-key"
    fake_reviews = [{"nickname": "Kevin", "rating": 5, "comment": "Sach hay", "timestamp": 2.0}]
    monkeypatch.setattr(
        "smartdoc.presentation.review_dialog.SupabaseReviewSync.fetch_reviews",
        lambda self, doc_id: fake_reviews,
    )

    dialog = ReviewDialog(app_context, _doc())
    assert _pump_until(qapp, lambda: dialog.reviews_list.count() > 0, timeout=3.0)

    assert dialog.reviews_list.count() == 1
    assert "Kevin" in dialog.reviews_list.item(0).text()


def test_no_reviews_shows_placeholder_message(qapp, app_context, monkeypatch):
    app_context.config.config.supabase_url = "https://fake.supabase.co"
    app_context.config.config.supabase_anon_key = "fake-key"
    monkeypatch.setattr(
        "smartdoc.presentation.review_dialog.SupabaseReviewSync.fetch_reviews",
        lambda self, doc_id: [],
    )

    dialog = ReviewDialog(app_context, _doc())
    assert _pump_until(qapp, lambda: dialog.reviews_list.count() > 0, timeout=3.0)
    assert "đầu tiên" in dialog.reviews_list.item(0).text()


def test_fetch_error_shown_in_status_label(qapp, app_context, monkeypatch):
    app_context.config.config.supabase_url = "https://fake.supabase.co"
    app_context.config.config.supabase_anon_key = "fake-key"

    def raise_error(self, doc_id):
        raise CloudReviewError("boom")

    monkeypatch.setattr("smartdoc.presentation.review_dialog.SupabaseReviewSync.fetch_reviews", raise_error)

    dialog = ReviewDialog(app_context, _doc())
    assert _pump_until(qapp, lambda: "boom" in dialog.status_label.text(), timeout=3.0)


def test_submit_without_rating_shows_warning_and_does_not_submit(qapp, app_context, monkeypatch):
    from PySide6.QtWidgets import QMessageBox

    app_context.config.config.supabase_url = "https://fake.supabase.co"
    app_context.config.config.supabase_anon_key = "fake-key"
    monkeypatch.setattr(
        "smartdoc.presentation.review_dialog.SupabaseReviewSync.fetch_reviews", lambda self, doc_id: []
    )
    submit_called = []
    monkeypatch.setattr(
        "smartdoc.presentation.review_dialog.SupabaseReviewSync.submit_review",
        lambda self, *a, **k: submit_called.append(1),
    )
    monkeypatch.setattr(QMessageBox, "warning", staticmethod(lambda *a, **k: QMessageBox.Ok))

    dialog = ReviewDialog(app_context, _doc())
    dialog._on_submit()

    assert submit_called == []


def test_submit_with_rating_calls_sync_and_refreshes_list(qapp, app_context, monkeypatch):
    app_context.config.config.supabase_url = "https://fake.supabase.co"
    app_context.config.config.supabase_anon_key = "fake-key"
    monkeypatch.setattr(
        "smartdoc.presentation.review_dialog.SupabaseReviewSync.fetch_reviews", lambda self, doc_id: []
    )

    submitted = []

    def fake_submit(self, doc_id, nickname, rating, comment, *, user_token, review_id=None):
        submitted.append((doc_id, nickname, rating, comment))
        return [{"nickname": nickname, "rating": rating, "comment": comment, "timestamp": 5.0}]

    monkeypatch.setattr("smartdoc.presentation.review_dialog.SupabaseReviewSync.submit_review", fake_submit)

    dialog = ReviewDialog(app_context, _doc())
    assert _pump_until(qapp, lambda: dialog.reviews_list.count() > 0, timeout=3.0)

    dialog.nickname_edit.setText("Lan")
    dialog._set_rating(4)
    dialog.comment_edit.setPlainText("Rat hay")
    dialog._on_submit()

    assert _pump_until(qapp, lambda: len(submitted) == 1, timeout=3.0)
    assert submitted[0] == ("doc1", "Lan", 4, "Rat hay")

    assert _pump_until(qapp, lambda: dialog.reviews_list.count() == 1 and "Lan" in dialog.reviews_list.item(0).text(), timeout=3.0)
    assert app_context.config.config.reviewer_nickname == "Lan"


def test_submit_error_shows_warning_and_reenables_button(qapp, app_context, monkeypatch):
    from PySide6.QtWidgets import QMessageBox

    app_context.config.config.supabase_url = "https://fake.supabase.co"
    app_context.config.config.supabase_anon_key = "fake-key"
    monkeypatch.setattr(
        "smartdoc.presentation.review_dialog.SupabaseReviewSync.fetch_reviews", lambda self, doc_id: []
    )

    def raise_error(self, doc_id, nickname, rating, comment, **kwargs):
        raise CloudReviewError("network down")

    monkeypatch.setattr("smartdoc.presentation.review_dialog.SupabaseReviewSync.submit_review", raise_error)
    warnings = []
    monkeypatch.setattr(QMessageBox, "warning", staticmethod(lambda *a, **k: warnings.append(a) or QMessageBox.Ok))

    dialog = ReviewDialog(app_context, _doc())
    dialog._set_rating(3)
    dialog._on_submit()

    assert _pump_until(qapp, lambda: len(warnings) == 1, timeout=3.0)
    assert dialog.submit_button.isEnabled()



def _my_review(app_context, **overrides):
    review = {"id": 7, "nickname": "Lan", "rating": 2, "comment": "old", "user_hash": app_context.identity.user_hash,
              "created_at": "2026-01-01T00:00:00+00:00"}
    review.update(overrides)
    return review


def test_own_review_is_marked_and_summary_shows_average(qapp, app_context, monkeypatch):
    _configure(app_context)
    reviews = [_my_review(app_context, rating=4), {"id": 8, "nickname": "Kevin", "rating": 2, "comment": "", "user_hash": "x"}]
    monkeypatch.setattr("smartdoc.presentation.review_dialog.SupabaseReviewSync.fetch_reviews", lambda self, d: reviews)

    dialog = ReviewDialog(app_context, _doc())
    assert _pump_until(qapp, lambda: dialog.reviews_list.count() == 2)

    assert "Bạn" in dialog.reviews_list.item(0).data(Qt.UserRole + 1)
    assert "Bạn" not in dialog.reviews_list.item(1).data(Qt.UserRole + 1)
    assert "#f5b301" in dialog.reviews_list.item(0).data(Qt.UserRole + 1)  # gold stars
    assert "3.0" in dialog.summary_label.text()
    assert "2 đánh giá" in dialog.summary_label.text()
    assert dialog.my_review_label.isVisibleTo(dialog)


@pytest.mark.parametrize("choice, expected_review_id", [("update", 7), ("new", None)])
def test_existing_review_asks_update_or_new(qapp, app_context, monkeypatch, choice, expected_review_id):
    _configure(app_context)
    monkeypatch.setattr(
        "smartdoc.presentation.review_dialog.SupabaseReviewSync.fetch_reviews",
        lambda self, d: [_my_review(app_context)],
    )
    submitted = []

    def fake_submit(self, doc_id, nickname, rating, comment, *, user_token, review_id=None):
        submitted.append(review_id)
        assert user_token == app_context.identity.token
        return [_my_review(app_context, rating=rating, comment=comment)]

    monkeypatch.setattr("smartdoc.presentation.review_dialog.SupabaseReviewSync.submit_review", fake_submit)
    asked = []
    monkeypatch.setattr(ReviewDialog, "_ask_update_or_new", lambda self, existing: asked.append(existing) or choice)

    dialog = ReviewDialog(app_context, _doc())
    assert _pump_until(qapp, lambda: dialog.reviews_list.count() == 1)
    dialog._set_rating(5)
    dialog._on_submit()

    assert _pump_until(qapp, lambda: submitted)
    assert asked and asked[0]["id"] == 7
    assert submitted == [expected_review_id]


def test_cancelling_the_update_or_new_question_submits_nothing(qapp, app_context, monkeypatch):
    _configure(app_context)
    monkeypatch.setattr(
        "smartdoc.presentation.review_dialog.SupabaseReviewSync.fetch_reviews",
        lambda self, d: [_my_review(app_context)],
    )
    submitted = []
    monkeypatch.setattr(
        "smartdoc.presentation.review_dialog.SupabaseReviewSync.submit_review",
        lambda self, *a, **k: submitted.append(1),
    )
    monkeypatch.setattr(ReviewDialog, "_ask_update_or_new", lambda self, existing: None)

    dialog = ReviewDialog(app_context, _doc())
    assert _pump_until(qapp, lambda: dialog.reviews_list.count() == 1)
    dialog._set_rating(5)
    dialog._on_submit()
    qapp.processEvents()

    assert submitted == []
    assert dialog.submit_button.isEnabled()


def test_taken_nickname_warns_and_does_not_submit(qapp, app_context, monkeypatch):
    from PySide6.QtWidgets import QMessageBox

    _configure(app_context)
    monkeypatch.setattr("smartdoc.presentation.review_dialog.SupabaseReviewSync.fetch_reviews", lambda self, d: [])
    monkeypatch.setattr(
        "smartdoc.presentation.review_dialog.SupabaseReviewSync.nickname_status", lambda self, nick, h: "taken"
    )
    submitted = []
    monkeypatch.setattr(
        "smartdoc.presentation.review_dialog.SupabaseReviewSync.submit_review",
        lambda self, *a, **k: submitted.append(1),
    )
    warnings = []
    monkeypatch.setattr(QMessageBox, "warning", staticmethod(lambda *a, **k: warnings.append(a) or QMessageBox.Ok))

    dialog = ReviewDialog(app_context, _doc())
    dialog.nickname_edit.setText("Kevin")
    dialog._set_rating(4)
    dialog._on_submit()

    assert _pump_until(qapp, lambda: warnings)
    assert "đã có người dùng" in warnings[0][2]
    assert submitted == []
    assert dialog.submit_button.isEnabled()
    assert app_context.config.config.reviewer_nickname != "Kevin"


def test_successful_submit_refreshes_rating_status_everywhere(qapp, app_context, monkeypatch):
    from smartdoc.core.event_bus import LibraryUpdatedEvent

    _configure(app_context)
    app_context.db.add_or_update_document("doc1", {"title": "Sample Book", "file_path": "x.pdf", "created_at": 0.0})
    monkeypatch.setattr("smartdoc.presentation.review_dialog.SupabaseReviewSync.fetch_reviews", lambda self, d: [])
    monkeypatch.setattr(
        "smartdoc.presentation.review_dialog.SupabaseReviewSync.submit_review",
        lambda self, doc_id, nickname, rating, comment, **k: [
            {"id": 1, "nickname": nickname, "rating": rating, "comment": comment},
            {"id": 2, "nickname": "Other", "rating": 2, "comment": ""},
        ],
    )
    events = []
    app_context.event_bus.subscribe(LibraryUpdatedEvent, events.append)

    dialog = ReviewDialog(app_context, _doc())
    dialog._set_rating(4)
    dialog._on_submit()

    assert _pump_until(qapp, lambda: "Đã gửi" in dialog.status_label.text())
    stored = app_context.db.get_document("doc1")
    assert stored["avg_rating"] == 3.0
    assert stored["review_count"] == 2
    assert events
    assert "3.0" in dialog.summary_label.text()


# --- moderation (S2-03) ------------------------------------------------------------------------------------------------------------

def _loaded(qapp, app_context, monkeypatch, reviews, flags=None):
    _configure(app_context)
    monkeypatch.setattr("smartdoc.presentation.review_dialog.SupabaseReviewSync.fetch_reviews", lambda self, doc_id: list(reviews))
    if flags is not None:
        monkeypatch.setattr("smartdoc.presentation.review_dialog.SupabaseReviewSync.flags", lambda self, force=False: flags)
    dialog = ReviewDialog(app_context, _doc())
    assert _pump_until(qapp, lambda: dialog.reviews_list.count() == max(len(reviews), 1), timeout=3.0)  # loaded (or the "be the first" row)
    return dialog


def _reviews(app_context):
    return [
        {"id": 11, "nickname": "Kevin", "rating": 5, "comment": "Hay", "user_hash": "someone-else"},
        {"id": 12, "nickname": "Bạn", "rating": 4, "comment": "Của tôi", "user_hash": app_context.identity.user_hash},
    ]


def test_the_owners_banner_is_shown_as_plain_text_and_reviews_can_be_off(qapp, app_context, monkeypatch):
    from smartdoc.application.service_flags import FlagSnapshot

    flags = FlagSnapshot({"reviews_enabled": "false", "banner_message": "<b>Bảo trì</b> tới 22h"})
    dialog = _loaded(qapp, app_context, monkeypatch, _reviews(app_context), flags)
    assert _pump_until(qapp, lambda: not dialog.notice_label.isHidden())
    assert dialog.banner_label.text() == "<b>Bảo trì</b> tới 22h" and not dialog.banner_label.isHidden()  # never rendered as HTML
    assert "tạm ngừng" in dialog.notice_label.text() and dialog.reviews_list.count() == 2  # reading still works
    assert not dialog.submit_button.isEnabled()
    dialog.reviews_list.setCurrentRow(0)
    assert not dialog.report_button.isEnabled()  # nor can one report while it is off


def test_when_the_switches_cannot_be_read_nothing_is_disabled(qapp, app_context, monkeypatch):
    dialog = _loaded(qapp, app_context, monkeypatch, _reviews(app_context))  # flags() -> None from the autouse fixture
    qapp.processEvents()
    assert dialog.notice_label.isHidden() and dialog.banner_label.isHidden() and dialog.submit_button.isEnabled()


def test_only_somebody_elses_review_can_be_reported(qapp, app_context, monkeypatch):
    dialog = _loaded(qapp, app_context, monkeypatch, _reviews(app_context))
    assert not dialog.report_button.isEnabled()  # nothing selected
    dialog.reviews_list.setCurrentRow(0)
    assert dialog.report_button.isEnabled()
    dialog.reviews_list.setCurrentRow(1)  # the user's own
    assert not dialog.report_button.isEnabled()


def test_reporting_asks_for_a_reason_sends_it_and_refreshes_the_list(qapp, app_context, monkeypatch):
    from PySide6.QtWidgets import QMessageBox

    dialog = _loaded(qapp, app_context, monkeypatch, _reviews(app_context))
    sent, thanks, fetches = [], [], []
    monkeypatch.setattr(dialog, "_ask_report_reason", lambda: "abuse")
    monkeypatch.setattr(
        "smartdoc.presentation.review_dialog.SupabaseReviewSync.report_review",
        lambda self, review_id, reason, *, user_token: sent.append((review_id, reason, user_token)) or 1,
    )
    monkeypatch.setattr(QMessageBox, "information", staticmethod(lambda *a, **k: thanks.append(a[2])))
    monkeypatch.setattr(dialog, "_load_reviews_async", lambda: fetches.append(1))

    dialog.reviews_list.setCurrentRow(0)
    dialog.report_button.click()
    assert _pump_until(qapp, lambda: len(thanks) == 1)
    assert sent == [(11, "abuse", app_context.identity.token)] and "Cảm ơn bạn" in thanks[0] and fetches == [1]


def test_cancelling_the_reason_reports_nothing(qapp, app_context, monkeypatch):
    dialog = _loaded(qapp, app_context, monkeypatch, _reviews(app_context))
    monkeypatch.setattr(dialog, "_ask_report_reason", lambda: None)
    monkeypatch.setattr("smartdoc.presentation.review_dialog.SupabaseReviewSync.report_review", lambda *a, **k: pytest.fail("nothing to send"))
    dialog.reviews_list.setCurrentRow(0)
    dialog.report_button.click()
    qapp.processEvents()
    assert dialog.report_button.isEnabled()


def test_a_report_the_server_refuses_is_explained_in_plain_words(qapp, app_context, monkeypatch):
    from PySide6.QtWidgets import QMessageBox

    dialog = _loaded(qapp, app_context, monkeypatch, _reviews(app_context))
    warnings = []
    monkeypatch.setattr(dialog, "_ask_report_reason", lambda: "spam")

    def refuse(self, review_id, reason, *, user_token):
        raise CloudReviewError("Bạn đã báo cáo bài đánh giá này rồi. Cảm ơn bạn.", code="ALREADY_REPORTED")

    monkeypatch.setattr("smartdoc.presentation.review_dialog.SupabaseReviewSync.report_review", refuse)
    monkeypatch.setattr(QMessageBox, "warning", staticmethod(lambda *a, **k: warnings.append(a[2])))
    dialog.reviews_list.setCurrentRow(0)
    dialog.report_button.click()
    assert _pump_until(qapp, lambda: len(warnings) == 1)
    assert "đã báo cáo" in warnings[0] and dialog.report_button.isEnabled()


def test_the_reason_list_uses_the_servers_codes(qapp, app_context, monkeypatch):
    from PySide6.QtWidgets import QInputDialog

    dialog = _loaded(qapp, app_context, monkeypatch, _reviews(app_context))
    monkeypatch.setattr(QInputDialog, "getItem", staticmethod(lambda parent, title, label, items, current, editable: ("Lộ thông tin cá nhân", True)))
    assert dialog._ask_report_reason() == "privacy"
    monkeypatch.setattr(QInputDialog, "getItem", staticmethod(lambda *a: ("", False)))
    assert dialog._ask_report_reason() is None
