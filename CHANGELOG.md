# Changelog

Chronological, human-readable history of what changed and why — kept so
the whole project can be understood as one coherent story, not just a pile
of commits. Newest entries at the top. Each entry links the commit(s) it
corresponds to.

## 2026-09-17 — In-app Document Reader window

- **Reader window (`presentation/reader_window.py`):** a separate,
  independent top-level window (not modal -- the library stays usable
  while reading) with the common PDF-viewing controls: previous/next page,
  a page-number jump box, zoom in/out, fit-width/fit-page, and fullscreen
  (F11). Built on Qt's own `QtPdf`/`QtPdfWidgets` modules, which ship as
  part of the existing `pyside6` dependency (no new package needed).
  EPUB/AZW3/MOBI (and any PDF that fails to load) fall back to a plain
  message + "Mở bằng ứng dụng khác" button rather than a half-working
  embedded viewer -- Qt has no first-party EPUB rendering widget, and this
  app's EPUB extractor only pulls metadata/cover today, not body text (see
  `import_queue.py`'s known-limitations note), so there is nothing to
  render for those formats yet regardless. Opened from the Document Detail
  Panel (click the cover) and the library grid/list's right-click menu
  ("Đọc trong ứng dụng").
- Not yet re-verified against a fresh PyInstaller build -- QtPdf is a
  separate Qt module from the widgets already bundled, and while PyInstaller
  should pick it up automatically from the plain `import` statements (same
  mechanism as every other PySide6 submodule this app already uses), that
  should be confirmed the next time `packaging/SmartDocLibrary.spec` is
  built.

## 2026-09-17 — Cover Image Search (Open Library)

- **Cover Image Search:** search Open Library's public search API
  (`openlibrary.org/search.json`, no API key needed) by title + author,
  preview thumbnail candidates (with publish year), and pick one to replace
  a document's cover. Reuses the existing `CoverCacheManager` to save the
  picked image, so it's automatically resized to the library's standard
  300px width and re-encoded as WEBP -- "quality phù hợp, tối ưu dung
  lượng" (appropriate quality, optimized storage) came for free instead of
  needing its own resize/compress logic. Available from the Document Detail
  Panel ("🔍 Tìm ảnh bìa..." under the cover) and the library grid/list's
  right-click menu. New `DatabaseManager.update_document_cover()` for
  replacing just the cover path without touching other metadata.

## 2026-09-17 — Duplicate Finder redesign + Settings expansion (font/threads/scan timing)

- **Duplicate Finder:** both tabs (exact/fuzzy) gained a "Ngày thêm" (date
  added) column; all columns are now clickable-header-sortable
  (`QTableWidget` native sorting, with a small custom item so the date
  column sorts by timestamp rather than as text), defaulting to sorted by
  the first column. A new "Chọn file trùng ▾" button auto-checks every
  document in each duplicate group except the one to keep -- newest-added
  by default, or oldest-added -- and colors the rows marked for deletion so
  they're visually distinct from the kept one. The old single-purpose
  "Xóa các mục đã chọn khỏi thư viện" button became "Xóa file ▾" with an
  explicit 3-way choice (library only / library + original file on disk /
  cancel) instead of always doing the same thing.
- **Settings — Giao diện tab:** added font family (`QFontComboBox`) and
  size pickers, applied at startup via `QApplication.setFont()`
  (`AppConfig.font_family`/`font_size` already existed but nothing read
  them until now).
- **Settings — Hiệu năng tab:** now shows currently-running worker threads
  alongside available CPU cores, and a new field for the file-watcher's
  scan debounce (`AppConfig.watch_debounce_seconds`) -- the first
  "configure a max/timing parameter beyond the shipped default" control,
  per the request to allow this generally.

## 2026-09-17 — Import dedup/summary, manual Collections, detail panel inline edit, bug fixes

A review pass against a large user checklist covering the list view,
file/collection management, and known bugs. This entry covers the first
batch (bug fixes + the import/collections gap); Duplicate Finder redesign,
Settings expansion, cover search, and the in-app reader follow in later
entries the same day.

