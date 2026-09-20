# SPDX-License-Identifier: AGPL-3.0-or-later
"""The Supabase SQL, run for real (S2-02, S2-07, E-07, E-09): 001, 002 and 003 applied to an embedded PostgreSQL that has
the roles and default privileges Supabase gives a project (anon, authenticated, service_role, authenticator), and then
used the way the app and an attacker holding only the public anon key would use them.

This is optional: it needs two packages that are not project dependencies and are not installed by `uv sync`
(`uv pip install pgserver psycopg2-binary`), and it skips itself without them, so CI and a plain checkout never need a
database. It is the nearest thing to running the migration on the real project before the owner does.

Stand-ins for what a real Supabase project has and this server lacks: `extensions.digest` (pgcrypto is not in the embedded
build; sha256 of the same bytes) and PostgREST (a request is `set role <the key's role>` and then the statement).
"""
from __future__ import annotations

import copy
import hashlib
import itertools
import json
import secrets
from contextlib import closing
from pathlib import Path
from types import SimpleNamespace
from urllib.parse import urlsplit

import pytest

pgserver = pytest.importorskip("pgserver", reason="optional: uv pip install pgserver psycopg2-binary")
psycopg2 = pytest.importorskip("psycopg2", reason="optional: uv pip install pgserver psycopg2-binary")
from psycopg2 import errors as pgerrors  # noqa: E402
from psycopg2.extras import RealDictCursor  # noqa: E402

from smartdoc.domain import error_report as er  # noqa: E402

SQL_DIR = Path(__file__).resolve().parents[1] / "src" / "smartdoc" / "application" / "sql"

ROLES = """
create role anon nologin noinherit;
create role authenticated nologin noinherit;
create role service_role nologin noinherit bypassrls;
create role authenticator noinherit login password 'x';
grant anon, authenticated, service_role to authenticator;
"""

# The 1.0.0 review tables from application/cloud_reviews.py's docstring, and what a Supabase project grants by default.
BASE_SCHEMA = """
create schema if not exists extensions;
create function extensions.digest(text, text) returns bytea language sql immutable as $$ select sha256(convert_to($1, 'UTF8')) $$;
grant usage on schema public, extensions to anon, authenticated, service_role;
alter default privileges in schema public grant all on tables to anon, authenticated, service_role;
alter default privileges in schema public grant all on functions to anon, authenticated, service_role;
alter default privileges in schema public grant all on sequences to anon, authenticated, service_role;

create table reviews (
  id bigint generated always as identity primary key,
  doc_id text not null,
  nickname text not null default 'Ẩn danh',
  rating int2 not null check (rating between 1 and 5),
  comment text not null default '',
  created_at timestamptz not null default now()
);
alter table reviews enable row level security;
create policy "Allow public read" on reviews for select using (true);
create policy "Allow public insert" on reviews for insert with check (true);
create view review_stats as
  select doc_id, avg(rating)::float8 as avg_rating, count(*) as review_count from reviews group by doc_id;
grant select on review_stats to anon, authenticated;
"""


def _sql(name: str) -> str:
    text = (SQL_DIR / name).read_text(encoding="utf-8")
    return text.replace("create extension if not exists pgcrypto with schema extensions;", "")  # not in the embedded build


class Db:
    """One throw-away database of the embedded server; every call is its own connection, like a REST request."""

    def __init__(self, parts, name: str) -> None:
        self._parts, self.name = parts, name

    def _connect(self, role: str | None):
        conn = psycopg2.connect(host=self._parts.hostname, port=self._parts.port, user="postgres", dbname=self.name)
        conn.autocommit = True
        if role:
            conn.cursor().execute(f"set role {role}")
        return conn

    def run(self, sql: str, params=None, *, role: str | None = None) -> list[dict]:
        with closing(self._connect(role)) as conn, conn.cursor(cursor_factory=RealDictCursor) as cur:
            cur.execute(sql, params)
            return [dict(row) for row in cur.fetchall()] if cur.description else []

    def one(self, sql: str, params=None, *, role: str | None = None):
        rows = self.run(sql, params, role=role)
        return next(iter(rows[0].values())) if rows else None

    def error(self, sql: str, params=None, *, role: str | None = None) -> psycopg2.Error:
        try:
            self.run(sql, params, role=role)
        except psycopg2.Error as exc:
            return exc
        raise AssertionError("the statement was expected to fail")

    def message(self, sql: str, params=None, *, role: str | None = "anon") -> str:
        """The primary message of an error raised by the SQL itself (the codes the app maps, e.g. RATE_LIMITED)."""
        exc = self.error(sql, params, role=role)
        assert isinstance(exc, pgerrors.RaiseException), f"not a raised code: {exc}"
        return exc.diag.message_primary

    def denied(self, sql: str, params=None, *, role: str = "anon") -> None:
        assert isinstance(self.error(sql, params, role=role), pgerrors.InsufficientPrivilege)

    def apply(self, name: str) -> None:
        self.run(_sql(name))

    def flag(self, key: str, value: str) -> None:
        self.run("update public.service_flags set value = %s where key = %s", (value, key))


