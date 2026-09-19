# MewBook ("Mèo Mực")

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

Or just double-click `run.bat` in the project root — it points
`UV_PROJECT_ENVIRONMENT` at a virtualenv outside the project folder (see below),
sets `PYTHONUTF8` and runs `uv run smartdoc` for you, and stays open on a crash so
you can read the traceback instead of the window flashing shut.

**Important if your project folder lives inside OneDrive (or any other
sync tool):** keep the virtualenv *outside* the synced tree, or
`uv sync`/`uv add` will intermittently fail with `Access is denied` while the
sync client holds a lock on files inside `.venv`. `run.bat` uses
`%USERPROFILE%\.venvs\ebook-manager`; to use the same location from your own
shell, point uv at it in every session with:

```
export UV_PROJECT_ENVIRONMENT="$HOME/.venvs/ebook-manager"       # bash
$env:UV_PROJECT_ENVIRONMENT = "$env:USERPROFILE\.venvs\ebook-manager"   # PowerShell
```

(or set it once as a permanent user environment variable so you don't have
to repeat it — not done automatically here, since that's a persistent
system change). `run.bat` keeps a value you have already set, so a different
location works too.

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
- `application/` — file watcher, background import job queue, smart classification service,
  cover search, metadata lookup (`metadata_lookup.py`), metadata apply/undo
  (`metadata_applier.py`) and the safe file writer (`metadata_writer.py`)
- `presentation/` — PySide6 UI: main window, omnibar, grid/list view, sidebar
  (virtual collections + hashtag/author/format filters), file actions, `QtEventBridge`
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

## Smart classification (phân loại thông minh)

Tags books with a category (a hashtag such as "Kiếm hiệp - Tiên hiệp") and
files that hashtag under a folder of the sidebar's Hashtag tree ("Văn học").
It never moves or edits the original files, only adds hashtags, and a whole run
can be undone from the bar above the list.

**Where it appears**
- After files or folders are added, one compact popup carries the import result
  and asks whether to classify the new documents. "Ghi nhớ lựa chọn" makes the
  answer permanent; Settings → Phân loại changes it back (ask / always / never).
- The button "✨ Phân loại thông minh" above the document list (also Tools menu)
  applies to the list being viewed, i.e. the folder, hashtag or collection
  selected in the sidebar plus any search, all pages, and says how many
  documents that is before starting. Right-click on selected documents does the
  same for just those.

**How it works** (`domain/taxonomy.py`, `infrastructure/text_sampler.py`,
`infrastructure/vi_tokenizer.py`, `application/classification_features.py`,
`domain/text_classifier.py`, `application/classify_worker.py`,
`application/smart_classifier.py`)
- The first 2,000 to 5,000 words (Settings, default 3,000) are read from EPUB,
  PDF or MOBI, together with the title, author, your own tags, subjects embedded
  in the file, its description and its chapter titles.
- Vietnamese text is word-segmented with pyvi ("văn học thế giới" becomes
  "văn_học thế_giới"); text without diacritics gets word-pair features instead.
- A sparse linear model (one JSON file) scores 48 categories from
  `src/smartdoc/data/taxonomy.json`. When the model is not sure it leaves the
  book alone instead of guessing; those books are remembered as looked at.
- A category you already put on a book, or a folder you already chose for a
  hashtag, is never overridden.

**Speed rules.** Nothing is loaded at startup: no model, no tokenizer, no
process. A job runs in a separate spawned process at below-normal CPU and low
disk priority (one process for small jobs, two at most for big ones), works in
small chunks so Stop reacts at once, writes to the database in batches and
refreshes the list at most every two seconds. The process exits when the job
ends, so its memory (pyvi pulls in scikit-learn, about 100 MB) is only used
while classifying.

**Training is a separate program.** The app only runs the model. `train.py`
builds it, and you run it whenever you have collected more labelled books:

```
uv run python train.py --dry-run                       # train and report, but save nothing
uv run python train.py                                 # your library + your tags
uv run python train.py --dataset D:\Sach\da-phan-loai   # + folders named after categories
uv run python train.py --output builtin                # replace the model shipped with the app
```

By default it writes `%APPDATA%\SmartDocLibrary\models\classifier_model.json.gz`
(used in preference to the shipped model) and a plain-text report next to it. It
reads the library read-only and only trusts labels that people wrote (category
tags, subjects inside the files), never tags the classifier itself applied.
`train.py --help` lists all options. The category list can be extended without
touching code: put a `taxonomy.json` in the app data folder that adds
categories, overrides one by `id`, or removes one with `"disabled": true`, then
re-run `train.py`.

**Measured accuracy** (trained on 9,451 labelled books of the author's own
library, evaluated on 1,689 held-out titles with their embedded labels hidden):
the right category 71% of the time, the right sidebar folder 90%; with the
abstain thresholds it answers about 56% of books at about 85% precision. On
books that had no label at all the figures are lower (roughly 60% category,
78% folder). The shipped model reflects that library (mostly Vietnamese
fiction and non-fiction), so retrain on yours for best results.

## Versioning & releases

