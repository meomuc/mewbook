# SPDX-License-Identifier: AGPL-3.0-or-later
"""The local error-report queue and its history (E-03, spec 4.2 and 4.5)."""
from __future__ import annotations

import json

import pytest

from smartdoc.application import error_report_queue as q
from smartdoc.domain import error_report as er

CONTEXT = er.ReportContext("1.1.0", "0123abc", "release", "Windows 11", "vi", "broadsheet", "a" * 64, 1)


class Clock:
    def __init__(self, now: float = 1_000_000.0) -> None:
        self.now = now

    def __call__(self) -> float:
        return self.now


def make_report(tag: str = "a", *, size: int = 0) -> er.ErrorReport:
    """A valid report whose fingerprint depends on `tag`; `size` pads the note to make it bigger."""
    frames = (er.StackFrame("smartdoc/app.py", f"fn_{tag}", 1),)
    stable, exact = er.fingerprints(f"Error{tag}", frames)
    return er.ErrorReport(
        report_id=er.new_report_id(), occurred_at="2026-09-19T10:00Z", source="crash", process_kind="gui",
        feature_area="startup", exception_type=f"Error{tag}", stack_frames=frames, message_scrubbed="m",
        fingerprint_stable=stable, fingerprint_exact=exact, context=CONTEXT, user_note="n" * size,
    )


@pytest.fixture
def clock():
    return Clock()


@pytest.fixture
def queue(tmp_path, clock):
    return q.ErrorReportQueue(tmp_path / "reports", clock=clock)


def test_nothing_is_created_until_a_report_is_added(tmp_path, queue):
    assert queue.items() == [] and queue.get(er.new_report_id()) is None and queue.sent() == []
    assert not (tmp_path / "reports").exists()
    queue.add(make_report())
    assert (tmp_path / "reports").is_dir()


def test_a_report_is_stored_as_the_exact_payload_and_read_back(queue):
    report = make_report("x")
    queue.add(report)
    stored = json.loads((queue.directory / f"{report.report_id}.json").read_text(encoding="utf-8"))
    assert stored["payload"] == report.to_payload() and stored["status"] == q.STATUS_PENDING
    item = queue.get(report.report_id)
    assert item.report == report and item.status == q.STATUS_PENDING and item.attempts == 0
    assert not list(queue.directory.glob("*.tmp"))  # written atomically


def test_reports_are_listed_oldest_first_and_approval_is_tracked(queue, clock):
    first, second = make_report("1"), make_report("2")
    queue.add(first)
    clock.now += 10
    queue.add(second)
    assert [i.report.report_id for i in queue.items()] == [first.report_id, second.report_id]
    assert queue.approved() == []
    assert queue.set_status(second.report_id, q.STATUS_APPROVED) is True
    assert [i.report.report_id for i in queue.approved()] == [second.report_id]
    assert queue.set_status(er.new_report_id(), q.STATUS_APPROVED) is False
    queue.count_attempt(second.report_id)
    assert queue.get(second.report_id).attempts == 1 and queue.get(second.report_id).status == q.STATUS_APPROVED


def test_the_oldest_reports_go_when_there_are_more_than_twenty(queue, clock):
    ids = []
    for index in range(q.MAX_FILES + 5):
        report = make_report(str(index))
        clock.now += 1
        queue.add(report)
        ids.append(report.report_id)
    kept = [item.report.report_id for item in queue.items()]
    assert len(kept) == q.MAX_FILES and kept == ids[5:]


def test_the_size_limit_evicts_the_oldest_first_and_never_the_newest(tmp_path, clock, monkeypatch):
    monkeypatch.setattr(q, "MAX_TOTAL_BYTES", 5000)  # room for a few reports of ~1.6 KB
    queue = q.ErrorReportQueue(tmp_path / "reports", clock=clock)
    ids = []
    for index in range(6):
        report = make_report(str(index), size=600)
        clock.now += 1
        queue.add(report)
        ids.append(report.report_id)
    kept = [item.report.report_id for item in queue.items()]
    assert 1 <= len(kept) < 6 and kept == ids[-len(kept):]  # the newest ones stay, in order
    on_disk = sum(p.stat().st_size for p in queue.directory.glob("*.json") if p.name != q.HISTORY_FILE_NAME)
    assert on_disk <= 5000


def test_a_file_that_is_not_a_well_formed_report_is_deleted_and_never_returned(queue):
    good = make_report("g")
    queue.add(good)
    bad_json = queue.directory / f"{er.new_report_id()}.json"
    bad_json.write_text("{not json", encoding="utf-8")
    wrong_payload = queue.directory / f"{er.new_report_id()}.json"
    wrong_payload.write_text(json.dumps({"format": 1, "status": "approved", "attempts": 0, "created_at": 1, "payload": {"a": 1}}), encoding="utf-8")
    other = queue.directory / "notes.json"
    other.write_text("{}", encoding="utf-8")
    assert [i.report.report_id for i in queue.items()] == [good.report_id]
    assert not bad_json.exists() and not wrong_payload.exists()
    assert other.exists()  # only files named like a report are touched


