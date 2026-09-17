# SmartDoc Library

Metadata-first ebook/document manager (Windows first). Scans and indexes files in
place — never copies or moves your originals.

## Setup

Requires [uv](https://docs.astral.sh/uv/). Pinned to Python 3.12 (PySide6/PyMuPDF
wheels lag behind brand-new Python releases, so avoid 3.13+/3.14 for now).

```
uv sync
uv run pytest
uv run smartdoc     # launch the app
```

**Important if your project folder lives inside OneDrive (as this one does):**
keep the virtualenv *outside* the synced tree, or `uv sync`/`uv add` will
intermittently fail with `Access is denied` while OneDrive holds a lock on
files inside `.venv`. This repo's venv lives at
`C:/Users/slook/.venvs/ebook-manager`; point uv at it in every session with:

```
export UV_PROJECT_ENVIRONMENT="C:/Users/slook/.venvs/ebook-manager"   # bash
$env:UV_PROJECT_ENVIRONMENT = "C:/Users/slook/.venvs/ebook-manager"   # PowerShell
```

(or set it once as a permanent user environment variable so you don't have
to repeat it — not done automatically here, since that's a persistent
system change).

On Windows, if you run a module's demo (`uv run python -m smartdoc.domain.models`)
from a raw console and see `UnicodeEncodeError` on Vietnamese text, the console is
using the legacy cp1252 codepage, not a bug in the code. Either run
`chcp 65001` first or set `PYTHONUTF8=1`. The shipped PySide6 GUI is not affected
by this — it only shows up printing to a bare console.

## Architecture

Clean Architecture, 4 layers, under `src/smartdoc/`:

- `core/` — `AppContext` (dependency root), `EventBus`, `ConfigManager`
- `domain/` — `Document` model, `MetadataNormalizer`
- `infrastructure/` — SQLite FTS5 `DatabaseManager`, PDF/EPUB extractors, cover cache
- `application/` — file watcher, background import job queue
- `presentation/` — PySide6 UI: main window, omnibar, grid/list view, sidebar
  (virtual collections + faceted filters), file actions, `QtEventBridge`
- `app.py` — composition root (`uv run smartdoc`)

Every class takes `context: AppContext` in `__init__` and reaches its
dependencies through it (`context.db`, `context.config`, `context.event_bus`)
instead of constructing or importing collaborators directly.

**Threading rule:** `EventBus.publish()` runs subscriber callbacks
synchronously on whatever thread called `publish()`. Background threads
(import queue workers, the file watcher) publish events too, so any Qt
widget/model that reacts to an event must not touch itself directly from
the subscriber callback — marshal onto the GUI thread first through
`presentation/qt_event_bridge.py`'s `QtEventBridge` (a QObject whose signal
is emitted from the subscriber lambda; Qt auto-queues the connected slot
onto the GUI thread when the emit happens off-thread). Every presentation
widget that subscribes to the event bus goes through this bridge.

**Theming:** Qt6 auto-adopts a dark palette when Windows is set to dark
mode. `presentation/theme.py`'s `apply_light_theme()` forces one explicit
palette app-wide instead, applied once in `app.py` before any window is
built — without it, widgets that set only a background color in their
stylesheet (not also a text color) can end up unreadable (e.g. white text
on the white Omnibar background). Any new widget's stylesheet should set
`color` alongside `background` for the same reason, as defense in depth.

**Combined query path:** `DatabaseManager.query_documents()` is the one
read path the UI uses — an optional FTS text query plus an optional
parameterized WHERE clause (facet filters, a selected Virtual Collection's
rules, or both). When a WHERE fragment touches a column that also exists on
`documents_fts` (`title`/`author`/`tags`/`content`), it must be qualified
as `documents.<col>` or SQLite raises "ambiguous column name" once a text
query is also present (see the method's docstring).

## Packaging (Windows)

```
uv sync --group dev   # pulls in pyinstaller
cd packaging
uv run pyinstaller --noconfirm --distpath ../dist --workpath ../build_pyinstaller SmartDocLibrary.spec
```

Run it from `packaging/` (not the repo root) -- when PyInstaller is given a
`.spec` file directly (as opposed to generating one from a script path), it
resolves that spec's relative paths against the spec file's own directory,
not the current working directory. `--name`/`--windowed`/etc. are makespec
options and are rejected once you're building from an existing `.spec`;
those choices are already baked into it.

Produces `dist/SmartDocLibrary/SmartDocLibrary.exe`, a standalone build that
runs without the dev venv or a system Python install (verified: launched
the built exe directly, with the real app icon on both the window and the
.exe file, and it started and stayed responsive on its own).
`packaging/SmartDocLibrary.spec` is checked in so the build is reproducible;
`packaging/generate_icon.py` regenerates the icon if it ever needs a
redesign. `dist/` and `build_pyinstaller/` are build output, not committed.

Not done yet: a signed
installer (Inno Setup or similar) so it doesn't trip Windows SmartScreen /
antivirus on a fresh machine, and the auto-updater (TDD-024).

## Status

**Milestones A–D** are done and verified by `uv run pytest` (175 tests) plus
an end-to-end smoke test that launches the real `MainWindow`, bulk-scans a
folder, and proves the live file watcher flows through to the UI.

What works: point the app at a folder (File → Thêm thư mục...), it
watches + bulk-scans, extracts metadata/cover/text from PDF and EPUB,
indexes into SQLite FTS5, and shows results in a grid with search
(debounced Omnibar), sort + cover-size slider, pagination, double-click to
open, a right-click menu (open / reveal in Explorer / edit metadata / bulk
edit / remove from library), a faceted filter panel (by format/author, with
counts), Virtual Collections (saved rule-based filters) in the sidebar, a
Settings dialog (file types, watch folders, theme, worker threads), a
Duplicate Finder (exact content-hash matches + fuzzy title/author matches),
and a Calibre library importer (File → Nhập từ thư viện Calibre...).

Content hashing for duplicate detection needed a schema change
(`content_hash` column); `DatabaseManager.initialize_tables()` now migrates
an older library.db in place (`ALTER TABLE ... ADD COLUMN`) rather than
assuming a fresh database, since `CREATE TABLE IF NOT EXISTS` is a no-op
against an existing table under an old schema.

Not yet implemented: AZW3/MOBI binary parsing (routed through the EPUB
extractor today, which only handles zip/OPF containers and will silently
fall back to filename-as-title for real AZW3/MOBI files), multi-rule
collection editing (the creation dialog only supports one condition — the
domain layer supports AND/OR multi-rule collections already, just no UI for
it yet), grouped list view (TDD-013's "group by year/author" header rows),
Calibre tag/rating carryover (see calibre_migrator.py's docstring), an
installed app icon (done) but no signed installer yet, and most of
Milestone F (AI review, semantic search, personal cloud export).

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

Known, accepted risk (carried over from the original design): every
install of the app ships pointed at the *same* Supabase project, so all
reviews across all users are visible to everyone and anyone can post as
any nickname — this is the intended "anonymous community reviews"
behavior, not a flaw, but it does mean there's no per-user moderation or
abuse prevention beyond what the RLS policies and Supabase's own rate
limiting provide.
