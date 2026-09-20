-- SPDX-License-Identifier: AGPL-3.0-or-later
-- MewBook 1.1.0 -- Review moderation, abuse limits and the public service switches (S2-02).
--
-- Run ONCE in the Supabase SQL Editor, AFTER 001_reviewer_identity.sql. Safe to re-run: every statement is idempotent,
-- and re-running never overwrites a value you have tuned in service_flags.
--
-- Compatible with MewBook 1.0.0 clients: submit_review keeps its name and arguments, the reviews and review_stats
-- views keep their columns (the reviews table only gains three), and a 1.0.0 client simply stops seeing hidden reviews.
--
-- What it adds
--   * service_flags        -- public key-value switches read by the app: reviews_enabled (kill-switch), banner_message,
--                             and the limits below. Change a value with an UPDATE; no new release is needed.
--   * reviews.is_hidden / hidden_reason / hidden_at
--                          -- a hidden review is invisible to everyone but you: the public "select" policy shows only
--                             visible reviews, and review_stats leaves hidden ones out.
--   * review_reports       -- one row per (review, reporter); reporters are identified by the sha256 of their secret
--                             token, exactly like reviews. A review reported by `auto_hide_threshold` different people is
--                             hidden automatically (at most `max_auto_hides_per_hour` times an hour, so a flood of fake
--                             reporters cannot hide the whole catalogue).
--   * blocked_identities   -- user_hash values that may no longer post or report.
--   * submit_review        -- same signature; now also refuses when reviews are switched off (REVIEWS_DISABLED), for a
--                             blocked identity (IDENTITY_BLOCKED), and past the per-identity and global limits
--                             (RATE_LIMITED); a NEW review over max_comment_length is refused (COMMENT_TOO_LONG).
--   * report_review        -- the way a user reports a review (see the MODERATION_RUNBOOK for what you do with reports).
--
-- Error codes the app maps to Vietnamese messages: REVIEWS_DISABLED, IDENTITY_BLOCKED, RATE_LIMITED, COMMENT_TOO_LONG,
-- INVALID_TOKEN, INVALID_RATING, INVALID_DOC, NICKNAME_TAKEN, REVIEW_NOT_OWNED, REVIEW_NOT_FOUND, CANNOT_REPORT_OWN,
-- ALREADY_REPORTED, INVALID_REASON.
--
-- Defaults (docs/handoff/02 section 8, decision O10): hide at 3 different reporters; 10 reviews an hour and 30 a day per
-- identity; comment up to 2000 characters for new reviews. The nickname limit stays at the 40 characters submit_review
-- already used (a lower limit would change the name of everybody with a 31-40 character nickname the next time they edit).

-- ---------------------------------------------------------------------------------------------------------------------
-- 1. The public switches
-- ---------------------------------------------------------------------------------------------------------------------

create table if not exists public.service_flags (
  key        text primary key,
  value      text not null,
  updated_at timestamptz not null default now()
);

alter table public.service_flags enable row level security;
drop policy if exists "Public read flags" on public.service_flags;
create policy "Public read flags" on public.service_flags for select using (true);
revoke all on public.service_flags from anon, authenticated;
grant select on public.service_flags to anon, authenticated;

insert into public.service_flags (key, value) values
  ('reviews_enabled',           'true'),
  ('banner_message',            ''),
  ('auto_hide_threshold',       '3'),
  ('max_reviews_per_hour',      '10'),
  ('max_reviews_per_day',       '30'),
  ('max_reviews_global_per_hour', '1000'),
  ('max_reports_per_day',       '20'),
  ('max_auto_hides_per_hour',   '20'),
  ('max_comment_length',        '2000'),
  ('max_nickname_length',       '40')
on conflict (key) do nothing;