def test_a_report_id_is_never_used_as_a_path(queue):
    for evil in ("../x", "..\\x", "a/b", "", "not-a-uuid"):
        with pytest.raises(ValueError):
            queue._path(evil)
    assert queue.get(er.new_report_id()) is None


def test_removing_and_clearing(queue):
    a, b = make_report("a"), make_report("b")
    queue.add(a)
    queue.add(b)
    queue.remove(a.report_id)
    queue.remove(a.report_id)  # already gone: fine
    assert [i.report.report_id for i in queue.items()] == [b.report_id]
    assert queue.clear() == 1 and queue.items() == []


def test_a_queue_that_cannot_be_written_says_so(tmp_path):
    blocked = tmp_path / "reports"
    blocked.write_text("a file where the folder should be", encoding="utf-8")
    with pytest.raises(q.ErrorReportQueueError):
        q.ErrorReportQueue(blocked).add(make_report())


# --- history and the send rules ------------------------------------------------------------------------------------------

def test_a_sent_report_is_recorded_without_its_content_and_its_file_is_deleted(queue, clock):
    report = make_report("s")
    queue.add(report, q.STATUS_APPROVED)
    queue.record_sent(report)
    assert queue.items() == []
    (record,) = queue.sent()
    assert (record.report_id, record.fingerprint_stable, record.sent_at) == (report.report_id, report.fingerprint_stable, clock.now)
    history_text = (queue.directory / q.HISTORY_FILE_NAME).read_text(encoding="utf-8")
    assert report.message_scrubbed not in history_text and "stack_frames" not in history_text


def test_the_same_bug_is_not_sent_twice_in_24_hours(queue, clock):
    report = make_report("d")
    assert queue.send_verdict(report.fingerprint_stable) == q.VERDICT_OK
    queue.record_sent(report)
    assert queue.send_verdict(report.fingerprint_stable) == q.VERDICT_DUPLICATE
    clock.now += q.DUPLICATE_WINDOW_SECONDS - 1
    assert queue.send_verdict(report.fingerprint_stable) == q.VERDICT_DUPLICATE
    clock.now += 2
    assert queue.send_verdict(report.fingerprint_stable) == q.VERDICT_OK


def test_at_most_ten_reports_go_out_in_24_hours(queue, clock):
    for index in range(q.MAX_SENT_PER_DAY):
        queue.record_sent(make_report(f"n{index}"))
        clock.now += 60
    fresh = make_report("fresh")
    assert queue.send_verdict(fresh.fingerprint_stable) == q.VERDICT_DAILY_LIMIT
    clock.now += q.DUPLICATE_WINDOW_SECONDS
    assert queue.send_verdict(fresh.fingerprint_stable) == q.VERDICT_OK


def test_a_bug_is_known_while_queued_recently_sent_or_recently_declined(queue, clock):
    queued, sent, declined, unknown = make_report("q"), make_report("s"), make_report("d"), make_report("u")
    queue.add(queued)
    queue.add(sent)
    queue.record_sent(sent)
    queue.record_declined(declined.fingerprint_stable)
    assert queue.is_known(queued.fingerprint_stable)
    assert queue.is_known(sent.fingerprint_stable)
    assert queue.is_known(declined.fingerprint_stable)
    assert not queue.is_known(unknown.fingerprint_stable)
    queue.remove(queued.report_id)
    assert not queue.is_known(queued.fingerprint_stable)
    clock.now += q.DUPLICATE_WINDOW_SECONDS + 1
    assert not queue.is_known(sent.fingerprint_stable) and not queue.is_known(declined.fingerprint_stable)


def test_the_history_is_pruned_by_age_and_count_and_survives_corruption(queue, clock):
    old, new = make_report("old"), make_report("new")
    queue.record_sent(old)
    clock.now += q.SENT_KEEP_SECONDS + 1
    queue.record_sent(new)
    assert [r.report_id for r in queue.sent()] == [new.report_id]  # the old record aged out when the history was written
    for index in range(q.MAX_SENT_RECORDS + 10):
        queue.record_sent(make_report(f"c{index}"))
    assert len(queue.sent()) == q.MAX_SENT_RECORDS
    (queue.directory / q.HISTORY_FILE_NAME).write_text("][", encoding="utf-8")
    assert queue.sent() == [] and queue.send_verdict("f" * 64) == q.VERDICT_OK
    queue.record_sent(make_report("after"))  # and writing again just works
    assert len(queue.sent()) == 1
