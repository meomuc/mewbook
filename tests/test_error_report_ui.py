# SPDX-License-Identifier: AGPL-3.0-or-later
"""The error-report dialogs (E-04, FR-ERR-03, FR-ERR-04): the question, the prompt that asks it, the Settings tab and
the manual report. Acceptance scenarios ERR-A1 (nothing sent until "Gửi báo cáo"), ERR-A4 (the preview is the payload)."""
from __future__ import annotations

import json
import threading

import pytest
from PySide6.QtWidgets import QApplication

from smartdoc.application import error_reporter as rep
from smartdoc.application.error_report_queue import STATUS_APPROVED, STATUS_PENDING
from smartdoc.core.event_bus import ErrorReportApprovedEvent
from smartdoc.presentation import error_report_dialog as erd
from smartdoc.presentation.error_report_dialog import ErrorReportDialog, ErrorReportPrompt
from smartdoc.presentation.main_window import MainWindow
from smartdoc.presentation.manual_report_dialog import ManualReportDialog
from smartdoc.presentation.privacy_panel import PrivacyPanel
from smartdoc.presentation.settings_dialog import SettingsDialog

ACCOUNT = "Nguyễn Văn Ánh"
TITLE = "Đắc nhân tâm"


def _crash(message: str = "boom", filename: str = r"C:\code\smartdoc\application\import_queue.py") -> BaseException:
    namespace = {"exc": OSError}
    exec(compile(f"def explode():\n    raise exc({message!r})\n", filename, "exec"), namespace)  # noqa: S102
    try:
        namespace["explode"]()
    except BaseException as caught:  # noqa: BLE001
        return caught
    raise AssertionError("no exception")


@pytest.fixture
def reporter(app_context):
    app_context.error_reports.enabled = True  # a release build
    return app_context.error_reports


@pytest.fixture
def approved(app_context):
    heard = []
    app_context.event_bus.subscribe(ErrorReportApprovedEvent, lambda e: heard.append(e.report_id))
    return heard


def _pending(reporter, message: str = "boom", filename: str = r"C:\code\smartdoc\application\import_queue.py") -> str:
    exc = _crash(message, filename)
    report_id = reporter.capture_exception(type(exc), exc, exc.__traceback__)
    assert report_id is not None
    return report_id


# --- the question -----------------------------------------------------------------------------------------------------------

def test_the_dialog_asks_the_question_and_sends_nothing_by_itself(qapp, app_context, reporter, approved):
    """ERR-A1: opening the dialog (and looking at it) approves nothing."""
    report_id = _pending(reporter, f"cannot open {TITLE}.epub")
    dialog = ErrorReportDialog(app_context, report_id)

    assert dialog.windowTitle() == "Mèo gặp lỗi bất ngờ"
    text = dialog.question_label.text()
    assert "báo cáo lỗi ẩn danh" in text and "<b>không</b>" in text and "tên sách, đường dẫn hay nội dung tài liệu" in text
    assert "OSError" in dialog.summary_label.text() and TITLE not in dialog.summary_label.text()
    assert [dialog.preview_button.text(), dialog.send_button.text(), dialog.decline_button.text()] == [
        "Xem nội dung sẽ gửi", "Gửi báo cáo", "Không gửi",
    ]
    assert (dialog.always_check.text(), dialog.never_check.text()) == ("Luôn gửi tự động (ẩn danh)", "Không hỏi lại")
    assert reporter.pending(report_id).status == STATUS_PENDING and approved == []
    assert dialog.preview.isHidden()


def test_the_preview_shows_exactly_the_payload_that_will_be_sent(qapp, app_context, reporter):
    """ERR-A4."""
    report_id = _pending(reporter, f"{ACCOUNT} opened {TITLE}.epub")
    dialog = ErrorReportDialog(app_context, report_id)
    dialog.preview_button.click()

    assert not dialog.preview.isHidden() and dialog.preview_button.text() == "Ẩn nội dung sẽ gửi"
    shown = json.loads(dialog.preview.toPlainText())
    assert shown == reporter.pending(report_id).report.to_payload()
    assert ACCOUNT not in dialog.preview.toPlainText() and TITLE not in dialog.preview.toPlainText()
    dialog.preview_button.click()
    assert dialog.preview.isHidden() and dialog.preview_button.text() == "Xem nội dung sẽ gửi"


def test_sending_approves_the_report_and_thanks_with_its_id(qapp, app_context, reporter, approved):
    report_id = _pending(reporter)
    dialog = ErrorReportDialog(app_context, report_id)
    dialog.send_button.click()

    assert dialog.sent and reporter.pending(report_id).status == STATUS_APPROVED and approved == [report_id]
    assert dialog.thanks_label.text() == f"Cảm ơn bạn. Mã báo cáo: {report_id}" and not dialog.thanks_label.isHidden()
    assert dialog.send_button.isHidden() and not dialog.close_button.isHidden()
    assert reporter.mode() == rep.MODE_ASK  # a plain yes changes no setting