@pytest.fixture(scope="session")
def server(tmp_path_factory):
    srv = pgserver.get_server(tmp_path_factory.mktemp("pgdata"), cleanup_mode="stop")
    parts = urlsplit(srv.get_uri())
    admin = Db(parts, "postgres")
    admin.run(ROLES)
    with closing(psycopg2.connect(host=parts.hostname, port=parts.port, user="postgres", dbname="postgres")) as conn:
        conn.autocommit = True
        conn.cursor().execute("create database stage_001")
    stage = Db(parts, "stage_001")
    stage.run(BASE_SCHEMA)
    stage.apply("001_reviewer_identity.sql")  # what a 1.0.0 project has
    yield SimpleNamespace(parts=parts, counter=itertools.count())
    srv.cleanup()


def _new_db(server, *stages: str) -> Db:
    name = f"t_{next(server.counter)}"
    with closing(psycopg2.connect(host=server.parts.hostname, port=server.parts.port, user="postgres", dbname="postgres")) as conn:
        conn.autocommit = True
        conn.cursor().execute(f"create database {name} template stage_001")
    db = Db(server.parts, name)
    for stage in stages:
        db.apply(stage)
    return db


@pytest.fixture
def db_001(server) -> Db:
    return _new_db(server)


@pytest.fixture
def db_002(server) -> Db:
    return _new_db(server, "002_review_moderation.sql")


@pytest.fixture
def db_003(server) -> Db:
    return _new_db(server, "002_review_moderation.sql", "003_error_reports.sql")


# --- helpers that speak like the app ---------------------------------------------------------------------------------------------

def new_token() -> str:
    return secrets.token_urlsafe(32)


def hash_of(token: str) -> str:
    return hashlib.sha256(token.encode("utf-8")).hexdigest()


def submit(db: Db, token: str, doc: str = "doc-1", nick: str = "Lan", rating: int = 5, comment: str = "Hay", review_id=None) -> dict:
    (row,) = db.run("select * from public.submit_review(%s, %s, %s, %s, %s, %s)", (token, doc, nick, rating, comment, review_id), role="anon")
    return row


def visible(db: Db, doc: str = "doc-1") -> list[dict]:
    return db.run("select * from public.reviews where doc_id = %s order by created_at desc", (doc,), role="anon")


def report(db: Db, token: str, review_id: int, reason: str = "spam") -> int:
    return db.one("select public.report_review(%s, %s, %s)", (token, review_id, reason), role="anon")


# =====================================================================================================================
# S2: review moderation (002)
# =====================================================================================================================

def test_a_1_0_0_client_keeps_working_after_the_upgrade(db_002):
    token = new_token()
    row = submit(db_002, token, nick="Lan", comment="Hay lắm")
    assert row["user_hash"] == hash_of(token) and row["is_hidden"] is False  # the same hash 001 stores
    assert [r["nickname"] for r in visible(db_002)] == ["Lan"]
    stats = db_002.run("select * from public.review_stats", role="anon")
    assert stats == [{"doc_id": "doc-1", "avg_rating": 5.0, "review_count": 1}]  # the view keeps its three columns
    assert db_002.one("select user_hash from public.reviewers where nickname_key = 'lan'", role="anon") == hash_of(token)
    edited = submit(db_002, token, nick="Lan", rating=4, comment="Sửa", review_id=row["id"])
    assert (edited["rating"], edited["comment"]) == (4, "Sửa")
    assert db_002.message("select * from public.submit_review(%s,'d','Lan',3,'x',null)", (new_token(),)) == "NICKNAME_TAKEN"
    assert db_002.message("select * from public.submit_review(%s,'d','Lan',3,'x',%s)", (new_token(), row["id"])) == "NICKNAME_TAKEN"
    assert db_002.message("select * from public.submit_review(%s,'d','Other',3,'x',%s)", (new_token(), row["id"])) == "REVIEW_NOT_OWNED"
    assert db_002.message("select * from public.submit_review('short','d','x',3,'x',null)") == "INVALID_TOKEN"
    assert db_002.message("select * from public.submit_review(%s,'d','x',9,'x',null)", (new_token(),)) == "INVALID_RATING"


def test_the_old_public_read_policy_is_gone_so_a_hidden_review_cannot_leak(db_002):
    policies = db_002.run("select policyname from pg_policies where schemaname = 'public' and tablename = 'reviews'")
    assert [p["policyname"] for p in policies] == ["Public read visible reviews"]


def test_a_hidden_review_is_invisible_to_the_public_and_to_the_stats_but_not_to_the_owner(db_002):
    row = submit(db_002, new_token())
    other = submit(db_002, new_token(), nick="Mai", rating=3)
    db_002.run("update public.reviews set is_hidden = true, hidden_reason = 'abuse', hidden_at = now() where id = %s", (row["id"],))
    assert [r["nickname"] for r in visible(db_002)] == ["Mai"]
    assert db_002.run("select avg_rating, review_count from public.review_stats", role="anon") == [{"avg_rating": 3.0, "review_count": 1}]
    assert db_002.one("select count(*) from public.reviews where doc_id = 'doc-1'") == 2  # you still see both
    db_002.run("update public.reviews set is_hidden = false, hidden_reason = null, hidden_at = null where id = %s", (row["id"],))
    assert len(visible(db_002)) == 2 and other["id"] != row["id"]


