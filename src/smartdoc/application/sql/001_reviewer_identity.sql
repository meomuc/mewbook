-- MewBook 1.0.0 -- Community reviews: anonymous identity + unique nicknames.
--
-- Run ONCE in the Supabase SQL Editor of the project configured in
-- Settings -> Đánh giá cộng đồng, after the original `reviews` table and
-- `review_stats` view from application/cloud_reviews.py exist. Safe to
-- re-run (every statement is idempotent).
--
-- What it adds:
--   * reviews.user_hash   -- sha256 of the installation's secret token
--                            (see src/smartdoc/core/user_identity.py). Public.
--   * reviews.updated_at  -- set when a review is edited.
--   * reviewers           -- one row per claimed nickname, owned by a user_hash.
--   * submit_review(...)  -- the ONLY write path. Runs server-side, hashes the
--                            secret token itself, rejects a nickname owned by
--                            someone else, and only lets the owner update a
--                            review. Direct INSERTs from the anon key are
--                            revoked so user_hash can't be forged.

create extension if not exists pgcrypto with schema extensions;

alter table public.reviews add column if not exists user_hash text;
alter table public.reviews add column if not exists updated_at timestamptz;
create index if not exists reviews_doc_id_idx on public.reviews (doc_id);
create index if not exists reviews_user_hash_idx on public.reviews (user_hash);

create table if not exists public.reviewers (
  nickname_key text primary key,          -- lower-cased, whitespace-collapsed nickname
  nickname     text not null,             -- as first typed
  user_hash    text not null,
  created_at   timestamptz not null default now()
);

alter table public.reviewers enable row level security;
drop policy if exists "Allow public read" on public.reviewers;
create policy "Allow public read" on public.reviewers for select using (true);

-- Writes now go exclusively through submit_review() below.
drop policy if exists "Allow public insert" on public.reviews;

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
  v_nickname text := left(btrim(coalesce(p_nickname, '')), 40);
  v_key      text;
  v_owner    text;
  v_row      public.reviews;
begin
  if p_token is null or length(p_token) < 32 then
    raise exception 'INVALID_TOKEN';
  end if;
  if p_rating is null or p_rating < 1 or p_rating > 5 then
    raise exception 'INVALID_RATING';
  end if;
  if coalesce(p_doc_id, '') = '' then
    raise exception 'INVALID_DOC';
  end if;

  v_hash := encode(extensions.digest(p_token, 'sha256'), 'hex');
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
