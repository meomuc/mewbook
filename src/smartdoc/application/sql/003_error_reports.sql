-- SPDX-License-Identifier: AGPL-3.0-or-later
-- MewBook 1.1.0 -- Anonymous error reports: storage, the one door, limits, and the narrow roles for the triage agent (E-07).
--
-- Run ONCE in the Supabase SQL Editor, AFTER 002_review_moderation.sql (it uses the service_flags table and the flag_*
-- helpers made there). Safe to re-run: every statement is idempotent, and re-running never overwrites a value you tuned.
-- MewBook 1.0.0 has no error reports and is not affected.
--
-- The app sends a report only after the user said yes (docs/handoff/09_ERROR_REPORTING_SPEC.md). The report is scrubbed on
-- the user's computer; this script keeps it only as long as needed and gives nobody but you access to the raw rows.
--
-- Who can do what
--   anon (the public key inside every app)   call submit_error_report(...) and read service_flags. Nothing else: no select,
--                                             insert, update or delete on any error table or view.
--   triage_reader (the daily agent, read)     select on two FILTERED views, v_triage_groups and v_triage_samples, which have no
--                                             user_note and no log_tail. Nothing else.
--   triage_writer (the daily agent, write)    call triage_set_status(...): mark a group "triaged" or "fix_proposed", with a note and
--                                             an issue link. Nothing else.
--   you (the project owner, SQL editor)       everything, including user_note and log_tail (docs/ERROR_OPS_RUNBOOK.md).
--
-- submit_error_report(p_report jsonb) returns the report id, or raises one of:
--   REPORTS_DISABLED       error_reports_enabled is off (you switched it off, or a limit below tripped it)
--   RATE_LIMITED           this installation sent more than error_max_per_install_per_day reports today
--   INVALID_REPORT         a field is missing, too long, of the wrong type or not an allowed value (detail says which)
--   PAYLOAD_TOO_LARGE      the whole report is over 24 KiB (the app trims to 16 KiB; jsonb text is a little longer)
--   UNSUPPORTED_SCHEMA     a report format this server does not know
--
-- Limits (service_flags; change with an UPDATE, no release needed)
--   error_max_per_install_per_day   20     per installation (a salted hash the app makes up; not the review identity)
--   error_max_global_per_hour       300    over it, error_reports_enabled is switched OFF automatically and the app backs off
--   error_max_rows                  50000  over it, the same: stop receiving before the free plan's quota is hit
--   error_samples_per_group_per_day 5      only 5 detailed samples per bug per day are kept; further ones just count
--   error_retention_days            90     purge_error_reports() deletes detailed samples older than this
--   accept_dev_reports              false  reports from developer builds are refused
--
-- The counter table error_hourly and the flag flip happen even when a report is not stored (a raised exception would undo
-- them), so a call that trips a limit succeeds and every later call is refused with REPORTS_DISABLED.

-- ---------------------------------------------------------------------------------------------------------------------
-- 1. Switches
-- ---------------------------------------------------------------------------------------------------------------------

insert into public.service_flags (key, value) values
  ('error_reports_enabled',           'true'),
  ('accept_dev_reports',              'false'),
  ('error_max_per_install_per_day',   '20'),
  ('error_max_global_per_hour',       '300'),
  ('error_max_rows',                  '50000'),
  ('error_samples_per_group_per_day', '5'),
  ('error_retention_days',            '90')
on conflict (key) do nothing;

-- ---------------------------------------------------------------------------------------------------------------------
-- 2. Tables (nobody but you can read or write them)
-- ---------------------------------------------------------------------------------------------------------------------

