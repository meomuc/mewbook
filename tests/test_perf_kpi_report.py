# SPDX-License-Identifier: AGPL-3.0-or-later
"""tools/eval/perf_kpi_report.py's pure parsing/stats functions -- imported directly via sys.path,
mirroring the way the tool itself adds src/ to sys.path to reach smartdoc."""
from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "tools" / "eval"))

from perf_kpi_report import parse_perf_lines, percentile, summarize  # noqa: E402


def test_parse_perf_lines_ignores_unrelated_log_lines():
    text = (
        "2026-10-09 10:00:01 INFO [Main] smartdoc: ==== MewBook starting ====\n"
        "2026-10-09 10:00:05 INFO [Import] smartdoc.perf: PERF op=import duration_ms=1200 items=10\n"
        "2026-10-09 10:00:06 WARNING [Main] smartdoc: unrelated warning\n"
        "2026-10-09 10:00:07 INFO [AI] smartdoc.perf: PERF op=ai_summary duration_ms=500 outcome=success\n"
    )
    records = parse_perf_lines(text)
    assert len(records) == 2
    assert records[0] == {"op": "import", "duration_ms": "1200", "items": "10"}
    assert records[1] == {"op": "ai_summary", "duration_ms": "500", "outcome": "success"}


def test_parse_perf_lines_empty_text_returns_empty_list():
    assert parse_perf_lines("") == []
    assert parse_perf_lines("no perf lines here\njust noise\n") == []


def test_percentile_with_a_single_value_does_not_crash():
    assert percentile([100.0], 95) == 100.0


def test_percentile_on_a_known_distribution():
    values = [float(v) for v in range(1, 101)]  # 1..100
    assert percentile(values, 50) == 50.5  # statistics.quantiles' exclusive-method median of 1..100


def test_summarize_groups_by_op_with_correct_stats():
    records = [
        {"op": "import", "duration_ms": "100"},
        {"op": "import", "duration_ms": "300"},
        {"op": "classify", "duration_ms": "9000"},
    ]
    report = summarize(records)
    assert set(report.keys()) == {"classify", "import"}
    assert report["import"]["count"] == 2
    assert report["import"]["mean_ms"] == 200
    assert report["import"]["min_ms"] == 100
    assert report["import"]["max_ms"] == 300
    assert report["classify"]["count"] == 1
    assert report["classify"]["suggested_watch_threshold_ms"] == 9000


def test_summarize_ignores_records_missing_op_or_duration():
    records = [{"op": "import"}, {"duration_ms": "100"}, {"op": "import", "duration_ms": "100"}]
    report = summarize(records)
    assert report["import"]["count"] == 1
