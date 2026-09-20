# SPDX-License-Identifier: AGPL-3.0-or-later
"""The error reporter (E-03): consent, scrubbing of what this machine knows, storms, the manual report.
Acceptance scenarios of docs/handoff/09 section 11: ERR-A1, ERR-A2, ERR-A3, ERR-A4, ERR-A6 (the capture side)."""
from __future__ import annotations

import json
import logging
import platform

import pytest

from smartdoc.application import error_reporter as rep
from smartdoc.application.error_report_queue import STATUS_APPROVED, STATUS_PENDING
from smartdoc.core import diagnostics
from smartdoc.core.build_info import BuildInfo
from smartdoc.core.event_bus import ErrorReportApprovedEvent, ErrorReportPendingEvent

ACCOUNT = "Nguyễn Văn Ánh"
COMPUTER = "MAY-CUA-ANH"
TITLE = "Đắc nhân tâm"
AUTHOR = "Dale Carnegie"
HOME = rf"C:\Users\{ACCOUNT}"
KEY = "sk-abcdefghijklmnopqrstuvwxyz0123456789"


def _raise_in(filename: str, message: str, exc: type[BaseException] = OSError) -> BaseException:
    namespace = {"exc": exc}
    exec(compile(f"def explode():\n    raise exc({message!r})\n", filename, "exec"), namespace)  # noqa: S102
    try:
        namespace["explode"]()
    except BaseException as caught:  # noqa: BLE001
        return caught
    raise AssertionError("no exception")


def _capture(reporter, exc):
    return reporter.capture_exception(type(exc), exc, exc.__traceback__)


@pytest.fixture
def machine(monkeypatch, tmp_path):
    """A machine whose account, computer and folders carry Vietnamese names."""
    for variable in ("LOGNAME", "USER", "LNAME"):
        monkeypatch.delenv(variable, raising=False)
    monkeypatch.setenv("USERNAME", ACCOUNT)
    monkeypatch.setenv("COMPUTERNAME", COMPUTER)
    monkeypatch.setenv("USERPROFILE", HOME)
    monkeypatch.setenv("APPDATA", rf"{HOME}\AppData\Roaming")
    monkeypatch.setattr(platform, "node", lambda: COMPUTER)


@pytest.fixture
def reporter(app_context, machine):
    reporter = app_context.error_reports
    reporter.enabled = True  # a release build; a source checkout collects nothing
    return reporter


@pytest.fixture
def events(app_context):
    heard = {"pending": [], "approved": []}
    app_context.event_bus.subscribe(ErrorReportPendingEvent, lambda e: heard["pending"].append(e.report_id))
    app_context.event_bus.subscribe(ErrorReportApprovedEvent, lambda e: heard["approved"].append(e.report_id))
    return heard


def _crash(message: str = "boom"):
    return _raise_in(rf"{HOME}\code\smartdoc\application\import_queue.py", message)


# --- consent: ERR-A1, ERR-A2 --------------------------------------------------------------------------------------------------

def test_a_source_checkout_collects_nothing(app_context, machine):
    assert app_context.error_reports.enabled is False  # no build stamp, so the dev channel
    assert _capture(app_context.error_reports, _crash()) is None
    assert not (app_context.config.app_data_dir / "reports").exists()


def test_only_a_clean_release_build_is_enabled(app_context):
    release = rep.ErrorReporter(app_context.config, app_context.event_bus, build=BuildInfo("0123456789ab", "release"))
    dirty = rep.ErrorReporter(app_context.config, app_context.event_bus, build=BuildInfo("0123456789ab-dirty", "dev"))
    assert release.enabled is True and dirty.enabled is False


def test_by_default_the_user_is_asked_and_nothing_is_approved(reporter, events):
    """ERR-A1: a dialog, and nothing sent until the user chooses "Gửi báo cáo"."""
    assert reporter.mode() == rep.MODE_ASK and reporter.effective_mode() == rep.MODE_ASK
    report_id = _capture(reporter, _crash())
    assert report_id is not None
    assert events == {"pending": [report_id], "approved": []}
    item = reporter.pending(report_id)
    assert item.status == STATUS_PENDING and reporter.queue.approved() == []