def test_three_different_people_hide_a_review_and_nobody_can_pad_the_count(db_002):
    author = submit(db_002, new_token())
    reporters = [new_token() for _ in range(3)]
    assert report(db_002, reporters[0], author["id"]) == 1
    assert db_002.message("select public.report_review(%s, %s, 'spam')", (reporters[0], author["id"])) == "ALREADY_REPORTED"
    assert report(db_002, reporters[1], author["id"], "abuse") == 2 and len(visible(db_002)) == 1
    assert report(db_002, reporters[2], author["id"], "illegal") == 3
    assert visible(db_002) == []  # hidden
    hidden = db_002.run("select is_hidden, hidden_reason, hidden_at is not null as stamped from public.reviews")[0]
    assert hidden == {"is_hidden": True, "hidden_reason": "auto: 3 reports", "stamped": True}


def test_reports_are_refused_for_own_unknown_and_badly_labelled_reviews(db_002):
    token = new_token()
    row = submit(db_002, token)
    assert db_002.message("select public.report_review(%s, %s, 'spam')", (token, row["id"])) == "CANNOT_REPORT_OWN"
    assert db_002.message("select public.report_review(%s, 999999, 'spam')", (new_token(),)) == "REVIEW_NOT_FOUND"
    assert db_002.message("select public.report_review(%s, %s, 'because')", (new_token(), row["id"])) == "INVALID_REASON"
    assert db_002.message("select public.report_review('short', %s, 'spam')", (row["id"],)) == "INVALID_TOKEN"
    assert report(db_002, new_token(), row["id"], "  SPAM ") == 1  # the reason is trimmed and lower-cased


def test_a_dismissed_report_no_longer_counts_toward_hiding(db_002):
    row = submit(db_002, new_token())
    report(db_002, new_token(), row["id"])
    report(db_002, new_token(), row["id"])
    db_002.run("update public.review_reports set dismissed_at = now() where review_id = %s", (row["id"],))  # the moderator said "fine"
    assert report(db_002, new_token(), row["id"]) == 1 and len(visible(db_002)) == 1


def test_a_flood_of_reporters_cannot_hide_more_than_the_hourly_cap(db_002):
    db_002.flag("max_auto_hides_per_hour", "1")
    first, second = submit(db_002, new_token(), doc="a", nick="A"), submit(db_002, new_token(), doc="b", nick="B")
    for review in (first, second):
        for _ in range(3):
            report(db_002, new_token(), review["id"])
    assert visible(db_002, "a") == [] and len(visible(db_002, "b")) == 1  # the second reached the threshold but stays until you decide
    assert db_002.one("select count(*) from public.review_reports where review_id = %s", (second["id"],)) == 3  # the reports are still there for you


def test_the_threshold_and_the_report_limit_come_from_the_switches(db_002):
    db_002.flag("auto_hide_threshold", "1")
    row = submit(db_002, new_token())
    assert report(db_002, new_token(), row["id"]) == 1 and visible(db_002) == []
    db_002.flag("max_reports_per_day", "2")
    token = new_token()
    others = [submit(db_002, new_token(), doc=f"d{i}", nick=f"N{i}") for i in range(3)]
    report(db_002, token, others[0]["id"])
    report(db_002, token, others[1]["id"])
    assert db_002.message("select public.report_review(%s, %s, 'spam')", (token, others[2]["id"])) == "RATE_LIMITED"


def test_the_kill_switch_stops_writing_and_reporting_but_not_reading(db_002):
    row = submit(db_002, new_token())
    db_002.flag("reviews_enabled", "false")
    assert db_002.message("select * from public.submit_review(%s,'d','x',3,'x',null)", (new_token(),)) == "REVIEWS_DISABLED"
    assert db_002.message("select public.report_review(%s, %s, 'spam')", (new_token(), row["id"])) == "REVIEWS_DISABLED"
    assert len(visible(db_002)) == 1  # reading still works
    assert db_002.one("select value from public.service_flags where key = 'reviews_enabled'", role="anon") == "false"  # and the app can see why
    db_002.flag("banner_message", "Bảo trì tới 22h")
    assert db_002.one("select value from public.service_flags where key = 'banner_message'", role="anon") == "Bảo trì tới 22h"


