-- SPDX-License-Identifier: AGPL-3.0-or-later
-- MewBook -- Community reviews: the base table and the stats view. Run FIRST, once, in the Supabase SQL Editor of the project
-- (then 001, 002, 003). Safe to re-run: every statement is idempotent.
--
-- This is the "one-time setup" from the docstring of application/cloud_reviews.py, kept as a file because 001 assumes the
-- `reviews` table already exists. The old "Allow public insert" policy is deliberately NOT created: since 001 every write goes
-- through submit_review(), and 001 drops that policy anyway.

create table if not exists public.reviews (
  id         bigint generated always as identity primary key,
  doc_id     text not null,
  nickname   text not null default 'Ẩn danh',
  rating     int2 not null check (rating between 1 and 5),
  comment    text not null default '',
  created_at timestamptz not null default now()
);

alter table public.reviews enable row level security;
drop policy if exists "Allow public read" on public.reviews;
create policy "Allow public read" on public.reviews for select using (true);

create or replace view public.review_stats as
  select doc_id, avg(rating)::float8 as avg_rating, count(*) as review_count
  from public.reviews
  group by doc_id;

grant select on public.review_stats to anon, authenticated;
