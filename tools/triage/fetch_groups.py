# SPDX-License-Identifier: AGPL-3.0-or-later
"""Reads the two filtered views with the read-only role and picks the day's groups (S1e, E-10; spec 6.1).

`v_triage_groups` and `v_triage_samples` (application/sql/003_error_reports.sql) are all the `triage_reader` role can see:
groups and frame lists, no user note, no log, no manual reports. What comes back is still untrusted (anybody with the public
key can send a report), so nothing here is passed on as it is: `select_groups` keeps only well-formed groups and
`build_agent_input` re-checks every value.

Which groups (defaults of docs/handoff/09 section 13, O19): a bug that is **new** or **reopened** and has not been summarised
yet, or one that has **spiked** since the last summary; a crash, or a problem seen on at least two different computers; the
crashes first, then the ones on most computers; at most `max_groups` a day (5).
"""
from __future__ import annotations

import logging
from collections.abc import Mapping
from datetime import datetime, timedelta, timezone

import requests

from tools.triage import schema
from tools.triage.config import TriageConfig

logger = logging.getLogger(__name__)

TIMEOUT_SECONDS = 15
LOOKBACK = timedelta(hours=48)
MIN_INSTALLS_FOR_WORKER_CRASH = 2
SPIKE_MINIMUM = 10
GROUP_COLUMNS = ("fingerprint_stable,exception_type,feature_area,process_kind,source,first_seen,last_seen,occurrence_count,"
                 "distinct_installs,versions_affected,status")
SAMPLE_COLUMNS = "report_id,received_at,app_version,build_id,exception_type,stack_frames"


class TriageFetchError(Exception):
    """The server could not be read (network, key, role); the run fails and counts toward the three-failure brake."""


def select_groups(rows: list[object], seen: Mapping[str, Mapping[str, object]], limit: int) -> list[dict[str, object]]:
    """The groups to look at today. Pure: `seen` is what earlier runs recorded ({fingerprint: {"count": n, "date": "..."}})."""
    picked: list[dict[str, object]] = []
    for row in rows:
        group = schema.clean_group(row)
        if group is None or group["status"] in ("fixed", "wontfix"):
            continue
        if group["source"] != "crash" and group["distinct_installs"] < MIN_INSTALLS_FOR_WORKER_CRASH:
            continue
        previous = seen.get(str(group["fingerprint_stable"]))
        if previous is None:
            wanted = group["status"] in ("new", "reopened")
        else:
            count = int(previous.get("count", 0))
            spiked = group["occurrence_count"] - count >= max(SPIKE_MINIMUM, count // 2)
            reopened = group["status"] == "reopened" and str(group["last_seen"]) > str(previous.get("date", ""))
            wanted = spiked or reopened
        if wanted:
            picked.append({**group, "exception_type": row.get("exception_type") if isinstance(row, dict) else None})
    picked.sort(key=lambda g: (0 if g["source"] == "crash" else 1, -int(g["distinct_installs"]), -int(g["occurrence_count"]), str(g["fingerprint_stable"])))
    return picked[:limit]


class GroupFetcher:
    def __init__(self, config: TriageConfig, *, session: requests.Session | None = None) -> None:
        self._config = config
        self._session = session or requests.Session()

    def _get(self, view: str, params: dict[str, str]) -> list[object]:
        headers = {"apikey": self._config.api_key, "Authorization": f"Bearer {self._config.reader_token}", "Accept": "application/json"}
        try:
            response = self._session.get(f"{self._config.supabase_url}/rest/v1/{view}", params=params, headers=headers, timeout=TIMEOUT_SECONDS)
        except requests.RequestException as exc:
            raise TriageFetchError(f"cannot reach the server ({type(exc).__name__})") from exc
        if not response.ok:
            raise TriageFetchError(f"the server refused the read of {view} (HTTP {response.status_code})")
        try:
            rows = response.json()
        except ValueError as exc:
            raise TriageFetchError(f"{view} did not answer with JSON") from exc
        if not isinstance(rows, list):
            raise TriageFetchError(f"{view} did not answer with a list")
        return rows

    def recent_groups(self, now: datetime | None = None) -> list[object]:
        """Every group seen in the last 48 hours (the day's candidates before the selection)."""
        since = ((now or datetime.now(timezone.utc)) - LOOKBACK).strftime("%Y-%m-%dT%H:%M:%SZ")
        return self._get("v_triage_groups", {"select": GROUP_COLUMNS, "last_seen": f"gte.{since}", "order": "last_seen.desc", "limit": "200"})

    def samples(self, fingerprint: str) -> list[object]:
        """The newest few samples of one group (frames and versions only)."""
        if not schema.clean_hash(fingerprint):
            raise TriageFetchError("not a fingerprint")
        return self._get("v_triage_samples", {
            "select": SAMPLE_COLUMNS, "fingerprint_stable": f"eq.{fingerprint}", "order": "received_at.desc", "limit": str(schema.MAX_SAMPLES),
        })


class StatusWriter:
    """Level L1: marks a group "triaged" through the one function the triage_writer role may call. The note is a fixed
    sentence made by the orchestrator; nothing the agent wrote is ever sent back to the server."""

    def __init__(self, config: TriageConfig, *, session: requests.Session | None = None) -> None:
        self._config = config
        self._session = session or requests.Session()

    def set_status(self, fingerprint: str, status: str, note: str = "") -> None:
        if not schema.clean_hash(fingerprint) or status not in ("triaged", "fix_proposed"):
            raise TriageFetchError("not a status the writer may set")
        headers = {"apikey": self._config.api_key, "Authorization": f"Bearer {self._config.writer_token}", "Content-Type": "application/json"}
        try:
            response = self._session.post(
                f"{self._config.supabase_url}/rest/v1/rpc/triage_set_status", headers=headers,
                json={"p_fingerprint": fingerprint, "p_status": status, "p_note": note[:500]}, timeout=TIMEOUT_SECONDS,
            )
        except requests.RequestException as exc:
            raise TriageFetchError(f"cannot reach the server ({type(exc).__name__})") from exc
        if not response.ok:
            raise TriageFetchError(f"the server refused the status change (HTTP {response.status_code})")
