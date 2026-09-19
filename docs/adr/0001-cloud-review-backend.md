# ADR 0001 -- Backend of the community review feature: Google Drive, then Firestore, then Supabase

- **Status:** accepted (implemented in `application/cloud_reviews.py`; anonymous identity since 1.0.0).
- **Moved from:** the README "Status" section, where this story used to live (S0-11).
- **Later work:** hardening and moderation of the Supabase project is planned in stage S2
  (`docs/handoff/04_IMPLEMENTATION_PLAN.md`).

## Context and decision

**Milestone F, Cloud Review System (TDD-016), redesigned twice: Drive →
Firestore → Supabase.** The original spec (a shared service account writing
review JSON files to Google Drive) doesn't work at all: verified against
the real API that Google has removed personal storage quota for service
accounts, so they cannot create files even inside a folder a real person
explicitly shared with them as Editor (sharing worked, the service account
had real Editor permission, and file creation still failed with
`storageQuotaExceeded`, with or without `supportsAllDrives=True`; Shared
Drives / domain-wide delegation, Google's own suggested workarounds, both
need a paid Workspace plan). Pivoted to Firestore, which should have had no
such wall — but every attempt (hand-rolled REST calls, the official
`google-cloud-firestore` Admin client library, an Editor-level IAM role, the
full `cloud-platform` OAuth scope, a Standard-edition Native-mode database
created specifically for this, several minutes of wait for propagation) hit
an identical, unexplained `403 Missing or insufficient permissions`,
pointing at something at the Google Cloud organization/project-policy level
neither of us could see or fix from the outside.

`application/cloud_reviews.py` now targets **Supabase** instead (a
`reviews` table via its auto-generated PostgREST API, called with plain
`requests` — no SDK). This turned out to be a better fit, not just a
workaround: Supabase's "anon" API key is *designed* to be public and
embedded in client apps, with access control enforced by Postgres Row
Level Security policies on the table, not by keeping the key secret. That
is a sounder security model for this feature than the original spec (a
single powerful Google credential shipped inside every install, usable for
far more than posting reviews) — no secret file to protect, no
`.gitignore` special-casing needed, `AppConfig.supabase_url` /
`.supabase_anon_key` are plain config values. **Verified working against a
real Supabase project end to end** (submit → fetch round-tripped real data
correctly, ordered newest-first). Wired into the UI as
`presentation/review_dialog.py` (a star-rating + comment form, reachable
from a document's right-click menu → "Xem / Viết đánh giá"); network calls
run on a background thread and report back through plain Qt signals, not
the EventBus.

One-time setup (exact SQL in `cloud_reviews.py`'s module docstring): create
a Supabase project, create the `reviews` table with `select`/`insert` RLS
policies open to `anon`, and set `AppConfig.supabase_url` /
`.supabase_anon_key`. There is deliberately no `delete` policy — the app
has no delete-review feature, so `SupabaseReviewSync.delete_reviews()` (a
test/cleanup helper) silently affects zero rows against a table set up
this way; that's correct RLS behavior, not a bug.

Since 1.0.0 every installation has an anonymous identity
(`core/user_identity.py`): a random secret token, generated on first run,
stored encrypted, and deleted by the uninstaller. Reviews are written only
through the server-side `submit_review` function
(`src/smartdoc/application/sql/001_reviewer_identity.sql`, which you can copy
from Settings → "Sao chép SQL nâng cấp"). That function hashes the token
server-side, so a nickname belongs to the first installation that used it,
only a review's author can update it, and authorship can't be forged. There
is still no moderation beyond that and Supabase's own rate limiting:
reviews stay public and anonymous.

## Consequences

- The client holds no secret that grants more than posting and reading reviews; the Supabase "anon" key is
  meant to be public and the security boundary is Row Level Security plus the `submit_review` function.
- Moderation is manual and done by the project owner in the Supabase dashboard (decision D4); the runbook is
  planned in S2-05.
- Reviews are public and anonymous. What the client sends and what is stored is listed in
  `docs/legal/DATA_SOURCES.md` (section 2.8).