- **Reveal-in-Explorer bug fixed:** `explorer /select,"path"` was being
  built as a Python argument *list*, which `subprocess` auto-quotes as
  `"/select,<path>"` (quoting the whole token, not just the path) whenever
  the path contains a space -- Explorer doesn't parse that and silently
  falls back to its default folder (Documents/Quick access), which is
  exactly the reported symptom. Fixed by passing one pre-built command
  string with only the path quoted (still no shell involved, so this isn't
  a `shell=True` injection risk). Also now falls back to opening the
  file's parent folder if the recorded path no longer exists, instead of
  Explorer's confusing silent default.
- **Duplicate-on-import detection + a result summary:** re-scanning a
  folder (or re-adding a file) no longer silently re-extracts and
  re-writes a file that's already indexed by path. `ImportQueueManager`
  now tracks each user-initiated batch (folder scan, multi-file add, a
  drag-and-drop drop) and publishes one `ImportBatchCompletedEvent` with
  success/duplicate/failed counts once every file in that batch has been
  processed; the main window shows this as one summary dialog.
- **File menu: "Thêm file..." + drag-and-drop:** a multi-file picker
  action was added alongside the existing "Thêm thư mục...", and the main
  window now accepts files and folders dropped directly onto it.
- **Manual Collection membership:** Virtual Collections (TDD-009) were
  rule-only, so clicking one only ever showed rule matches and there was
  no way to manually curate one. Added a `collection_documents` table and
  `DatabaseManager` methods for it; a collection's filter is now
  `(rule match) OR (manually added)`, and an empty collection (no rule, no
  manual members) correctly shows zero documents instead of silently
  falling back to "no filter" (a latent bug that manual-only collections
  would otherwise have hit immediately). "Add to collection" is available
  from the library grid/list's right-click menu (single and multi-select).
  The sidebar's collection list also gained a right-click menu to rename
  or delete a collection.
- **Detail panel: inline editing, no button row.** The four action buttons
  (Open/Reveal/Edit/Review) are gone; the info rows are now the controls
  themselves -- click the cover to open the file, the file path to reveal
  it in Explorer, the rating to open the review dialog. Title, author, and
  tags are directly editable `QLineEdit`s that save on focus-out (these
  are the only three fields the app supports editing at all, so this
  fully replaces the old separate metadata-editor button for this panel).
- **Last-used directory remembered** for file/folder pickers (add file,
  add folder, Calibre import, Settings' watch-folder picker) via a new
  `AppConfig.last_used_directory`.
- **Configurable file-watcher debounce:** `watch_debounce_seconds` moved
  from a hardcoded constant into `AppConfig` (default unchanged: 1.5s).

## 2026-09-17 — List View QTableView + Document Detail Side Panel

**Commits:** `f1ee45c` → `db6b48f`

- **List View redesign:** replaced `QListView.ListMode` (still just one
  column of icon+text) with a proper `QTableView` + `LibraryTableModel`
  showing real columns: Title, Author, Tags, Average Rating, Review Count,
  Date Added, Date Modified. Grid and List now live in a `QStackedWidget`
  so switching mode is instant, with no widget teardown/rebuild. Right-click
  the table header to toggle which optional columns are visible (persisted
  in `AppConfig.visible_columns`). Grid alignment fixed: covers now snap to
  an even grid via `setUniformItemSizes(True)` + explicit `setGridSize()`,
  and long titles are truncated with "…" so one cell never expands and
  misaligns its neighbors.
- **Document Detail Side Panel:** a collapsible panel on the right side of
  the library showing cover art (280px), title, author, format + file size,
  dates, rating, file path, action buttons (open / reveal / edit / review),
  tags as colored badge chips, and AI summary (when available). Panel
  subscribes to the new `DocumentSelectedEvent` emitted by the library view
  whenever the user clicks a single document. Multi-select or deselect
  clears the panel. Toggle visibility via View → "Hiện/Ẩn Panel chi tiết";
  preference persisted in `AppConfig.show_detail_panel` (default: hidden).
  Panel also reacts to `LibraryUpdatedEvent` to auto-refresh after metadata
  edits without requiring a re-click.
- **Bug fix:** `Ctrl+A` select-all now targets the active view (grid or
  table) instead of hardcoding `list_view`.
- **Infrastructure:** added `DatabaseManager.get_document(doc_id)` for
  single-document lookup by ID.

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