MewBook follows [Semantic Versioning 2.0.0](https://semver.org). **1.0.0
(2026-09-19) is the first release.** The version is
`MAJOR.MINOR.PATCH`:

| Bump | When | Examples |
|---|---|---|
| **MAJOR** (2.0.0) | Existing users' data, settings or workflow would break or need migrating by hand | incompatible library.db change with no automatic migration, a feature removed, a new required server-side step |
| **MINOR** (1.1.0) | New features, backwards compatible | a new cover source, a new AI provider, a new theme |
| **PATCH** (1.0.1) | Bug fixes only, no new behavior | a crash fix, a wrong label, a broken API call |

Pre-releases add a suffix, e.g. `1.1.0-beta.1`, and rank below `1.1.0`.

- **Single source of truth:** `__version__` in `src/smartdoc/__init__.py`.
  `pyproject.toml` (hatch dynamic version), the About dialog, the log header,
  the exe's version resource and the installer all read it from there, so
  never edit a version number anywhere else.
- **Changelog:** every user-visible change goes under `## [Unreleased]` in
  `CHANGELOG.md` ([Keep a Changelog](https://keepachangelog.com) format:
  Added / Changed / Deprecated / Removed / Fixed / Security).
- **Release checklist:** the full per-release checklist (gates, clean-machine
  tests, signing, AGPL source package, tag) is `docs/RELEASE_CHECKLIST.md`. In short:
  1. Move the `[Unreleased]` entries under a new `## [X.Y.Z] - YYYY-MM-DD` heading.
  2. Set `__version__ = "X.Y.Z"`, and make sure `APP_SOURCE_URL_TEMPLATE` (same file) points at the
     public repository so Help → About links to the source of exactly this version.
  3. `powershell -ExecutionPolicy Bypass -File packaging\build.ps1` (runs the tests, then builds the exe and installer).
  4. Commit, then tag: `git tag -a vX.Y.Z -m "MewBook X.Y.Z"` and `git push --tags`.
  4a. `dist/` and `build_pyinstaller/` are build output (they also contain
     local build paths): never commit them and never ship them as the source
     release. Make the source archive from tracked files only
     (`git archive --format=zip -o MewBook-X.Y.Z-src.zip vX.Y.Z`), never by
     zipping the working folder. Only the installer/exe built from them is
     distributed.
  4b. Attach the installer and the source archive to the release and publish their SHA-256
     checksums (`Get-FileHash <file> -Algorithm SHA256`, collected in `SHA256SUMS.txt`); the
     AGPL requires the corresponding source to be offered with every binary.
  5. If the release needs a Supabase change, say so under **Security** or
     **Changed** in the changelog and ship the SQL in `src/smartdoc/application/sql/`.

## Packaging (Windows)

One command builds everything, stamped with the current version:

```
uv sync --group dev   # pulls in pyinstaller
powershell -ExecutionPolicy Bypass -File packaging\build.ps1
```

This runs the test suite, builds
`dist/MewBook/MewBook.exe` (with `LICENSE` and `THIRD_PARTY_NOTICES.md` bundled) (whose Properties → Details show the version,
publisher and copyright), and, if [Inno Setup 6](https://jrsoftware.org/isdl.php)
is installed, builds `dist/installer/MewBook-Setup-X.Y.Z.exe` from
`packaging/MewBook.iss` (its licence page shows `LICENSE`, AGPL-3.0-or-later). The installer runs per-user (no admin prompt), adds
Start menu and optional desktop shortcuts, and upgrades in place (fixed
`AppId`). On uninstall it deletes the anonymous identity (`identity.dat`), so
a reinstall gets a new one, and it asks whether to delete the library data
too. Original ebook files are never touched.

To build only the exe by hand:

```
cd packaging
uv run pyinstaller --noconfirm --distpath ../dist --workpath ../build_pyinstaller MewBook.spec
```

Run it from `packaging/` (not the repo root) -- when PyInstaller is given a
`.spec` file directly (as opposed to generating one from a script path), it
resolves that spec's relative paths against the spec file's own directory,
not the current working directory. `--name`/`--windowed`/etc. are makespec
options and are rejected once you're building from an existing `.spec`;
those choices are already baked into it.

Produces `dist/MewBook/MewBook.exe`, a standalone build that
runs without the dev venv or a system Python install (verified: launched
the built exe directly, with the real app icon on both the window and the
.exe file, and it started and stayed responsive on its own).
`packaging/MewBook.spec` is checked in so the build is reproducible;
`packaging/generate_icon.py` regenerates the icon if it ever needs a
redesign. `dist/` and `build_pyinstaller/` are build output, not committed.
(The build/product name is MewBook -- "Mèo Mực" is the in-app display name;
see AppConfig's docstring on `APP_DIR_NAME` for why the on-disk %APPDATA%
folder itself keeps its original name across the rename.)

Not done yet: **code signing** (needs a purchased code-signing certificate;
until then Windows SmartScreen warns on first run of the installer), and the
auto-updater (TDD-024). Also see `THIRD_PARTY_NOTICES.md` for licensing
steps that must happen before selling closed-source copies (PyMuPDF is
AGPL, mobi is GPL).

## Status

**Milestones A–D** are done and verified by `uv run pytest` (175 tests) plus
an end-to-end smoke test that launches the real `MainWindow`, bulk-scans a
folder, and proves the live file watcher flows through to the UI.

What works: point the app at a folder (File → Thêm thư mục...), it
watches + bulk-scans, extracts metadata/cover/text from PDF and EPUB,
indexes into SQLite FTS5, and shows results in a grid with search
(debounced Omnibar), sort + cover-size slider, pagination, double-click to
open, a right-click menu (open / reveal in Explorer / edit metadata / bulk
edit / remove from library), a filter sidebar (hashtag / author / format with live
counts, an "Đang lọc" bar and quick-filter suggestions), Virtual Collections (saved rule-based filters) in the sidebar, a
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

## License

MewBook is free software: you can redistribute it and/or modify it under the terms of the GNU Affero General
Public License, version 3 or (at your option) any later version (`AGPL-3.0-or-later`, see `LICENSE`). It is
distributed in the hope that it will be useful, but **without any warranty**. Third-party components and their
licences are listed in `THIRD_PARTY_NOTICES.md`; the audit is in `docs/legal/LICENSE_INVENTORY.md`. New source
files follow `docs/legal/SPDX_POLICY.md`.