def test_a_blocked_identity_cannot_post_or_report(db_002):
    token = new_token()
    row = submit(db_002, new_token(), nick="Lan")
    db_002.run("insert into public.blocked_identities (user_hash, reason) values (%s, 'spam')", (hash_of(token),))
    assert db_002.message("select * from public.submit_review(%s,'d','x',3,'x',null)", (token,)) == "IDENTITY_BLOCKED"
    assert db_002.message("select public.report_review(%s, %s, 'spam')", (token, row["id"])) == "IDENTITY_BLOCKED"
    db_002.run("delete from public.blocked_identities where user_hash = %s", (hash_of(token),))
    assert submit(db_002, token, nick="Mai")["nickname"] == "Mai"  # unblocked


def test_new_reviews_are_rate_limited_per_hour_per_day_and_globally_but_edits_are_not(db_002):
    token = new_token()
    rows = [submit(db_002, token, doc=f"d{i}") for i in range(10)]
    assert db_002.message("select * from public.submit_review(%s,'d10','Lan',5,'x',null)", (token,)) == "RATE_LIMITED"
    assert submit(db_002, token, doc="d0", comment="sửa", review_id=rows[0]["id"])["comment"] == "sửa"  # editing is not posting more
    assert submit(db_002, new_token(), nick="Mai", doc="d10")["nickname"] == "Mai"  # somebody else is not affected

    db_002.flag("max_reviews_per_hour", "100")
    db_002.flag("max_reviews_per_day", "10")
    assert db_002.message("select * from public.submit_review(%s,'d11','Lan',5,'x',null)", (token,)) == "RATE_LIMITED"  # the day limit
    db_002.flag("max_reviews_per_day", "100")
    db_002.flag("max_reviews_global_per_hour", "11")
    assert db_002.message("select * from public.submit_review(%s,'d12','Zed',5,'x',null)", (new_token(),)) == "RATE_LIMITED"  # everybody


def test_a_review_older_than_the_window_does_not_count(db_002):
    token = new_token()
    for i in range(10):
        submit(db_002, token, doc=f"d{i}")
    db_002.run("update public.reviews set created_at = now() - interval '2 hours' where user_hash = %s", (hash_of(token),))
    assert submit(db_002, token, doc="fresh")["doc_id"] == "fresh"  # the hourly count is back to zero (the daily one is 11 of 30)


def test_comment_and_nickname_limits(db_002):
    token = new_token()
    assert len(submit(db_002, token, comment="x" * 2000)["comment"]) == 2000
    assert db_002.message("select * from public.submit_review(%s,'d2','Lan',5,%s,null)", (token, "x" * 2001)) == "COMMENT_TOO_LONG"
    review = submit(db_002, token, doc="d3", comment="ngắn")
    longer = submit(db_002, token, doc="d3", comment="y" * 3000, review_id=review["id"])  # old reviews were allowed 4000 and may be edited
    assert len(longer["comment"]) == 3000
    assert len(submit(db_002, token, doc="d3", comment="z" * 5000, review_id=review["id"])["comment"]) == 4000  # as before, cut at 4000
    long_name = "N" * 41
    assert len(submit(db_002, new_token(), doc="d4", nick=long_name)["nickname"]) == 40  # as before, cut at 40


def test_the_public_key_can_read_reviews_and_flags_and_nothing_more(db_002):
    row = submit(db_002, new_token())
    db_002.denied("insert into public.reviews (doc_id, rating, user_hash) values ('x', 5, 'forged')")
    db_002.denied("update public.reviews set rating = 1")
    db_002.denied("delete from public.reviews")
    db_002.denied("insert into public.reviewers (nickname_key, nickname, user_hash) values ('k', 'K', 'h')")
    for table in ("review_reports", "blocked_identities"):
        db_002.denied(f"select * from public.{table}")
        db_002.denied(f"insert into public.{table} default values")
    db_002.denied("insert into public.service_flags (key, value) values ('reviews_enabled', 'false')")
    db_002.denied("update public.service_flags set value = 'false'")
    db_002.denied("delete from public.service_flags")
    for call in ("select public.hash_token('x')", "select public.flag_on('reviews_enabled')", "select public.flag_int('x', 1)",
                 "select public.flag_text('x', 'y')"):
        db_002.denied(call)
    assert db_002.run("select count(*) as n from public.reviews", role="anon") == [{"n": 1}] and row["id"]


def test_running_the_migration_twice_changes_nothing_and_keeps_tuned_values(db_002):
    db_002.flag("auto_hide_threshold", "7")
    before = db_002.one("select count(*) from pg_proc where pronamespace = 'public'::regnamespace")
    db_002.apply("002_review_moderation.sql")
    assert db_002.one("select value from public.service_flags where key = 'auto_hide_threshold'") == "7"
    assert db_002.one("select count(*) from pg_proc where pronamespace = 'public'::regnamespace") == before


def test_002_also_upgrades_a_project_that_already_holds_reviews(server):
    """The owner's real situation: 1.0.0 reviews exist before the migration runs."""
    db = _new_db(server)
    tokens = [new_token() for _ in range(3)]
    for index, token in enumerate(tokens):
        submit(db, token, doc="doc-1", nick=f"Người {index}", rating=3 + index % 3, comment="x" * (index * 1000))
    db.apply("002_review_moderation.sql")
    assert len(visible(db)) == 3
    assert db.one("select count(*) from public.reviews where not is_hidden") == 3
    assert submit(db, tokens[0], nick="Người 0", comment="đã sửa", review_id=visible(db)[-1]["id"])["comment"] == "đã sửa"


