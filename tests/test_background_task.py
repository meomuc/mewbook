# SPDX-License-Identifier: AGPL-3.0-or-later
"""Quiet housekeeping says what it is doing (status bar), but never flashes for a job that ends at once."""
from __future__ import annotations

from smartdoc.application.background_task import TASK_FILE_CHECK, TASK_READ_TEXT, TaskReporter
from smartdoc.core.event_bus import BackgroundTaskEvent, EventBus


class _Clock:
    def __init__(self) -> None:
        self.now = 100.0

    def __call__(self) -> float:
        return self.now


def _reporter(clock, total=100):
    bus = EventBus()
    seen: list[BackgroundTaskEvent] = []
    bus.subscribe(BackgroundTaskEvent, seen.append)
    return TaskReporter(bus, TASK_FILE_CHECK, total, clock=clock), seen


def test_a_job_that_ends_within_the_quiet_time_says_nothing(app_context):
    clock = _Clock()
    reporter, seen = _reporter(clock)
    for _ in range(50):
        reporter.step()
    clock.now += 0.9
    reporter.step()
    reporter.finish()
    assert seen == []


def test_a_longer_job_reports_at_a_calm_pace_then_says_it_is_finished(app_context):
    clock = _Clock()
    reporter, seen = _reporter(clock, total=1000)
    clock.now += 1.5
    reporter.step(10)  # first word after the quiet time
    reporter.step(10)  # too soon after: skipped
    clock.now += 0.6
    reporter.step(10)
    reporter.finish()
    assert [(e.done, e.total, e.finished) for e in seen] == [(10, 1000, False), (30, 1000, False), (30, 1000, True)]


def test_no_bus_no_problem():
    reporter = TaskReporter(None, TASK_READ_TEXT, 5, quiet_seconds=0)
    reporter.step()
    reporter.finish()


def test_the_start_up_checks_use_it(app_context, tmp_path):
    for n in range(3):
        (tmp_path / f"{n}.pdf").write_bytes(b"x")
        app_context.db.add_or_update_document(f"d{n}", {"title": "t", "author": "a", "file_path": str(tmp_path / f"{n}.pdf"), "created_at": 1.0})
    seen: list[BackgroundTaskEvent] = []
    app_context.event_bus.subscribe(BackgroundTaskEvent, seen.append)
    assert app_context.relink.check_files() == 0  # quick: silent, and the result is unchanged
    assert seen == []


def test_counts_for_the_backfills(app_context):
    for n, ext in enumerate(("epub", "pdf", "mobi")):
        app_context.db.add_or_update_document(f"d{n}", {"title": "t", "author": "a", "file_path": f"{n}.{ext}", "extension": ext, "created_at": 1.0})
    assert app_context.db.count_documents_without_text(("epub", "mobi")) == 2
    assert app_context.db.count_documents_missing_fingerprint() == 3


def test_the_status_bar_shows_and_clears_the_background_work(qapp, app_context):
    """S3: the status bar shows a themed task icon + a short 'done/total' count now, not a full sentence --
    the full description moved entirely into the tooltip (both the icon's and the label's)."""
    from smartdoc.presentation.status_bar_panel import StatusBarPanel

    bar = StatusBarPanel(app_context)
    bar._on_bridged_event(BackgroundTaskEvent(TASK_READ_TEXT, 120, 800))
    assert bar.activity_icon.isVisibleTo(bar) and bar.activity_label.text() == "120/800"
    assert "tìm được theo nội dung" in bar.activity_label.toolTip()
    assert "tìm được theo nội dung" in bar.activity_icon.toolTip()
    bar._on_bridged_event(BackgroundTaskEvent("folder-scan", 900, 0))  # no total known: no count shown
    assert "theo dõi có file mới" in bar.activity_icon.toolTip() and "900" not in bar.activity_label.text()
    bar._on_bridged_event(BackgroundTaskEvent(TASK_READ_TEXT, 800, 800, finished=True))
    bar._on_bridged_event(BackgroundTaskEvent("folder-scan", 900, 0, finished=True))
    assert not bar.activity_icon.isVisibleTo(bar) and bar.activity_label.text() == ""
    bar.deleteLater()


# -- the trash reports how far it got -------------------------------------------------------------------------------------------

def test_moving_to_the_trash_reports_each_file_and_reads_collections_once(app_context, tmp_path, monkeypatch):
    for n in range(4):
        (tmp_path / f"{n}.pdf").write_bytes(b"x" * (n + 1))
        app_context.db.add_or_update_document(f"d{n}", {"title": f"t{n}", "author": "a", "file_path": str(tmp_path / f"{n}.pdf"), "created_at": 1.0})
    asked = []
    real = app_context.db.list_collection_document_ids
    monkeypatch.setattr(app_context.db, "list_collection_document_ids", lambda cid: asked.append(cid) or real(cid))
    told = []
    result = app_context.trash.send([(f"d{n}", str(tmp_path / f"{n}.pdf")) for n in range(4)], lambda done, total: told.append((done, total)))
    assert len(result.moved) == 4 and told == [(0, 4), (1, 4), (2, 4), (3, 4)]
    collections = len(app_context.db.list_collections())
    assert len(asked) == collections  # once per collection for the whole list, not once per book


def test_emptying_the_trash_reports_progress(app_context, tmp_path):
    for n in range(3):
        (tmp_path / f"{n}.pdf").write_bytes(b"x")
        app_context.db.add_or_update_document(f"d{n}", {"title": "t", "author": "a", "file_path": str(tmp_path / f"{n}.pdf"), "created_at": 1.0})
    app_context.trash.send([(f"d{n}", str(tmp_path / f"{n}.pdf")) for n in range(3)])
    told = []
    assert app_context.trash.empty(lambda done, total: told.append((done, total))) == 3
    assert told == [(0, 3), (1, 3), (2, 3)]