-- Readers for the switches. Internal: only the functions below (which run with their owner's rights) call them.
create or replace function public.flag_text(p_key text, p_default text)
returns text
language sql
stable
security definer
set search_path = public
as $$
  select coalesce((select value from public.service_flags where key = p_key), p_default)
$$;

create or replace function public.flag_int(p_key text, p_default int)
returns int
language sql
stable
security definer
set search_path = public
as $$
  select coalesce(
    (select case when value ~ '^[0-9]{1,9}$' then value::int end from public.service_flags where key = p_key),
    p_default)
$$;

create or replace function public.flag_on(p_key text, p_default boolean default true)
returns boolean
language sql
stable
security definer
set search_path = public
as $$
  select coalesce(
    (select lower(btrim(value)) not in ('false', '0', 'no', 'off') from public.service_flags where key = p_key),
    p_default)
$$;

-- sha256 of a secret token, in hex: the same value 001_reviewer_identity.sql stores as user_hash.
create or replace function public.hash_token(p_token text)
returns text
language sql
immutable
security definer
set search_path = public, extensions
as $$
  select encode(extensions.digest(p_token, 'sha256'), 'hex')
$$;

revoke all on function public.flag_text(text, text) from public, anon, authenticated;
revoke all on function public.flag_int(text, int) from public, anon, authenticated;
revoke all on function public.flag_on(text, boolean) from public, anon, authenticated;
revoke all on function public.hash_token(text) from public, anon, authenticated;

-- ---------------------------------------------------------------------------------------------------------------------
-- 2. Hiding reviews
-- ---------------------------------------------------------------------------------------------------------------------

alter table public.reviews add column if not exists is_hidden     boolean not null default false;
alter table public.reviews add column if not exists hidden_reason text;
alter table public.reviews add column if not exists hidden_at     timestamptz;

create index if not exists reviews_visible_doc_idx on public.reviews (doc_id) where not is_hidden;
create index if not exists reviews_created_at_idx  on public.reviews (created_at);
create index if not exists reviews_user_hash_created_idx on public.reviews (user_hash, created_at);

-- New constraints skip the rows that are already there ("not valid"): nothing existing can make them fail.
do $$
begin
  if not exists (select 1 from pg_constraint where conname = 'reviews_hidden_has_time' and conrelid = 'public.reviews'::regclass) then
    alter table public.reviews add constraint reviews_hidden_has_time check (not is_hidden or hidden_at is not null) not valid;
  end if;
  if not exists (select 1 from pg_constraint where conname = 'reviews_comment_max_length' and conrelid = 'public.reviews'::regclass) then
    alter table public.reviews add constraint reviews_comment_max_length check (char_length(comment) <= 4000) not valid;
  end if;
  if not exists (select 1 from pg_constraint where conname = 'reviews_nickname_max_length' and conrelid = 'public.reviews'::regclass) then
    alter table public.reviews add constraint reviews_nickname_max_length check (char_length(nickname) <= 40) not valid;
  end if;
end
$$;

alter table public.reviews enable row level security;
-- The old policy showed every row; policies add up, so it must go or hidden reviews would stay visible.
drop policy if exists "Allow public read" on public.reviews;
drop policy if exists "Public read visible reviews" on public.reviews;
create policy "Public read visible reviews" on public.reviews for select using (not is_hidden);

-- Reading stays open; every write goes through submit_review / report_review (which run with the owner's rights).
revoke insert, update, delete, truncate, references, trigger on public.reviews from anon, authenticated;
revoke insert, update, delete, truncate, references, trigger on public.reviewers from anon, authenticated;

-- Hidden reviews do not count. (The view runs with its owner's rights, so the filter has to be here, not in a policy.)
create or replace view public.review_stats as
  select doc_id, avg(rating)::float8 as avg_rating, count(*) as review_count
  from public.reviews
  where not is_hidden
  group by doc_id;

grant select on public.review_stats to anon, authenticated;

-- ---------------------------------------------------------------------------------------------------------------------
-- 3. Reports and blocked identities (nobody but you can read or write these)
-- ---------------------------------------------------------------------------------------------------------------------

create table if not exists public.review_reports (
  id            bigint generated always as identity primary key,
  review_id     bigint not null references public.reviews (id) on delete cascade,
  reporter_hash text   not null,
  reason        text   not null check (reason in ('spam', 'abuse', 'illegal', 'privacy', 'other')),
  created_at    timestamptz not null default now(),
  dismissed_at  timestamptz,                       -- set by you when the report was looked at and rejected
  unique (review_id, reporter_hash)
);
create index if not exists review_reports_open_idx     on public.review_reports (review_id) where dismissed_at is null;
create index if not exists review_reports_reporter_idx on public.review_reports (reporter_hash, created_at);

create table if not exists public.blocked_identities (
  user_hash  text primary key,
  reason     text not null default '',
  blocked_at timestamptz not null default now()
);

alter table public.review_reports enable row level security;
alter table public.blocked_identities enable row level security;
revoke all on public.review_reports from anon, authenticated;
revoke all on public.blocked_identities from anon, authenticated;

-- ---------------------------------------------------------------------------------------------------------------------
-- 4. submit_review: the same door, with limits
-- ---------------------------------------------------------------------------------------------------------------------

create or replace function public.submit_review(
  p_token     text,
  p_doc_id    text,
  p_nickname  text,
  p_rating    int,
  p_comment   text,
  p_review_id bigint default null
)
returns public.reviews
language plpgsql
security definer
set search_path = public, extensions
as $$
declare
  v_hash     text;
  v_nickname text := left(btrim(coalesce(p_nickname, '')), public.flag_int('max_nickname_length', 40));
  v_key      text;
  v_owner    text;
  v_row      public.reviews;
begin
  if not public.flag_on('reviews_enabled') then
    raise exception 'REVIEWS_DISABLED';
  end if;
  if p_token is null or length(p_token) < 32 then
    raise exception 'INVALID_TOKEN';
  end if;
  if p_rating is null or p_rating < 1 or p_rating > 5 then
    raise exception 'INVALID_RATING';
  end if;
  if coalesce(p_doc_id, '') = '' then
    raise exception 'INVALID_DOC';
  end if;

  v_hash := public.hash_token(p_token);
  if exists (select 1 from public.blocked_identities where user_hash = v_hash) then
    raise exception 'IDENTITY_BLOCKED';
  end if;

  -- Limits apply to NEW reviews: editing your own review is not posting more.
  if p_review_id is null then
    if (select count(*) from public.reviews where user_hash = v_hash and created_at > now() - interval '1 hour')
         >= public.flag_int('max_reviews_per_hour', 10)
       or (select count(*) from public.reviews where user_hash = v_hash and created_at > now() - interval '1 day')
         >= public.flag_int('max_reviews_per_day', 30)
       or (select count(*) from public.reviews where created_at > now() - interval '1 hour')
         >= public.flag_int('max_reviews_global_per_hour', 1000) then
      raise exception 'RATE_LIMITED';
    end if;
    if char_length(coalesce(p_comment, '')) > public.flag_int('max_comment_length', 2000) then
      raise exception 'COMMENT_TOO_LONG';
    end if;
  end if;

  if v_nickname = '' then
    v_nickname := 'Ẩn danh';
  end if;
  v_key := lower(regexp_replace(v_nickname, '\s+', ' ', 'g'));

  -- "Ẩn danh" (anonymous) is shared by everyone and never claimed.
  if v_key <> lower('Ẩn danh') then
    insert into public.reviewers (nickname_key, nickname, user_hash)
    values (v_key, v_nickname, v_hash)
    on conflict (nickname_key) do nothing;

    select user_hash into v_owner from public.reviewers where nickname_key = v_key;
    if v_owner is distinct from v_hash then
      raise exception 'NICKNAME_TAKEN';
    end if;
  end if;

  if p_review_id is not null then
    update public.reviews
       set nickname = v_nickname,
           rating = p_rating,
           comment = left(coalesce(p_comment, ''), 4000),
           updated_at = now()
     where id = p_review_id and user_hash = v_hash
    returning * into v_row;
    if not found then
      raise exception 'REVIEW_NOT_OWNED';
    end if;
  else
    insert into public.reviews (doc_id, nickname, rating, comment, user_hash)
    values (p_doc_id, v_nickname, p_rating, left(coalesce(p_comment, ''), 4000), v_hash)
    returning * into v_row;
  end if;

  return v_row;
end;
$$;

revoke all on function public.submit_review(text, text, text, int, text, bigint) from public;
grant execute on function public.submit_review(text, text, text, int, text, bigint) to anon, authenticated;

-- ---------------------------------------------------------------------------------------------------------------------
-- 5. report_review: how a user flags a review
-- ---------------------------------------------------------------------------------------------------------------------

create or replace function public.report_review(
  p_token     text,
  p_review_id bigint,
  p_reason    text default 'other'
)
returns int                       -- how many different people have reported this review (and not been dismissed)
language plpgsql
security definer
set search_path = public, extensions
as $$
declare
  v_hash   text;
  v_owner  text;
  v_reason text := lower(btrim(coalesce(p_reason, 'other')));
  v_count  int;
begin
  if not public.flag_on('reviews_enabled') then
    raise exception 'REVIEWS_DISABLED';
  end if;
  if p_token is null or length(p_token) < 32 then
    raise exception 'INVALID_TOKEN';
  end if;
  if v_reason not in ('spam', 'abuse', 'illegal', 'privacy', 'other') then
    raise exception 'INVALID_REASON';
  end if;

  v_hash := public.hash_token(p_token);
  if exists (select 1 from public.blocked_identities where user_hash = v_hash) then
    raise exception 'IDENTITY_BLOCKED';
  end if;

  select user_hash into v_owner from public.reviews where id = p_review_id;
  if not found then
    raise exception 'REVIEW_NOT_FOUND';
  end if;
  if v_owner = v_hash then
    raise exception 'CANNOT_REPORT_OWN';
  end if;

  if (select count(*) from public.review_reports where reporter_hash = v_hash and created_at > now() - interval '1 day')
       >= public.flag_int('max_reports_per_day', 20) then
    raise exception 'RATE_LIMITED';
  end if;

  insert into public.review_reports (review_id, reporter_hash, reason)
  values (p_review_id, v_hash, v_reason)
  on conflict (review_id, reporter_hash) do nothing;
  if not found then
    raise exception 'ALREADY_REPORTED';
  end if;

  select count(*) into v_count
    from public.review_reports
   where review_id = p_review_id and dismissed_at is null;

  if v_count >= public.flag_int('auto_hide_threshold', 3)
     and (select count(*) from public.reviews where hidden_reason like 'auto:%' and hidden_at > now() - interval '1 hour')
           < public.flag_int('max_auto_hides_per_hour', 20) then
    update public.reviews
       set is_hidden = true, hidden_reason = 'auto: ' || v_count || ' reports', hidden_at = now()
     where id = p_review_id and not is_hidden;
  end if;

  return v_count;
end;
$$;

revoke all on function public.report_review(text, bigint, text) from public;
grant execute on function public.report_review(text, bigint, text) to anon, authenticated;

-- Make the new functions visible to the REST API at once.
notify pgrst, 'reload schema';