def test_send_with_the_always_box_ticked_changes_the_standing_choice(qapp, app_context, reporter):
    dialog = ErrorReportDialog(app_context, _pending(reporter))
    dialog.always_check.setChecked(True)
    dialog.send_button.click()
    assert reporter.mode() == rep.MODE_ALWAYS and reporter.effective_mode() == rep.MODE_ALWAYS


def test_not_sending_deletes_the_report_and_the_never_box_stops_the_asking(qapp, app_context, reporter, approved):
    report_id = _pending(reporter)
    dialog = ErrorReportDialog(app_context, report_id)
    dialog.decline_button.click()
    assert reporter.pending(report_id) is None and approved == [] and reporter.mode() == rep.MODE_ASK and not dialog.sent

    other = ErrorReportDialog(app_context, _pending(reporter, "other", r"C:\x\smartdoc\application\cover_search.py"))
    other.never_check.setChecked(True)
    other.decline_button.click()
    assert reporter.mode() == rep.MODE_NEVER


def test_closing_the_window_is_a_no_never_a_yes(qapp, app_context, reporter, approved):
    report_id = _pending(reporter)
    dialog = ErrorReportDialog(app_context, report_id)
    dialog.always_check.setChecked(True)  # ticked, but the answer was not "Gửi báo cáo"
    dialog.reject()  # [x] and Esc
    assert reporter.pending(report_id) is None and approved == [] and reporter.mode() == rep.MODE_ASK


def test_the_two_standing_choices_exclude_each_other(qapp, app_context, reporter):
    dialog = ErrorReportDialog(app_context, _pending(reporter))
    dialog.always_check.setChecked(True)
    dialog.never_check.setChecked(True)
    assert dialog.never_check.isChecked() and not dialog.always_check.isChecked()
    dialog.always_check.setChecked(True)
    assert dialog.always_check.isChecked() and not dialog.never_check.isChecked()


def test_a_report_that_is_gone_cannot_be_sent(qapp, app_context, reporter, approved):
    report_id = _pending(reporter)
    reporter.queue.remove(report_id)
    dialog = ErrorReportDialog(app_context, report_id)
    assert not dialog.send_button.isEnabled() and not dialog.preview_button.isEnabled() and approved == []


# --- when to ask -------------------------------------------------------------------------------------------------------------

@pytest.fixture
def asked(monkeypatch):
    """Replaces the modal loop: records which report was asked about and answers "Không gửi"."""
    shown = []

    def fake_exec(self):
        shown.append(self.report_id)
        self.decline_button.click()
        return 0

    monkeypatch.setattr(ErrorReportDialog, "exec", fake_exec)
    return shown


def test_the_prompt_asks_after_the_failing_call_has_returned_never_inside_it(qapp, app_context, reporter, asked):
    prompt = ErrorReportPrompt(app_context)
    report_id = _pending(reporter)
    assert asked == []  # the event arrived inside the "failing call": nothing may open a modal loop here
    qapp.processEvents()
    assert asked == [report_id]
    del prompt


def test_an_error_on_a_background_thread_is_asked_about_on_the_gui_thread(qapp, app_context, reporter, asked):
    prompt = ErrorReportPrompt(app_context)
    ids = []

    def fail_in_a_thread():
        exc = _crash("in a thread")
        ids.append(reporter.capture_exception(type(exc), exc, exc.__traceback__, thread_name="import-worker-3"))

    worker = threading.Thread(target=fail_in_a_thread)
    worker.start()
    worker.join()
    for _ in range(5):
        qapp.processEvents()
    assert asked == ids and ids[0] is not None
    del prompt


def test_one_dialog_at_a_time_and_the_next_report_is_asked_afterwards(qapp, app_context, reporter, monkeypatch):
    prompt = ErrorReportPrompt(app_context)
    shown, second_id = [], []

    def fake_exec(self):
        shown.append(self.report_id)
        if len(shown) == 1:  # while the first question is open, a different bug happens
            second_id.append(_pending(reporter, "second", r"C:\x\smartdoc\application\cover_search.py"))
            assert prompt.ask(second_id[0]) is False  # not stacked on top
        self.decline_button.click()
        return 0

    monkeypatch.setattr(ErrorReportDialog, "exec", fake_exec)
    first = _pending(reporter)
    for _ in range(6):
        qapp.processEvents()
    assert shown == [first, second_id[0]]