def test_in_never_mode_nothing_is_collected_written_or_announced(reporter, events, app_context):
    """ERR-A2: no file in reports/ and (the uploader hears nothing, so) no connection."""
    reporter.set_mode(rep.MODE_NEVER)
    assert _capture(reporter, _crash()) is None
    assert events == {"pending": [], "approved": []}
    assert not (app_context.config.app_data_dir / "reports").exists()
    assert reporter.capture_worker_crash("worker died") is None


def test_in_always_mode_the_report_goes_straight_to_the_uploader_without_asking(reporter, events):
    reporter.set_mode(rep.MODE_ALWAYS)
    assert _capture(reporter, _crash()) is None  # nothing to ask
    (item,) = reporter.queue.items()
    assert item.status == STATUS_APPROVED
    assert events == {"pending": [], "approved": [item.report.report_id]}


def test_always_only_counts_for_the_wording_the_user_agreed_to(reporter, events, app_context):
    reporter.set_mode(rep.MODE_ALWAYS)
    assert app_context.config.config.error_report_consent_version == rep.CONSENT_VERSION
    app_context.config.config.error_report_consent_version = rep.CONSENT_VERSION - 1  # an older text was agreed to
    assert reporter.mode() == rep.MODE_ALWAYS and reporter.effective_mode() == rep.MODE_ASK
    assert _capture(reporter, _crash()) is not None and events["approved"] == []


def test_a_mistyped_mode_in_the_settings_file_reads_as_ask(app_context):
    from smartdoc.core.config import ConfigManager

    path = app_context.config.settings_path
    data = json.loads(path.read_text(encoding="utf-8"))
    data["error_report_mode"] = "alwayz"
    path.write_text(json.dumps(data), encoding="utf-8")
    assert ConfigManager(app_context.config.app_data_dir).config.error_report_mode == "ask"
    with pytest.raises(rep.ErrorReportError):
        app_context.error_reports.set_mode("alwayz")


def test_choosing_never_deletes_what_is_waiting(reporter):
    _capture(reporter, _crash())
    assert reporter.queue.items()
    reporter.set_mode(rep.MODE_NEVER)
    assert reporter.queue.items() == []


# --- what the report holds: ERR-A3, ERR-A4 ---------------------------------------------------------------------------------------

def test_the_report_holds_nothing_the_machine_knows_to_be_private(reporter, app_context):
    """ERR-A3: Windows account, computer, a Vietnamese title in the library, an absolute path, an e-mail and a key."""
    app_context.db.add_or_update_document(
        "d1", {"title": TITLE, "author": AUTHOR, "file_path": rf"D:\Sách hay\{TITLE} - {AUTHOR}.epub", "created_at": 1.0, "extension": "epub"},
        extracted_text="text",
    )
    app_context.config.config.ai_api_key = KEY
    app_context.config.config.watch_folders = [r"D:\Sách hay"]
    message = (
        f"{ACCOUNT}@{COMPUTER} cannot open {HOME}\\Documents\\Sách hay\\{TITLE}.epub: '{TITLE}' by {AUTHOR}; "
        f"mail nguyen.van.anh@gmail.com key {KEY} token {app_context.identity.token}; scanned D:\\Sách hay"
    )
    report_id = _capture(reporter, _crash(message))
    stored = (reporter.queue.directory / f"{report_id}.json").read_text(encoding="utf-8")
    preview = reporter.preview_text(report_id)
    for text in (stored, preview):
        for private in (ACCOUNT, "Nguyễn", "Ánh", COMPUTER, TITLE, "nhân", AUTHOR, "Carnegie", "Sách", "gmail", KEY, app_context.identity.token,
                        app_context.identity.user_hash, "Documents"):
            assert private not in text, f"{private!r} leaked into {text[:400]}"


def test_the_stack_holds_no_absolute_path_and_no_local_value(reporter):
    report_id = _capture(reporter, _crash())
    payload = reporter.pending(report_id).report.to_payload()
    frames = payload["stack_frames"]  # the helper's own frame (this file: an absolute path) and then the failing one
    assert frames[-1] == {"path": "smartdoc/application/import_queue.py", "function": "explode", "line": 2}
    assert all(f["path"] == "<PATH>" or f["path"].startswith(("smartdoc/", "site-packages/", "stdlib/")) for f in frames)
    assert "tests" not in json.dumps(frames) and ACCOUNT not in json.dumps(frames, ensure_ascii=False)
    assert payload["feature_area"] == "import" and payload["process_kind"] == "gui" and payload["source"] == "crash"