create table if not exists public.error_groups (
  fingerprint_stable text primary key,              -- sha256 of the exception type + the 5 innermost frames, no line numbers
  exception_type     text not null,
  feature_area       text not null,
  process_kind       text not null,
  source             text not null check (source in ('crash', 'worker', 'manual')),
  first_seen         timestamptz not null default now(),
  last_seen          timestamptz not null default now(),
  occurrence_count   bigint not null default 0,
  distinct_installs  int not null default 0,
  versions_affected  text[] not null default '{}',
  top_frame          text,                           -- "smartdoc/application/x.py:function", for a human
  status             text not null default 'new' check (status in ('new', 'triaged', 'fix_proposed', 'fixed', 'wontfix', 'reopened')),
  issue_url          text,
  fixed_in_version   text,
  notes              text not null default ''
);

create table if not exists public.error_reports (
  report_id           uuid primary key,              -- made on the user's computer: a resend is recognised and ignored
  group_fingerprint   text not null references public.error_groups (fingerprint_stable) on delete cascade,
  received_at         timestamptz not null default now(),
  fingerprint_exact   text not null,
  app_version         text not null,
  build_id            text not null,
  channel             text not null,
  os                  text not null,
  locale              text not null,
  theme_id            text not null,
  feature_area        text not null,
  process_kind        text not null,
  source              text not null,
  exception_type      text not null,
  stack_frames        jsonb not null,
  message_scrubbed    text not null,                  -- untrusted text, however well it was scrubbed
  library_size_bucket text,
  install_hash        text not null,
  consent_version     int not null,
  occurred_at         timestamptz not null,
  user_note           text,                           -- only you read these two (see the triage views)
  log_tail            text
);
create index if not exists error_reports_group_idx    on public.error_reports (group_fingerprint, received_at);
create index if not exists error_reports_received_idx on public.error_reports (received_at);

create table if not exists public.error_group_installs (   -- counts distinct installations per bug
  fingerprint_stable text not null,
  install_hash       text not null,
  first_seen         timestamptz not null default now(),
  primary key (fingerprint_stable, install_hash)
);
create table if not exists public.error_install_daily (
  install_hash text not null,
  day          date not null,
  n            int  not null default 0,
  primary key (install_hash, day)
);
create table if not exists public.error_hourly (
  hour timestamptz primary key,
  n    int not null default 0
);

alter table public.error_groups        enable row level security;
alter table public.error_reports       enable row level security;
alter table public.error_group_installs enable row level security;
alter table public.error_install_daily enable row level security;
alter table public.error_hourly        enable row level security;
revoke all on public.error_groups, public.error_reports, public.error_group_installs,
              public.error_install_daily, public.error_hourly from anon, authenticated;

-- ---------------------------------------------------------------------------------------------------------------------
-- 3. Validation: the same rules the app checks before it sends (domain/error_report.py validate_payload)
-- ---------------------------------------------------------------------------------------------------------------------

create or replace function public.error_report_problem(p jsonb)
returns text                      -- null when the report is acceptable, else "CODE: what is wrong"
language plpgsql
stable
set search_path = public
as $$
declare
  f       jsonb;
  k       text;
  n       int;
  v_when  timestamptz;