# =====================================================================================================================
# E-07 / E-09: error reports (003)
# =====================================================================================================================

CONTEXT = er.ReportContext("1.1.0", "0123456789ab", "release", "Windows 11 (10.0.26200) AMD64", "vi", "broadsheet", "a" * 64, 1, "1k-10k")


def make_payload(tag: str = "a", *, install: str = "a" * 64, version: str = "1.1.0", source: str = "crash", note: str = "", log: str = "") -> dict:
    context = er.ReportContext(version, "0123456789ab", "release", "Windows 11", "vi", "broadsheet", install, 1, "1k-10k")
    if source == "manual":
        report = er.build_synthetic("ManualReport", "m", context=context, source="manual", user_note=note or "ghi chú", log_tail=log)
    elif source == "worker":
        report = er.build_synthetic("BrokenExecutor", "died", context=context, source="worker", process_kind="classify_worker", feature_area="classification")
    else:
        frames = (er.StackFrame("smartdoc/app.py", "main", 10), er.StackFrame("smartdoc/application/import_queue.py", f"fn_{tag}", 20))
        stable, exact = er.fingerprints(f"Error{tag}", frames)
        report = er.ErrorReport(
            report_id=er.new_report_id(), occurred_at=er.occurred_now(), source="crash", process_kind="gui", feature_area="import",
            exception_type=f"Error{tag}", stack_frames=frames, message_scrubbed="msg <PATH>", fingerprint_stable=stable,
            fingerprint_exact=exact, context=context, user_note=note, log_tail=log,
        )
    payload = report.to_payload()
    assert er.validate_payload(payload) == []  # a payload the app itself would send
    return payload


def send(db: Db, payload: dict, *, role: str = "anon") -> str:
    return db.one("select public.submit_error_report(%s::jsonb)", (json.dumps(payload, ensure_ascii=False),), role=role)


def refused(db: Db, payload, *, role: str = "anon") -> str:
    return db.message("select public.submit_error_report(%s::jsonb)", (json.dumps(payload, ensure_ascii=False),), role=role)


def test_a_report_the_app_built_is_accepted_and_stored_with_its_group(db_003):
    payload = make_payload("x", note="ghi chú", log="2026-09-19 10:00:00,000 INFO [t] smartdoc.x: m")
    assert send(db_003, payload) == payload["report_id"]
    row = db_003.run("select * from public.error_reports")[0]
    assert (str(row["report_id"]), row["app_version"], row["exception_type"], row["install_hash"]) == (
        payload["report_id"], "1.1.0", "Errorx", "a" * 64)
    assert row["stack_frames"] == payload["stack_frames"] and row["user_note"] == "ghi chú" and row["log_tail"].startswith("2026-09-19")
    group = db_003.run("select * from public.error_groups")[0]
    assert (group["fingerprint_stable"], group["occurrence_count"], group["distinct_installs"], group["versions_affected"]) == (
        payload["fingerprint_stable"], 1, 1, ["1.1.0"])
    assert group["top_frame"] == "smartdoc/application/import_queue.py:fn_x" and group["status"] == "new" and group["source"] == "crash"


@pytest.mark.parametrize("source", ["crash", "worker", "manual"])
def test_every_kind_of_report_the_app_can_make_is_accepted(db_003, source):
    payload = make_payload(source=source)
    assert send(db_003, payload) == payload["report_id"]
    assert db_003.one("select source from public.error_reports") == source


def test_a_resend_of_the_same_report_is_recognised_and_counts_once(db_003):
    payload = make_payload()
    send(db_003, payload)
    assert send(db_003, payload) == payload["report_id"]
    assert db_003.one("select count(*) from public.error_reports") == 1
    assert db_003.one("select occurrence_count from public.error_groups") == 1


def test_only_five_detailed_samples_a_day_are_kept_per_bug_the_rest_are_only_counted(db_003):
    for index in range(7):
        payload = make_payload("same", install=f"{index:064x}")
        payload["report_id"] = er.new_report_id()
        send(db_003, payload)
    assert db_003.one("select count(*) from public.error_reports") == 5
    group = db_003.run("select occurrence_count, distinct_installs from public.error_groups")[0]
    assert group == {"occurrence_count": 7, "distinct_installs": 7}


def test_the_same_installation_counts_once_however_many_times_it_reports(db_003):
    for _ in range(3):
        payload = make_payload("same")
        payload["report_id"] = er.new_report_id()
        send(db_003, payload)
    assert db_003.run("select occurrence_count, distinct_installs from public.error_groups") == [{"occurrence_count": 3, "distinct_installs": 1}]


def test_one_installation_is_limited_per_day(db_003):
    for index in range(20):
        send(db_003, make_payload(f"t{index}"))
    assert refused(db_003, make_payload("t21")) == "RATE_LIMITED"
    assert send(db_003, make_payload("t22", install="b" * 64))  # somebody else is not affected


