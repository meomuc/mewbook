import time

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
    assert "Chưa cấu hình" in dialog.status_label.text()


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

    def fake_submit(self, doc_id, nickname, rating, comment):
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
    assert app_context.config.config.reviewer_nickname == "Lan"

    assert _pump_until(qapp, lambda: dialog.reviews_list.count() == 1 and "Lan" in dialog.reviews_list.item(0).text(), timeout=3.0)


def test_submit_error_shows_warning_and_reenables_button(qapp, app_context, monkeypatch):
    from PySide6.QtWidgets import QMessageBox

    app_context.config.config.supabase_url = "https://fake.supabase.co"
    app_context.config.config.supabase_anon_key = "fake-key"
    monkeypatch.setattr(
        "smartdoc.presentation.review_dialog.SupabaseReviewSync.fetch_reviews", lambda self, doc_id: []
    )

    def raise_error(self, doc_id, nickname, rating, comment):
        raise CloudReviewError("network down")

    monkeypatch.setattr("smartdoc.presentation.review_dialog.SupabaseReviewSync.submit_review", raise_error)
    warnings = []
    monkeypatch.setattr(QMessageBox, "warning", staticmethod(lambda *a, **k: warnings.append(a) or QMessageBox.Ok))

    dialog = ReviewDialog(app_context, _doc())
    dialog._set_rating(3)
    dialog._on_submit()

    assert _pump_until(qapp, lambda: len(warnings) == 1, timeout=3.0)
    assert dialog.submit_button.isEnabled()