def test_the_preview_is_exactly_the_payload_that_is_stored_and_will_be_sent(reporter):
    """ERR-A4 (the uploader test checks the bytes that go over the wire)."""
    report_id = _capture(reporter, _crash("some message"))
    payload = reporter.pending(report_id).report.to_payload()
    assert json.loads(reporter.preview_text(report_id)) == payload
    with pytest.raises(rep.ErrorReportError):
        reporter.preview_text("00000000-0000-4000-8000-000000000000")


def test_the_context_names_the_build_the_os_and_a_separate_hashed_install_id(reporter, app_context):
    report_id = _capture(reporter, _crash())
    payload = reporter.pending(report_id).report.to_payload()
    assert payload["app_version"] and payload["build_id"] == "dev" and payload["channel"] == "dev"
    assert payload["locale"] == "vi" and payload["theme_id"] == app_context.config.config.theme
    assert payload["consent_version"] == rep.CONSENT_VERSION and payload["library_size_bucket"] == "<1k"
    assert ACCOUNT not in payload["os"] and COMPUTER not in payload["os"]
    install_id = app_context.config.config.error_report_install_id
    assert len(install_id) == 32 and install_id not in json.dumps(payload)  # only the hash leaves
    assert payload["install_hash"] == reporter.install_hash() != app_context.identity.user_hash  # not the review identity
    assert reporter.install_hash() == reporter.install_hash()  # stable


# --- storms: ERR-A6 (capture side) ----------------------------------------------------------------------------------------------

def test_the_same_bug_a_hundred_times_is_one_report(reporter, events):
    exc = _crash()
    for _ in range(100):
        _capture(reporter, exc)
    assert len(reporter.queue.items()) == 1 and len(events["pending"]) == 1


def test_the_same_bug_after_the_throttle_is_still_one_report_while_it_is_queued(reporter, monkeypatch):
    first = _capture(reporter, _crash())
    monkeypatch.setattr(rep.time, "monotonic", lambda: 10_000_000.0)  # long after the in-memory throttle expired
    assert _capture(reporter, _crash("a different message")) is None
    assert [i.report.report_id for i in reporter.queue.items()] == [first]


def test_different_bugs_are_different_reports(reporter):
    a = _capture(reporter, _crash())
    b = _capture(reporter, _raise_in(rf"{HOME}\smartdoc\application\cover_search.py", "other", ValueError))
    assert a and b and a != b and len(reporter.queue.items()) == 2


def test_a_bug_the_user_declined_is_not_asked_about_again_today(reporter, monkeypatch):
    report_id = _capture(reporter, _crash())
    reporter.decline(report_id)
    monkeypatch.setattr(rep.time, "monotonic", lambda: 10_000_000.0)
    assert _capture(reporter, _crash()) is None
    assert reporter.queue.items() == []


# --- the user's decision --------------------------------------------------------------------------------------------------------

def test_approving_marks_the_report_and_wakes_the_uploader(reporter, events):
    report_id = _capture(reporter, _crash())
    reporter.approve(report_id)
    assert reporter.pending(report_id).status == STATUS_APPROVED and events["approved"] == [report_id]
    assert reporter.mode() == rep.MODE_ASK  # a plain yes changes no setting


def test_approving_with_always_changes_the_setting(reporter):
    report_id = _capture(reporter, _crash())
    reporter.approve(report_id, always=True)
    assert reporter.mode() == rep.MODE_ALWAYS and reporter.effective_mode() == rep.MODE_ALWAYS


def test_declining_deletes_the_report_and_never_changes_the_setting_when_asked(reporter):
    report_id = _capture(reporter, _crash())
    reporter.decline(report_id, never=True)
    assert reporter.pending(report_id) is None and reporter.mode() == rep.MODE_NEVER


def test_approving_an_unknown_report_is_an_error(reporter):
    with pytest.raises(rep.ErrorReportError):
        reporter.approve("00000000-0000-4000-8000-000000000000")


# --- it never raises -------------------------------------------------------------------------------------------------------------

def test_a_failure_inside_the_reporter_is_logged_and_swallowed(reporter, monkeypatch, caplog):
    def broken():
        raise RuntimeError("the reporter itself is broken")

    monkeypatch.setattr(reporter, "known_private_strings", broken)
    with caplog.at_level(logging.ERROR):
        assert _capture(reporter, _crash()) is None
    assert "Could not make an error report" in caplog.text