def test_a_flood_from_everybody_trips_the_switch_and_the_app_backs_off(db_003):
    """ERR-A8: over the global hourly limit the server switches error reports off by itself."""
    db_003.flag("error_max_global_per_hour", "3")
    for index in range(3):
        send(db_003, make_payload(f"g{index}", install=f"{index:064x}"))
    assert db_003.one("select value from public.service_flags where key = 'error_reports_enabled'") == "true"
    tripping = make_payload("g3", install=f"{3:064x}")
    assert send(db_003, tripping) == tripping["report_id"]  # accepted, so the flip is kept, but not stored
    assert db_003.one("select value from public.service_flags where key = 'error_reports_enabled'") == "false"
    assert db_003.one("select count(*) from public.error_reports") == 3
    assert refused(db_003, make_payload("g4")) == "REPORTS_DISABLED"


def test_a_table_that_would_outgrow_the_plan_switches_receiving_off(db_003):
    db_003.flag("error_max_rows", "2")
    for index in range(2):
        send(db_003, make_payload(f"r{index}", install=f"{index:064x}"))
    send(db_003, make_payload("r2", install=f"{2:064x}"))
    assert db_003.one("select count(*) from public.error_reports") == 2
    assert db_003.one("select value from public.service_flags where key = 'error_reports_enabled'") == "false"


def test_the_owner_can_switch_reports_off_and_the_app_can_see_it(db_003):
    db_003.flag("error_reports_enabled", "false")
    assert refused(db_003, make_payload()) == "REPORTS_DISABLED"
    assert db_003.one("select value from public.service_flags where key = 'error_reports_enabled'", role="anon") == "false"


def test_developer_builds_are_refused_unless_the_owner_allows_them(db_003):
    payload = make_payload()
    payload["channel"] = "dev"
    payload["build_id"] = "dev"
    assert refused(db_003, payload) == "INVALID_REPORT"
    db_003.flag("accept_dev_reports", "true")
    assert send(db_003, payload) == payload["report_id"]


def test_a_fixed_bug_that_returns_in_the_release_meant_to_fix_it_is_reopened(db_003):
    first = make_payload("bug", version="1.0.9")
    send(db_003, first)
    db_003.run("update public.error_groups set status = 'fixed', fixed_in_version = '1.1.0'")
    before = make_payload("bug", version="1.0.9", install="b" * 64)
    send(db_003, before)
    assert db_003.one("select status from public.error_groups") == "fixed"  # an old version still has the bug: expected
    after = make_payload("bug", version="1.1.0", install="c" * 64)
    send(db_003, after)
    assert db_003.one("select status from public.error_groups") == "reopened"
    assert db_003.one("select versions_affected from public.error_groups") == ["1.0.9", "1.1.0"]


# --- parity with the app's own validation -----------------------------------------------------------------------------------------

INVALID_FIELDS = [
    ("report_id", "not-a-uuid"), ("app_version", "one.two.three"), ("build_id", "XYZ"), ("channel", "beta"), ("locale", "Vietnamese"),
    ("theme_id", "Has Space"), ("feature_area", "everything"), ("process_kind", "thread"), ("source", "telepathy"),
    ("exception_type", "has space"), ("message_scrubbed", "x" * 501), ("fingerprint_stable", "abc"), ("fingerprint_exact", "z" * 64),
    ("install_hash", "g" * 64), ("occurred_at", "yesterday"), ("occurred_at", "2026-13-45T25:61Z"), ("occurred_at", "2001-01-01T00:00Z"),
    ("occurred_at", "2999-01-01T00:00Z"), ("consent_version", "1"), ("consent_version", -1), ("library_size_bucket", "huge"),
    ("user_note", "n" * 1001), ("user_note", 5), ("log_tail", "l" * 10_001), ("stack_frames", "none"),
    ("stack_frames", [{"path": "a", "function": "f"}]), ("stack_frames", [{"path": "a", "function": "f", "line": -1}]),
    ("stack_frames", [{"path": "", "function": "f", "line": 1}]), ("stack_frames", [{"path": "a", "function": "f", "line": 1, "x": 1}]),
    ("stack_frames", ["not an object"]), ("stack_frames", [{"path": "a", "function": "f", "line": 1}] * 51), ("os", ""), ("os", "o" * 101),
]


@pytest.mark.parametrize(("field", "value"), INVALID_FIELDS)
def test_the_server_refuses_what_the_apps_own_check_refuses(db_003, field, value):
    payload = make_payload()
    payload[field] = value
    assert er.validate_payload(payload) != [] or field in ("occurred_at",)  # the app would never send it
    assert refused(db_003, payload) == "INVALID_REPORT"
    assert db_003.one("select count(*) from public.error_reports") == 0


@pytest.mark.parametrize("field", ["report_id", "fingerprint_stable", "stack_frames", "install_hash", "message_scrubbed", "source", "occurred_at"])
def test_a_missing_field_is_refused(db_003, field):
    payload = make_payload()
    del payload[field]
    assert refused(db_003, payload) == "INVALID_REPORT"