def test_at_start_up_only_the_newest_unanswered_report_is_asked_about(qapp, app_context, reporter, asked):
    """Reports an earlier session never got an answer for: one question about the newest, the older ones are dropped."""
    import itertools

    reporter.queue._clock = itertools.count(1000.0).__next__  # distinct, increasing creation times
    ids = []
    for index in range(3):
        report = reporter.build_manual(f"lỗi {index}")
        reporter.queue.add(report, STATUS_PENDING)  # queued straight into the folder, as an earlier run left them
        ids.append(report.report_id)
    prompt = ErrorReportPrompt(app_context)
    prompt.ask_about_waiting()
    assert asked == [ids[-1]]
    assert reporter.queue.items() == []  # the newest was answered ("Không gửi") and the two older ones were dropped


def test_the_prompt_does_not_ask_when_the_mode_is_never_or_always(qapp, app_context, reporter, asked):
    prompt = ErrorReportPrompt(app_context)
    report_id = _pending(reporter)
    asked.clear()  # (the live event has asked already; what follows is about a change of the standing choice)
    reporter.set_mode(rep.MODE_ALWAYS)
    assert prompt.ask(report_id) is False  # in "always" nothing is asked
    reporter.set_mode(rep.MODE_NEVER)
    prompt.ask_about_waiting()
    assert asked == []


# --- Settings -> "Quyền riêng tư và báo lỗi" -----------------------------------------------------------------------------------

def test_the_settings_tab_offers_the_three_modes_and_defaults_to_asking(qapp, app_context):
    panel = PrivacyPanel(app_context)
    assert list(panel.mode_buttons) == ["ask", "always", "never"]
    assert [b.text() for b in panel.mode_buttons.values()] == ["Hỏi mỗi lần", "Luôn gửi ẩn danh", "Không bao giờ"]
    assert panel.selected_mode() == "ask" and panel.mode_buttons["ask"].isChecked()
    assert "KHÔNG chứa tên hay đường dẫn file sách" in panel.intro_label.text()


def test_choosing_a_mode_is_applied_when_settings_are_saved(qapp, app_context, reporter):
    dialog = SettingsDialog(app_context)
    dialog.privacy_panel.mode_buttons["never"].setChecked(True)
    dialog._on_save()
    assert reporter.mode() == rep.MODE_NEVER and app_context.config.config.error_report_mode == "never"


def test_saving_settings_without_touching_the_mode_never_renews_an_old_consent(qapp, app_context, reporter):
    reporter.set_mode(rep.MODE_ALWAYS)
    app_context.config.config.error_report_consent_version = 0  # agreed to an older wording
    dialog = SettingsDialog(app_context)
    assert "hỏi lại" in dialog.privacy_panel.notice_label.text()
    dialog._on_save()
    assert app_context.config.config.error_report_consent_version == 0 and reporter.effective_mode() == rep.MODE_ASK


def test_a_source_build_says_it_collects_nothing(qapp, app_context):
    panel = PrivacyPanel(app_context)  # no reporter.enabled: a source checkout
    assert "không thu thập" in panel.notice_label.text()


def test_the_tab_lists_the_ids_of_sent_reports_and_copies_one(qapp, app_context, reporter):
    report = reporter.build_manual("x")
    reporter.submit(report)
    reporter.queue.record_sent(report)
    panel = PrivacyPanel(app_context)
    assert panel.sent_list.count() == 1 and report.report_id in panel.sent_list.item(0).text()
    assert not panel.copy_button.isEnabled()
    panel.sent_list.setCurrentRow(0)
    panel.copy_button.click()
    assert QApplication.clipboard().text() == report.report_id


def test_the_tab_shows_and_clears_the_reports_that_wait(qapp, app_context, reporter):
    _pending(reporter)
    panel = PrivacyPanel(app_context)
    assert "1 báo cáo" in panel.waiting_label.text() and panel.clear_button.isEnabled()
    panel.clear_button.click()
    assert reporter.queue.items() == [] and "Không có báo cáo nào đang chờ" in panel.waiting_label.text()
    assert not panel.clear_button.isEnabled()


# --- Help -> "Báo lỗi…" ---------------------------------------------------------------------------------------------------------