begin
  if p is null or jsonb_typeof(p) <> 'object' then
    return 'INVALID_REPORT: not an object';
  end if;
  if octet_length(p::text) > 24576 then
    return 'PAYLOAD_TOO_LARGE: over 24 KiB';
  end if;
  if p -> 'schema' is distinct from '1'::jsonb then
    return 'UNSUPPORTED_SCHEMA: schema';
  end if;

  -- text fields: type, length, shape
  foreach k in array array['report_id', 'app_version', 'build_id', 'channel', 'os', 'locale', 'theme_id', 'feature_area',
                           'process_kind', 'source', 'exception_type', 'message_scrubbed', 'fingerprint_stable',
                           'fingerprint_exact', 'install_hash', 'occurred_at'] loop
    if jsonb_typeof(p -> k) is distinct from 'string' then
      return 'INVALID_REPORT: ' || k;
    end if;
  end loop;

  if p ->> 'report_id' !~ '^[0-9a-f]{8}-[0-9a-f]{4}-4[0-9a-f]{3}-[89ab][0-9a-f]{3}-[0-9a-f]{12}$' then return 'INVALID_REPORT: report_id'; end if;
  if p ->> 'app_version' !~ '^\d{1,3}\.\d{1,3}\.\d{1,3}(-[0-9A-Za-z.-]{1,20})?$' then return 'INVALID_REPORT: app_version'; end if;
  if p ->> 'build_id' !~ '^([0-9a-f]{7,40}(-dirty)?|dev)$' then return 'INVALID_REPORT: build_id'; end if;
  if p ->> 'channel' not in ('release', 'dev') then return 'INVALID_REPORT: channel'; end if;
  if char_length(p ->> 'os') not between 1 and 100 then return 'INVALID_REPORT: os'; end if;
  if p ->> 'locale' !~ '^[a-z]{2,3}(-[A-Za-z]{2,4})?$' then return 'INVALID_REPORT: locale'; end if;
  if p ->> 'theme_id' !~ '^[a-z0-9_]{1,30}$' then return 'INVALID_REPORT: theme_id'; end if;
  if p ->> 'feature_area' not in ('import', 'classification', 'reader', 'cover_search', 'ai_summary', 'review', 'device', 'ui', 'startup', 'other') then
    return 'INVALID_REPORT: feature_area';
  end if;
  if p ->> 'process_kind' not in ('gui', 'classify_worker') then return 'INVALID_REPORT: process_kind'; end if;
  if p ->> 'source' not in ('crash', 'manual', 'worker') then return 'INVALID_REPORT: source'; end if;
  if p ->> 'exception_type' !~ '^[A-Za-z_][A-Za-z0-9_.]{0,99}$' then return 'INVALID_REPORT: exception_type'; end if;
  if char_length(p ->> 'message_scrubbed') > 500 then return 'INVALID_REPORT: message_scrubbed'; end if;
  if p ->> 'fingerprint_stable' !~ '^[0-9a-f]{64}$' then return 'INVALID_REPORT: fingerprint_stable'; end if;
  if p ->> 'fingerprint_exact' !~ '^[0-9a-f]{64}$' then return 'INVALID_REPORT: fingerprint_exact'; end if;
  if p ->> 'install_hash' !~ '^[0-9a-f]{64}$' then return 'INVALID_REPORT: install_hash'; end if;
  if p ->> 'occurred_at' !~ '^\d{4}-\d\d-\d\dT\d\d:\d\dZ$' then return 'INVALID_REPORT: occurred_at'; end if;
  begin
    v_when := (p ->> 'occurred_at')::timestamptz;
  exception when others then
    return 'INVALID_REPORT: occurred_at';
  end;
  if v_when > now() + interval '1 day' or v_when < now() - interval '90 days' then
    return 'INVALID_REPORT: occurred_at';
  end if;

  if jsonb_typeof(p -> 'consent_version') is distinct from 'number' or (p ->> 'consent_version') !~ '^[0-9]{1,4}$' then
    return 'INVALID_REPORT: consent_version';
  end if;
  if p ? 'library_size_bucket'
     and (jsonb_typeof(p -> 'library_size_bucket') is distinct from 'string'
          or (p ->> 'library_size_bucket') <> all (array['<1k', '1k-10k', '>10k'])) then
    return 'INVALID_REPORT: library_size_bucket';
  end if;
  if p ? 'user_note' and (jsonb_typeof(p -> 'user_note') <> 'string' or char_length(p ->> 'user_note') > 1000) then
    return 'INVALID_REPORT: user_note';
  end if;
  if p ? 'log_tail' and (jsonb_typeof(p -> 'log_tail') <> 'string' or char_length(p ->> 'log_tail') > 10000) then
    return 'INVALID_REPORT: log_tail';
  end if;

  if jsonb_typeof(p -> 'stack_frames') is distinct from 'array' or jsonb_array_length(p -> 'stack_frames') > 50 then
    return 'INVALID_REPORT: stack_frames';
  end if;
  for f in select value from jsonb_array_elements(p -> 'stack_frames') loop
    select count(*) into n from jsonb_object_keys(case when jsonb_typeof(f) = 'object' then f else '{}'::jsonb end);
    if jsonb_typeof(f) <> 'object' or n <> 3 or not (f ? 'path' and f ? 'function' and f ? 'line')
       or jsonb_typeof(f -> 'path') is distinct from 'string' or char_length(f ->> 'path') not between 1 and 200
       or jsonb_typeof(f -> 'function') is distinct from 'string' or char_length(f ->> 'function') not between 1 and 100
       or jsonb_typeof(f -> 'line') is distinct from 'number' or (f ->> 'line') !~ '^[0-9]{1,7}$' then
      return 'INVALID_REPORT: stack_frames';
    end if;
  end loop;

  return null;
