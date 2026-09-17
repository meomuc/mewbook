# Changelog

Chronological, human-readable history of what changed and why — kept so
the whole project can be understood as one coherent story, not just a pile
of commits. Newest entries at the top. Each entry links the commit(s) it
corresponds to.

## 2026-09-17 — Milestones A–E (Windows Phase 1) + Cloud Review System

**Commits:** `f50c766` → `2b7b51f`

Built SmartDoc Library from an empty repo to a working, packaged Windows
desktop app: PySide6 + SQLite FTS5, Clean Architecture (`core` / `domain` /
`infrastructure` / `application` / `presentation`).

- **Milestone A** — ingest pipeline: `DatabaseManager` (SQLite FTS5 with
  triggers keeping the virtual table in sync), PDF extractor (PyMuPDF),
  EPUB extractor (stdlib `zipfile` + `xml.etree`, no third-party EPUB
  library needed), cover cache, file watcher (debounced, so a
  still-copying file isn't read mid-write), background import queue,
  `AppContext` + `EventBus` as the integration backbone every later module
  plugs into.
- **Milestone B** — first usable UI: main window, debounced Omnibar
  search, grid view (Qt Model/View, so the widget cost stays flat
  regardless of library size), file actions (open / reveal in Explorer).
- **Milestone C** — Faceted Filter Panel (by format/author, with live
  counts) and Virtual Collections (saved rule-based filters, e.g.
  `extension = pdf`) in the sidebar.
- **Milestone D** — Metadata Editor + Bulk Editor, full menu bar
  (File/Edit/View/Tools) and toolbar (sort + cover-size slider),
  pagination, a Settings dialog (file types, watch folders, theme, worker
  threads), Duplicate Finder (exact content-hash matches + fuzzy
  title/author matches), and a Calibre library importer.
- **Milestone E (packaging)** — PyInstaller build, verified as a
  standalone `.exe` that runs without the dev venv; a custom app icon
  (document + magnifying glass, drawn programmatically in the app's own
  theme colors); `run.bat` as a double-click launcher.
- **Cloud Review System (TDD-016)** — anonymous star-rating + comment
  reviews. Went through two failed backend designs before landing on a
  working one:
  1. *Google Drive* (the original spec): doesn't work at all — Google has
     removed personal storage quota for service accounts, so they can't
     create files even in a folder explicitly shared with them as Editor.
  2. *Firestore*: should have avoided that wall, but every access path
     (hand-rolled REST, the official Admin SDK, an Editor IAM role, the
     broadest OAuth scope, a fresh database, several minutes of
     propagation wait) hit an identical, unexplained 403 — something at
     the Google Cloud project/org-policy level neither the user nor
     Claude could see or fix from outside the console.
  3. *Supabase* (final, working): a `reviews` table via Supabase's
     auto-generated REST API, called with plain `requests`. Verified
     against a real project end to end. Turned out to be a better fit,
     not just a workaround — Supabase's "anon" key is *designed* to be
     public and embedded in client apps, with access enforced by Postgres
     Row Level Security policies, unlike a Google service account key
     (which the app would otherwise have had to protect as a secret while
     shipping it to every install anyway).

**Real bugs found and fixed along the way** (each one caught by actually
running the app or a live integration test, not just unit tests in
isolation):
- The original spec's FTS5 schema was invalid SQLite (`content_rowid` must
  be an integer column; document IDs are MD5 hex strings) — redesigned
  with a separate `doc_rowid` integer key.
- Metadata title fallback used the full file path instead of just the
  filename when extraction failed.
- A cross-thread Qt safety violation: background import/watcher threads
  publish events that UI widgets were reacting to directly, which can
  crash Qt. Fixed with `QtEventBridge`, now the standard pattern for every
  presentation widget that subscribes to the event bus.
- Windows dark mode made text unreadable in several widgets (a stylesheet
  set `background` without also setting `color`) — fixed by forcing one
  explicit theme app-wide instead of per-widget patches.
- PDF import was 3x slower than necessary — `PdfExtractor` opened the same
  file separately for metadata, cover, and text; merged into one
  `extract_all()` that reuses a single open document.
- Bulk imports caused UI thrashing — one `LibraryUpdatedEvent` per
  document was triggering a full grid reset each time; debounced into one
  reload per burst, plus caching decoded cover icons.
- A stale/null config value made `CoverCacheManager` fall back to a bare
  relative `"covers"` path, which wrote ~650 cache files and a 12MB
  `library.db` directly into the project's source tree instead of
  `%APPDATA%`. Fixed the fallback to always resolve to an absolute path.

## What's next

See the "Not yet implemented" list in `README.md`'s Status section for the
standing backlog. New work in progress: list view columns + alignment,
sort by highest-rated (Supabase-backed), a document detail/edit side
panel, drag-and-drop import, an in-app reader, cover image search, and an
AI-generated non-spoiler book summary (Google Gemini).