def test_a_manual_report_needs_a_description_and_a_preview_before_it_can_be_sent(qapp, app_context, reporter, approved, monkeypatch):
    # The user's Windows account is called ACCOUNT, so it is one of the strings the reporter knows and removes from the
    # note (a name typed in free text cannot be recognised any other way -- which is why there is always a preview).
    for variable in ("LOGNAME", "USER", "LNAME"):
        monkeypatch.delenv(variable, raising=False)
    monkeypatch.setenv("USERNAME", ACCOUNT)
    dialog = ManualReportDialog(app_context)
    assert not dialog.preview_button.isEnabled() and not dialog.send_button.isEnabled()

    dialog.note_edit.setPlainText(f"Mở {TITLE}.epub thì treo. Tôi là {ACCOUNT}.")
    assert dialog.preview_button.isEnabled() and not dialog.send_button.isEnabled()  # no send without a preview
    dialog.preview_button.click()
    shown = json.loads(dialog.preview.toPlainText())
    assert dialog.send_button.isEnabled() and shown["source"] == "manual"
    assert TITLE not in dialog.preview.toPlainText() and ACCOUNT not in dialog.preview.toPlainText() and "treo" in shown["user_note"]
    assert reporter.queue.items() == [] and approved == []  # still nothing queued

    dialog.send_button.click()
    (item,) = reporter.queue.items()
    assert item.status == STATUS_APPROVED and item.report.to_payload() == shown  # what was read is what is queued (ERR-A4)
    assert approved == [item.report.report_id] and dialog.sent
    assert dialog.thanks_label.text() == f"Cảm ơn bạn. Mã báo cáo: {item.report.report_id}"


def test_editing_after_the_preview_switches_the_send_button_off_again(qapp, app_context, reporter):
    dialog = ManualReportDialog(app_context)
    dialog.note_edit.setPlainText("lỗi một")
    dialog.preview_button.click()
    assert dialog.send_button.isEnabled()
    dialog.note_edit.setPlainText("lỗi hai")
    assert not dialog.send_button.isEnabled() and dialog.preview.isHidden() and "xem" in dialog.status_label.text().lower()
    dialog.preview_button.click()
    dialog.log_check.setChecked(True)  # the log box counts as an edit too
    assert not dialog.send_button.isEnabled()


def test_the_description_is_limited_to_1000_characters(qapp, app_context, reporter):
    dialog = ManualReportDialog(app_context)
    dialog.note_edit.setPlainText("x" * 1500)
    assert len(dialog.note_edit.toPlainText()) == 1000 and dialog.counter_label.text() == "1000/1000"


def test_a_source_build_cannot_send_a_manual_report(qapp, app_context):
    dialog = ManualReportDialog(app_context)  # reporter.enabled is False
    assert not dialog.note_edit.isEnabled() and not dialog.preview_button.isEnabled() and "không gửi được" in dialog.status_label.text()


def test_the_help_menu_has_the_report_action(qapp, app_context):
    window = MainWindow(app_context)
    help_menu = next(action.menu() for action in window.menuBar().actions() if action.menu() and action.text().endswith("Help"))
    assert any(action.text().endswith("Báo lỗi…") for action in help_menu.actions())
    window.hide()
    window.deleteLater()


def test_the_crash_dialog_defers_to_the_report_prompt_when_a_report_waits(qapp, monkeypatch):
    from PySide6.QtWidgets import QMessageBox

    from smartdoc import app as app_module

    shown = []
    monkeypatch.setattr(QMessageBox, "critical", lambda *args: shown.append(args))
    monkeypatch.setattr(app_module, "_crash_dialog_open", False)
    app_module._show_crash_dialog("boom", "report-id")  # the prompt asks about it: no second message
    for _ in range(3):
        qapp.processEvents()
    assert shown == []
    app_module._show_crash_dialog("boom")  # no report: the plain message, as before
    for _ in range(3):
        qapp.processEvents()
    assert len(shown) == 1


def test_the_report_hook_of_the_app_returns_the_waiting_report(qapp, app_context, reporter, monkeypatch):
    from smartdoc import app as app_module

    exc = _crash()
    monkeypatch.setattr(app_module, "_error_reporter", None)
    assert app_module._report_unhandled_exception(type(exc), exc, exc.__traceback__, "MainThread") is None  # before the context exists
    monkeypatch.setattr(app_module, "_error_reporter", reporter)
    assert app_module._report_unhandled_exception(type(exc), exc, exc.__traceback__, "MainThread") == reporter.queue.items()[0].report.report_id
    assert erd.TITLE == "Mèo gặp lỗi bất ngờ"


def test_the_tab_says_when_reports_could_not_be_sent(qapp, app_context, reporter):
    _pending(reporter)
    app_context.error_uploader.status = "retry"  # what the uploader reports after a failed attempt
    panel = PrivacyPanel(app_context)
    assert "Chưa gửi được báo cáo. Ứng dụng sẽ thử lại sau." in panel.waiting_label.text()
    reporter.queue.clear()
    panel.refresh()
    assert "Chưa gửi được" not in panel.waiting_label.text()  # nothing waits, so nothing to worry about
