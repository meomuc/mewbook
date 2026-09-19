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
uv run python train.py --release --output builtin      # replace the model shipped with the app (higher word-frequency
                                                       # thresholds, so no names of the training library get in)
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

Not done yet: **code signing** (needs a code-signing certificate; until then Windows SmartScreen warns on
first run of the installer) and the auto-updater. Licensing of the bundled components is in
`THIRD_PARTY_NOTICES.md` (PyMuPDF is AGPL, mobi is GPL); the installer's licence page shows `LICENSE`.

## Status

MewBook **1.0.0** is feature-complete for its first release; over a thousand tests run with `uv run pytest`,
plus manual checks of the real window on Windows. What is in each release is in `CHANGELOG.md`; what comes next
(open-source preparation, operations, device transfer, conversion, i18n) is planned in
`docs/handoff/04_IMPLEMENTATION_PLAN.md`.

What works: point the app at a folder (File → Thêm thư mục...) and it watches and bulk-scans it, extracts
metadata, cover and text from PDF and EPUB, indexes into SQLite FTS5 and shows the library as a grid or list with
debounced search, sorting, a cover-size slider and pagination. Around that: an "Đang lọc" filter bar with facet
sidebar (hashtag / author / format, live counts) and saved collections, in-app reading of PDF, EPUB and Kindle
files (through the `mobi` package), a right-click menu (open, reveal in Explorer, edit metadata, bulk edit,
send to an e-reader folder, remove from library), a duplicate finder, a Calibre library importer, smart
classification (a bundled model, run in a background process), metadata lookup and cover search (Open Library,
Google Books, Apple Books, optional Google Images; each source can be switched off), AI summaries with the
user's own key, anonymous community reviews (`docs/adr/0001-cloud-review-backend.md`), several themes,
crash logs and a Windows installer.

Known limitations: metadata and covers of real MOBI/AZW3 files are not parsed yet (the extractor expects a zip
container and falls back to the file name); collections created in the UI have a single condition (the domain
layer already supports AND/OR); the list view has no grouping; Calibre tags and ratings are not carried over; the
installer is **not code-signed** (Windows SmartScreen warns on first run) and there is no auto-updater yet.

Content hashing for duplicate detection needed a schema change (`content_hash` column);
`DatabaseManager.initialize_tables()` migrates an older `library.db` in place (`ALTER TABLE ... ADD COLUMN`)
rather than assuming a fresh database. Only ever append columns; see CLAUDE.md.

Community reviews go through a Supabase project you run yourself (Settings → Đánh giá cộng đồng); the app works
without it. Since 1.0.0 every installation has an anonymous identity (`core/user_identity.py`) and reviews are
written only through the server-side `submit_review` function (`src/smartdoc/application/sql/001_reviewer_identity.sql`,
copyable from Settings → "Sao chép SQL nâng cấp"). Reviews stay public and anonymous.

## License

MewBook is free software: you can redistribute it and/or modify it under the terms of the GNU Affero General
Public License, version 3 or (at your option) any later version (`AGPL-3.0-or-later`, see `LICENSE`). It is
distributed in the hope that it will be useful, but **without any warranty**. Third-party components and their
licences are listed in `THIRD_PARTY_NOTICES.md`; the audit is in `docs/legal/LICENSE_INVENTORY.md`. New source
files follow `docs/legal/SPDX_POLICY.md`.