end;
$$;

-- a >= b for "major.minor.patch" versions (any pre-release suffix is ignored)
create or replace function public.version_ge(a text, b text)
returns boolean
language sql
immutable
set search_path = public
as $$
  select case
    when a ~ '^\d+\.\d+\.\d+' and b ~ '^\d+\.\d+\.\d+' then
      string_to_array(substring(a from '^\d+\.\d+\.\d+'), '.')::int[] >= string_to_array(substring(b from '^\d+\.\d+\.\d+'), '.')::int[]
    else false
  end
$$;

-- ---------------------------------------------------------------------------------------------------------------------
-- 4. The one door
-- ---------------------------------------------------------------------------------------------------------------------

create or replace function public.submit_error_report(p_report jsonb)
returns text
language plpgsql
security definer
set search_path = public
as $$
declare
  v_problem text;
  v_code    text;
  v_id      uuid;
  v_fp      text;
  v_install text;
  v_version text;
  v_frames  jsonb;
  v_top     text;
  v_n       int;
  v_max     int;
begin
  if not public.flag_on('error_reports_enabled') then
    raise exception 'REPORTS_DISABLED';
  end if;

  v_problem := public.error_report_problem(p_report);
  if v_problem is not null then
    v_code := split_part(v_problem, ':', 1);
    if v_code in ('PAYLOAD_TOO_LARGE', 'UNSUPPORTED_SCHEMA') then
      raise exception '%', v_code using detail = v_problem;
    end if;
    raise exception 'INVALID_REPORT' using detail = v_problem;
  end if;
  if p_report ->> 'channel' <> 'release' and not public.flag_on('accept_dev_reports', false) then
    raise exception 'INVALID_REPORT' using detail = 'channel: developer builds do not report';
  end if;

  v_id := (p_report ->> 'report_id')::uuid;
  if exists (select 1 from public.error_reports where report_id = v_id) then
    return v_id::text;                                        -- a resend of a report we already have
  end if;

  v_fp      := p_report ->> 'fingerprint_stable';
  v_install := p_report ->> 'install_hash';
  v_version := p_report ->> 'app_version';

  -- per installation, per day
  insert into public.error_install_daily as d (install_hash, day, n)
  values (v_install, (now() at time zone 'utc')::date, 1)
  on conflict (install_hash, day) do update set n = d.n + 1
  returning d.n into v_n;
  if v_n > public.flag_int('error_max_per_install_per_day', 20) then
    raise exception 'RATE_LIMITED';
  end if;

  -- everybody, per hour: over the limit the switch goes off (and this call still succeeds, so the flip is kept)
  insert into public.error_hourly as h (hour, n)
  values (date_trunc('hour', now()), 1)
  on conflict (hour) do update set n = h.n + 1
  returning h.n into v_n;
  if v_n > public.flag_int('error_max_global_per_hour', 300) then
    update public.service_flags set value = 'false', updated_at = now() where key = 'error_reports_enabled';
    return v_id::text;
  end if;

  -- the table must not outgrow the plan
  v_max := public.flag_int('error_max_rows', 50000);
  select count(*) into v_n from (select 1 from public.error_reports limit v_max) as capped;
  if v_n >= v_max then
    update public.service_flags set value = 'false', updated_at = now() where key = 'error_reports_enabled';
    return v_id::text;
  end if;

  v_frames := p_report -> 'stack_frames';
  if jsonb_array_length(v_frames) > 0 then
    v_top := left((v_frames -> -1 ->> 'path') || ':' || (v_frames -> -1 ->> 'function'), 300);
  end if;

  -- the group: one row per bug, however many reports
  insert into public.error_groups as g
    (fingerprint_stable, exception_type, feature_area, process_kind, source, occurrence_count, versions_affected, top_frame)
  values
    (v_fp, p_report ->> 'exception_type', p_report ->> 'feature_area', p_report ->> 'process_kind', p_report ->> 'source',
     1, array[v_version], v_top)
  on conflict (fingerprint_stable) do update
     set last_seen = now(),
         occurrence_count = g.occurrence_count + 1,
         versions_affected = (
           select (array_agg(distinct v order by v))[1:30] from unnest(g.versions_affected || v_version) as u(v)),
         -- a fixed bug that shows up again in the release that was meant to fix it (or a later one) is open again
         status = case
                    when g.status = 'fixed' and g.fixed_in_version is not null and public.version_ge(v_version, g.fixed_in_version)
                      then 'reopened'
                    else g.status
                  end;

  insert into public.error_group_installs (fingerprint_stable, install_hash) values (v_fp, v_install)
  on conflict do nothing;
  if found then
    update public.error_groups set distinct_installs = distinct_installs + 1 where fingerprint_stable = v_fp;
  end if;

  -- detailed samples: at most a few per bug per day, the rest only counted
  select count(*) into v_n from public.error_reports where group_fingerprint = v_fp and received_at > now() - interval '1 day';
  if v_n < public.flag_int('error_samples_per_group_per_day', 5) then
    insert into public.error_reports
      (report_id, group_fingerprint, fingerprint_exact, app_version, build_id, channel, os, locale, theme_id, feature_area,
       process_kind, source, exception_type, stack_frames, message_scrubbed, library_size_bucket, install_hash,
       consent_version, occurred_at, user_note, log_tail)
    values
      (v_id, v_fp, p_report ->> 'fingerprint_exact', v_version, p_report ->> 'build_id', p_report ->> 'channel',
       p_report ->> 'os', p_report ->> 'locale', p_report ->> 'theme_id', p_report ->> 'feature_area',
       p_report ->> 'process_kind', p_report ->> 'source', p_report ->> 'exception_type', v_frames,
       p_report ->> 'message_scrubbed', p_report ->> 'library_size_bucket', v_install,
       (p_report ->> 'consent_version')::int, (p_report ->> 'occurred_at')::timestamptz,
       p_report ->> 'user_note', p_report ->> 'log_tail');
  end if;

  return v_id::text;