def test_the_wrong_kind_of_body_is_refused(db_003):
    for body in ("[]", '"text"', "5", "null"):
        assert db_003.message("select public.submit_error_report(%s::jsonb)", (body,), role="anon") == "INVALID_REPORT"
    assert refused(db_003, {}) == "UNSUPPORTED_SCHEMA"  # an object with no format marker
    assert refused(db_003, {**make_payload(), "schema": 2}) == "UNSUPPORTED_SCHEMA"


def test_an_oversize_report_is_refused_and_a_new_field_from_a_newer_app_is_ignored(db_003):
    payload = make_payload()
    payload["stack_frames"] = [{"path": "p" * 200, "function": "f" * 100, "line": 1}] * 50
    payload["log_tail"], payload["user_note"], payload["message_scrubbed"] = "l" * 10_000, "n" * 1000, "m" * 500
    assert refused(db_003, payload) == "PAYLOAD_TOO_LARGE"
    newer = make_payload()
    newer["something_new"] = "a field this server has never heard of"
    assert send(db_003, newer) == newer["report_id"]
    assert db_003.one("select count(*) from public.error_reports") == 1


def test_everything_the_app_may_send_at_its_own_limits_is_accepted(db_003):
    """The limits agree: a report the app trims to 16 KiB is never refused as too large."""
    frames = tuple(er.StackFrame("p" * 190, "f" * 90 + str(i), i) for i in range(40))
    stable, exact = er.fingerprints("E", frames)
    report = er.fit_to_limit(er.ErrorReport(
        report_id=er.new_report_id(), occurred_at=er.occurred_now(), source="crash", process_kind="gui", feature_area="other",
        exception_type="E", stack_frames=frames, message_scrubbed="m" * 500, fingerprint_stable=stable, fingerprint_exact=exact,
        context=CONTEXT, user_note="n" * 1000, log_tail="l" * 8000,
    ))
    payload = report.to_payload()
    assert er.payload_size(payload) <= er.MAX_PAYLOAD_BYTES
    assert send(db_003, payload) == payload["report_id"]


# --- who can see what: ERR-A7, ERR-A13 -----------------------------------------------------------------------------------------------

ERROR_OBJECTS = ("error_reports", "error_groups", "error_group_installs", "error_install_daily", "error_hourly",
                 "v_triage_groups", "v_triage_samples")


def test_the_public_key_can_only_submit_a_report_and_read_the_switches(db_003):
    send(db_003, make_payload())
    for name in ERROR_OBJECTS:
        db_003.denied(f"select * from public.{name}")
    db_003.denied("insert into public.error_reports (report_id) values (gen_random_uuid())")
    db_003.denied("update public.error_groups set status = 'fixed'")
    db_003.denied("delete from public.error_reports")
    db_003.denied("update public.service_flags set value = 'true' where key = 'error_reports_enabled'")
    for call in ("select public.triage_set_status('%s', 'triaged')" % ("a" * 64), "select public.purge_error_reports()",
                 "select public.error_report_problem('{}'::jsonb)", "select public.version_ge('1.0.0', '1.0.0')"):
        db_003.denied(call)
    assert db_003.run("select key from public.service_flags where key = 'error_reports_enabled'", role="anon")


def test_the_triage_reader_sees_two_filtered_views_and_nothing_else(db_003):
    send(db_003, make_payload("v", note="tự do <b>không tin</b>", log="2026-09-19 10:00:00,000 INFO [t] smartdoc.x: m"))
    send(db_003, make_payload(source="manual", note="một người viết tự do"))
    groups = db_003.run("select * from public.v_triage_groups", role="triage_reader")
    samples = db_003.run("select * from public.v_triage_samples", role="triage_reader")
    assert [g["exception_type"] for g in groups] == ["Errorv"] and [s["exception_type"] for s in samples] == ["Errorv"]  # not the manual one
    for column in ("user_note", "log_tail", "install_hash"):
        assert column not in samples[0] and column not in groups[0]
        assert isinstance(db_003.error(f"select {column} from public.v_triage_samples", role="triage_reader"), pgerrors.UndefinedColumn)
    for name in ("error_reports", "error_groups", "error_group_installs", "error_install_daily", "error_hourly", "service_flags", "reviews"):
        db_003.denied(f"select * from public.{name}", role="triage_reader")
    db_003.denied("select user_note from public.error_reports", role="triage_reader")
    db_003.denied("update public.error_groups set status = 'fixed'", role="triage_reader")
    db_003.denied("select public.submit_error_report('{}'::jsonb)", role="triage_reader")
    db_003.denied("select public.triage_set_status('%s', 'triaged')" % ("a" * 64), role="triage_reader")
    db_003.denied("select public.purge_error_reports()", role="triage_reader")


