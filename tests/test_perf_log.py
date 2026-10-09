# SPDX-License-Identifier: AGPL-3.0-or-later
"""log_perf() writes exactly one structured, grep-able PERF line per call."""
from __future__ import annotations

import logging

from smartdoc.core.perf_log import log_perf


def test_log_perf_formats_one_structured_line(caplog):
    with caplog.at_level(logging.INFO, logger="smartdoc.perf"):
        log_perf("import", 1.234, items=10, success=9, failed=1)
    assert len(caplog.records) == 1
    msg = caplog.records[0].message
    assert "op=import" in msg
    assert "duration_ms=1234" in msg
    assert "items=10" in msg
    assert "success=9" in msg
    assert "failed=1" in msg


def test_log_perf_rounds_sub_millisecond_duration_to_zero_without_crashing(caplog):
    with caplog.at_level(logging.INFO, logger="smartdoc.perf"):
        log_perf("ai_summary", 0.0004, outcome="success")
    assert "duration_ms=0" in caplog.records[0].message


def test_log_perf_with_no_extra_fields(caplog):
    with caplog.at_level(logging.INFO, logger="smartdoc.perf"):
        log_perf("classify", 2.0)
    msg = caplog.records[0].message
    assert msg == "PERF op=classify duration_ms=2000"