end;
$$;

revoke all on function public.error_report_problem(jsonb) from public, anon, authenticated;
revoke all on function public.version_ge(text, text) from public, anon, authenticated;
revoke all on function public.submit_error_report(jsonb) from public;
grant execute on function public.submit_error_report(jsonb) to anon, authenticated;

-- ---------------------------------------------------------------------------------------------------------------------
-- 5. The triage agent: two narrow roles, no service_role
-- ---------------------------------------------------------------------------------------------------------------------

-- What the agent may see. No user_note, no log_tail; manual reports (free text a person wrote) are left out entirely.
create or replace view public.v_triage_groups as
  select fingerprint_stable, exception_type, feature_area, process_kind, source, first_seen, last_seen,
         occurrence_count, distinct_installs, versions_affected, top_frame, status, issue_url, fixed_in_version
    from public.error_groups
   where source in ('crash', 'worker');

create or replace view public.v_triage_samples as
  select r.report_id, r.group_fingerprint as fingerprint_stable, r.received_at, r.app_version, r.build_id,
         r.feature_area, r.process_kind, r.source, r.exception_type, r.stack_frames, r.message_scrubbed
    from public.error_reports r
   where r.source in ('crash', 'worker') and r.channel = 'release';

revoke all on public.v_triage_groups, public.v_triage_samples from anon, authenticated;

