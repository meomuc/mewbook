-- SPDX-License-Identifier: AGPL-3.0-or-later
-- 004_community_metadata.sql: Community-contributed book metadata (Supabase).
--
-- fingerprint is the stable cross-user key:
--   "isbn:<isbn13>"        when an ISBN-13 is known
--   sha256[:32] of         normalize(title)|normalize(author)  otherwise
-- See application/community_metadata_sync.make_fingerprint().
--
-- This file is intentionally append-only (CLAUDE.md rule: never edit a
-- released migration).  Any schema change goes in 005_*.sql.

create table if not exists public.community_metadata (
    fingerprint      text         primary key,
    title            text,
    author           text,
    publisher        text,
    pub_year         int,
    language         text,         -- 2-letter ISO code (e.g. "vi", "en")
    isbn             text,
    submitted_count  int          not null default 1,
    last_updated     timestamptz  not null default now(),
    source_url       text          -- canonical Open Library / Google Books URL if known
);

comment on table public.community_metadata is
    'One row per unique book fingerprint; aggregated from user contributions.';

alter table public.community_metadata enable row level security;

create policy "public read community_metadata"
    on public.community_metadata
    for select
    using (true);

-- Incremental upsert via RPC so the anon role never holds direct write access.
create or replace function public.contribute_metadata(
    p_fingerprint  text,
    p_data         jsonb
) returns void
language plpgsql
security definer
set search_path = public
as $$
begin
    -- Basic sanity: fingerprint must be non-empty.
    if p_fingerprint is null or length(trim(p_fingerprint)) = 0 then
        return;
    end if;

    insert into community_metadata (
        fingerprint, title, author, publisher,
        pub_year, language, isbn,
        submitted_count, last_updated, source_url
    ) values (
        p_fingerprint,
        nullif(trim(p_data->>'title'),     ''),
        nullif(trim(p_data->>'author'),    ''),
        nullif(trim(p_data->>'publisher'), ''),
        (p_data->>'pub_year')::int,
        nullif(trim(p_data->>'language'),  ''),
        nullif(trim(p_data->>'isbn'),      ''),
        1,
        now(),
        nullif(trim(p_data->>'source_url'), '')
    )
    on conflict (fingerprint) do update set
        -- Non-destructive: only fill in blank fields; never overwrite with a blank.
        title           = coalesce(nullif(trim(excluded.title), ''),           community_metadata.title),
        author          = coalesce(nullif(trim(excluded.author), ''),          community_metadata.author),
        publisher       = coalesce(nullif(trim(excluded.publisher), ''),       community_metadata.publisher),
        pub_year        = coalesce(excluded.pub_year,                          community_metadata.pub_year),
        language        = coalesce(nullif(trim(excluded.language), ''),        community_metadata.language),
        isbn            = coalesce(nullif(trim(excluded.isbn), ''),            community_metadata.isbn),
        submitted_count = community_metadata.submitted_count + 1,
        last_updated    = now();
end;
$$;

-- Revoke all direct writes; RPC only.
revoke insert, update, delete
    on public.community_metadata
    from anon, authenticated;

grant execute
    on function public.contribute_metadata(text, jsonb)
    to anon, authenticated;

-- Runtime kill-switch and size guard (reuses the service_flags table from 002).
insert into public.service_flags (key, value, updated_at) values
    ('community_metadata_enabled', 'on',  now()),
    ('metadata_max_mb',            '100', now())
on conflict (key) do nothing;