def test_a_closed_database_still_lets_a_report_be_made(reporter, app_context):
    app_context.db.close()
    report_id = _capture(reporter, _crash(f"file {TITLE}.epub"))
    assert report_id is not None and TITLE not in reporter.preview_text(report_id)


def test_a_queue_that_cannot_be_written_does_not_raise(reporter, app_context):
    (app_context.config.app_data_dir / "reports").write_text("a file, not a folder", encoding="utf-8")
    assert _capture(reporter, _crash()) is None


# --- worker crashes ----------------------------------------------------------------------------------------------------------------

def test_a_worker_crash_is_a_report_without_a_stack(reporter, events):
    report_id = reporter.capture_worker_crash("The classification worker process ended abnormally")
    payload = reporter.pending(report_id).report.to_payload()
    assert payload["source"] == "worker" and payload["process_kind"] == "classify_worker"
    assert payload["exception_type"] == "BrokenExecutor" and payload["feature_area"] == "classification" and payload["stack_frames"] == []
    assert events["pending"] == [report_id]
    assert reporter.capture_worker_crash("again") is None  # the same crash is not asked about twice


# --- a report the user writes ---------------------------------------------------------------------------------------------------------

def test_a_manual_report_is_previewed_first_and_scrubbed(reporter, events):
    note = f"Tôi là {ACCOUNT}, mở {TITLE}.epub thì treo. Mail nguyen@gmail.com"
    report = reporter.build_manual(note)
    assert reporter.queue.items() == [] and events["approved"] == []  # nothing is queued before "Gửi"
    payload = report.to_payload()
    assert payload["source"] == "manual" and payload["exception_type"] == "ManualReport"
    text = json.dumps(payload, ensure_ascii=False)
    assert ACCOUNT not in text and TITLE not in text and "gmail" not in text and "treo" in text
    reporter.submit(report)
    assert reporter.queue.get(report.report_id).status == STATUS_APPROVED and events["approved"] == [report.report_id]


def test_a_manual_report_can_carry_the_scrubbed_end_of_the_log(reporter, tmp_path, monkeypatch):
    log = tmp_path / "mewbook.log"
    lines = [f"2026-09-19 10:00:{i:02d},000 INFO [MainThread] smartdoc.app: line {i}" for i in range(60)]
    lines[59] = f"2026-09-19 10:01:00,000 WARNING [import-worker-1] smartdoc.application.import_queue: cannot read {HOME}\\a b\\{TITLE}.epub for {ACCOUNT}"
    log.write_text("\n".join(lines), encoding="utf-8")
    monkeypatch.setattr(diagnostics, "_log_path", log)
    with_log = reporter.build_manual("x", include_log=True).to_payload()
    without_log = reporter.build_manual("x").to_payload()
    assert "log_tail" not in without_log
    tail = with_log["log_tail"]
    assert tail.count("\n") == 49 and tail.endswith("cannot read <USER_DIR>/<PATH> for <PRIVATE>")
    assert ACCOUNT not in tail and TITLE not in tail and "smartdoc.application.import_queue" in tail


def test_reports_can_only_be_sent_from_a_build_that_collects(app_context, machine):
    reporter = app_context.error_reports  # a source checkout
    with pytest.raises(rep.ErrorReportError):
        reporter.build_manual("x")


def test_the_reports_the_user_sent_can_be_listed(reporter):
    report = reporter.build_manual("x")
    reporter.submit(report)
    reporter.queue.record_sent(report)
    assert [record.report_id for record in reporter.sent_reports()] == [report.report_id]


def test_the_windows_account_name_is_removed_even_when_it_stands_alone(reporter):
    report_id = _capture(reporter, _crash(f"denied for {ACCOUNT} on {COMPUTER.lower()}"))
    assert "denied for" in reporter.preview_text(report_id) and ACCOUNT not in reporter.preview_text(report_id)
    assert COMPUTER.lower() not in reporter.preview_text(report_id).lower()



def test_two_manual_reports_in_a_row_are_both_sendable(reporter):
    first, second = reporter.build_manual("one"), reporter.build_manual("two")
    reporter.submit(first)
    reporter.queue.record_sent(first)
    reporter.submit(second)  # not blocked as "the same bug as the one sent a minute ago"
    assert reporter.queue.send_verdict(second.fingerprint_stable) == "ok"
    assert [i.report.report_id for i in reporter.queue.approved()] == [second.report_id]