do $$
begin
  if not exists (select 1 from pg_roles where rolname = 'triage_reader') then
    create role triage_reader nologin noinherit;
  end if;
  if not exists (select 1 from pg_roles where rolname = 'triage_writer') then
    create role triage_writer nologin noinherit;
  end if;
  -- PostgREST logs in as "authenticator" and switches to the role named in the request's key; it may only switch to
  -- roles it has been granted.
  if exists (select 1 from pg_roles where rolname = 'authenticator') then
    grant triage_reader to authenticator;
    grant triage_writer to authenticator;
  end if;
end
$$;

alter role triage_reader set statement_timeout = '10s';
alter role triage_writer set statement_timeout = '5s';
grant usage on schema public to triage_reader, triage_writer;
revoke all on all tables in schema public from triage_reader, triage_writer;
grant select on public.v_triage_groups, public.v_triage_samples to triage_reader;

-- The only thing the writer can do: mark a bug as looked at, with a note and a link. "fixed", "wontfix" and "reopened"
-- are decisions for a person, and a closed bug is not touched.
create or replace function public.triage_set_status(
  p_fingerprint text,
  p_status      text,
  p_note        text default '',
  p_issue_url   text default null,
  p_fixed_in    text default null
)
returns void
language plpgsql
security definer
set search_path = public
as $$
begin
  if p_fingerprint is null or p_fingerprint !~ '^[0-9a-f]{64}$' then raise exception 'INVALID_FINGERPRINT'; end if;
  if p_status not in ('triaged', 'fix_proposed') then raise exception 'STATUS_NOT_ALLOWED'; end if;
  if p_issue_url is not null and (p_issue_url !~ '^https://[^ ]+$' or char_length(p_issue_url) > 300) then
    raise exception 'INVALID_URL';
  end if;
  if p_fixed_in is not null then raise exception 'STATUS_NOT_ALLOWED'; end if;   -- only a person records the release that fixed it

  update public.error_groups
     set status = p_status,
         notes = left(coalesce(p_note, ''), 2000),
         issue_url = coalesce(p_issue_url, issue_url)
   where fingerprint_stable = p_fingerprint and status in ('new', 'triaged', 'fix_proposed', 'reopened');
  if not found then
    raise exception 'GROUP_NOT_FOUND_OR_CLOSED';
  end if;
end;
$$;

revoke all on function public.triage_set_status(text, text, text, text, text) from public, anon, authenticated;
grant execute on function public.triage_set_status(text, text, text, text, text) to triage_writer;

-- ---------------------------------------------------------------------------------------------------------------------
-- 6. Retention: delete detailed samples after error_retention_days (run it weekly; see the runbook for pg_cron)
-- ---------------------------------------------------------------------------------------------------------------------

create or replace function public.purge_error_reports()
returns int                        -- how many detailed reports were deleted
language plpgsql
security definer
set search_path = public
as $$
declare
  v_days int := public.flag_int('error_retention_days', 90);
  v_n    int;
begin
  delete from public.error_reports where received_at < now() - make_interval(days => v_days);
  get diagnostics v_n = row_count;
  delete from public.error_group_installs where first_seen < now() - make_interval(days => v_days);
  delete from public.error_install_daily where day < (now() at time zone 'utc')::date - 2;
  delete from public.error_hourly where hour < now() - interval '2 days';
  return v_n;
end;
$$;

revoke all on function public.purge_error_reports() from public, anon, authenticated;

notify pgrst, 'reload schema';