def test_the_triage_writer_can_only_mark_a_bug_as_looked_at(db_003):
    payload = make_payload("w")
    send(db_003, payload)
    fp = payload["fingerprint_stable"]
    db_003.run("select public.triage_set_status(%s, 'triaged', 'Có vẻ do thiếu kiểm tra None', 'https://example.org/issues/1')", (fp,), role="triage_writer")
    group = db_003.run("select status, notes, issue_url from public.error_groups")[0]
    assert group == {"status": "triaged", "notes": "Có vẻ do thiếu kiểm tra None", "issue_url": "https://example.org/issues/1"}
    db_003.run("select public.triage_set_status(%s, 'fix_proposed')", (fp,), role="triage_writer")
    assert db_003.one("select status from public.error_groups") == "fix_proposed"

    def refuses(sql, params, code):
        assert db_003.message(sql, params, role="triage_writer") == code

    refuses("select public.triage_set_status(%s, 'fixed')", (fp,), "STATUS_NOT_ALLOWED")
    refuses("select public.triage_set_status(%s, 'wontfix')", (fp,), "STATUS_NOT_ALLOWED")
    refuses("select public.triage_set_status(%s, 'triaged', '', null, '1.1.1')", (fp,), "STATUS_NOT_ALLOWED")
    refuses("select public.triage_set_status(%s, 'triaged', '', 'http://insecure.example.org')", (fp,), "INVALID_URL")
    refuses("select public.triage_set_status('nope', 'triaged')", (), "INVALID_FINGERPRINT")
    refuses("select public.triage_set_status(%s, 'triaged')", ("f" * 64,), "GROUP_NOT_FOUND_OR_CLOSED")
    db_003.run("update public.error_groups set status = 'fixed', fixed_in_version = '1.1.0'")
    refuses("select public.triage_set_status(%s, 'triaged')", (fp,), "GROUP_NOT_FOUND_OR_CLOSED")  # a closed bug is left alone
    for name in ("v_triage_groups", "v_triage_samples", "error_reports", "error_groups", "service_flags"):
        db_003.denied(f"select * from public.{name}", role="triage_writer")
    db_003.denied("select public.submit_error_report('{}'::jsonb)", role="triage_writer")
    db_003.denied("update public.error_groups set status = 'wontfix'", role="triage_writer")


def test_the_views_have_no_free_text_the_owner_reserved(db_003):
    columns = db_003.run(
        "select table_name, column_name from information_schema.columns where table_schema = 'public' and table_name in ('v_triage_groups','v_triage_samples')"
    )
    names = {c["column_name"] for c in columns}
    assert not {"user_note", "log_tail", "install_hash", "os", "locale"} & names and "stack_frames" in names


def test_the_owner_can_read_everything_including_the_notes(db_003):
    send(db_003, make_payload(note="ghi chú của người dùng", log="2026-09-19 10:00:00,000 INFO [t] smartdoc.x: m"))
    row = db_003.run("select user_note, log_tail from public.error_reports")[0]
    assert row["user_note"] == "ghi chú của người dùng" and row["log_tail"].startswith("2026")


def test_old_samples_are_purged_but_the_group_counts_stay(db_003):
    payload = make_payload("old")
    send(db_003, payload)
    db_003.run("update public.error_reports set received_at = now() - interval '91 days'")
    fresh = make_payload("new", install="b" * 64)
    send(db_003, fresh)
    assert db_003.one("select public.purge_error_reports()") == 1
    assert [str(r["report_id"]) for r in db_003.run("select report_id from public.error_reports")] == [fresh["report_id"]]
    assert db_003.one("select count(*) from public.error_groups") == 2  # the aggregate outlives the detail


def test_deleting_one_report_by_its_id_is_a_plain_delete(db_003):
    """The runbook's answer to "please delete my report": by the id the user was shown."""
    keep, drop = make_payload("keep"), make_payload("drop")
    send(db_003, keep)
    send(db_003, drop)
    db_003.run("delete from public.error_reports where report_id = %s", (drop["report_id"],))
    assert [str(r["report_id"]) for r in db_003.run("select report_id from public.error_reports")] == [keep["report_id"]]


def test_running_003_twice_changes_nothing_and_keeps_tuned_values(db_003):
    db_003.flag("error_max_per_install_per_day", "7")
    send(db_003, make_payload())
    db_003.apply("003_error_reports.sql")
    assert db_003.one("select value from public.service_flags where key = 'error_max_per_install_per_day'") == "7"
    assert db_003.one("select count(*) from public.error_reports") == 1


def test_the_two_migrations_can_be_run_in_one_go_in_order(server):
    db = _new_db(server)
    db.run(_sql("002_review_moderation.sql") + "\n" + _sql("003_error_reports.sql"))
    assert send(db, make_payload())


def test_a_json_body_is_not_altered_on_its_way_through(db_003):
    payload = make_payload(note="Đắc nhân tâm — “ngoặc kép” 🐱")
    send(db_003, payload)
    assert db_003.one("select user_note from public.error_reports") == "Đắc nhân tâm — “ngoặc kép” 🐱"
    assert copy.deepcopy(payload) == payload
