# Changelog

Chronological, human-readable history of what changed and why — kept so
the whole project can be understood as one coherent story, not just a pile
of commits. Newest entries at the top. Each entry links the commit(s) it
corresponds to.

## 2026-09-17 — Send files to a USB-connected e-reader

- New "📱 Gửi tới máy đọc sách..." action in the File menu and both
  right-click context menus (single/multi-selection), and
  `FileActionEngine.send_to_ereader()`: copies the selected documents'
  files into the e-reader's book folder. An e-reader connected over USB
  just mounts as a normal folder on Windows, so this is a real
  `shutil.copy2` onto that folder -- unlike the library's own storage,
  which never copies/moves the user's files, this one's whole point is
  putting a copy on the external device. Supports selecting and sending
  many files at once, and can be run repeatedly.
  - If no folder has been set up yet (or the previously remembered one
    no longer exists -- e.g. a different device is plugged in now),
    prompts with a folder picker and remembers the choice
    (`AppConfig.ereader_folder_path`) for next time, no need to
    re-select on every send.
  - The remembered folder can also be reviewed/changed any time from
    Settings -> "Quản lý File" (previously only watch folders lived
    there).

## 2026-09-17 — Edit menu: clear selection, edit, delete, copy/cut/paste files

The Edit menu only had "Select all" -- everything else (edit, delete,
copy/cut/paste files) required the right-click context menu, and even
there, copy/cut/paste of the underlying files wasn't offered at all.

- New `presentation/clipboard_files.py`: `set_clipboard_files(paths,
  cut=...)` / `get_clipboard_file_paths()` put/read real file references
  on the OS clipboard, using the same "Preferred DropEffect" marker
  Windows Explorer itself uses to distinguish copy from cut -- so a
  library file copied here can be pasted straight into Explorer (or
  anywhere else that accepts file drops), and files cut/copied in
  Explorer can be pasted into the library. This app still never
  copies/moves files on its own storage -- copy/cut only ever place
  references on the clipboard, paste only ever imports/indexes.
- `LibraryListWidget` gained `clear_selection()`, `edit_selected()`,
  `delete_selected()`, `copy_selected()`, `cut_selected()`, and
  `paste_files()` (the last needs the app's `import_manager`, now passed
  through from `MainWindow`). `_show_single_document_menu` /
  `_show_multi_document_menu`'s edit/delete logic was factored into
  shared `_edit_documents()` / `_delete_documents_with_confirm()` helpers
  so the Edit menu and the right-click menu can't drift apart.
- Both context menus gained "📋 Sao chép" / "✂️ Cắt" actions alongside the
  new Edit menu entries (Ctrl+C/Ctrl+X/Ctrl+V, Del, Ctrl+Shift+A for
  clear selection).

## 2026-09-17 — File-type badge, panel refresh button, clearer dividers/action colors

- **Grid view covers gained a file-type badge** ("PDF"/"EPUB") stamped at
  the bottom-right corner -- small, semi-transparent dark background so it
  reads over any cover art without dominating it. Composed directly onto
  the cached icon (`LibraryModel._icon_cache` is now keyed by
  `(cover_path, extension)`, not just `cover_path`, since the badge is
  part of the pixmap itself). List view is untouched -- it already shows
  format as its own column, not an icon.
- **Detail panel gained a 🔄 refresh button** in a new header row, to
  manually re-fetch the current document (same logic the panel already
  used automatically on `LibraryUpdatedEvent`, now factored into one
  shared `_refresh_current_document()` both paths call).
- **More divider lines**: one between the cover/read/cover-search group
  and the editable title/author group, one between the tags group and AI
  Summary -- the panel previously had gaps between some sections but not
  others.
- **Action vs. status color distinction**: `rating_label` and `path_label`
  (both clickable) now use the theme's accent color, matching the
  already-accent-colored cover-search and AI-summary links -- previously
  they were plain text, indistinguishable from the genuinely read-only
  `format_size_label`/`date_added_label`/`date_modified_label`.

## 2026-09-17 — In-app EPUB reading (not just PDF)

The reader window's non-PDF fallback ("open with the OS's own app") was
reported as a bug, not accepted as a known limitation -- fair, since
EPUB is one of this app's two real formats.

- New `infrastructure/epub_reader.py`: `EpubDocument` opens an EPUB and
  exposes its chapters *in spine order* (the OPF's `<spine>` lists
  `<itemref idref="...">` pointing at `<item>` entries in the
  `<manifest>` -- reading order is not just alphabetical filenames, and a
  test specifically constructs a manifest/spine that disagree in order to
  prove this is respected). Raises `EpubReadError` on a corrupt zip,
  missing OPF, or missing manifest/spine, so the reader window can fall
  back cleanly instead of crashing.
- `ReaderWindow` gained an EPUB path: chapters render in a `QTextBrowser`
  (a `_EpubTextBrowser` subclass overrides `loadResource()` to pull
  `<img>` bytes straight out of the zip, since the browser has no idea
  those relative paths live inside an archive) with prev/next chapter,
  a chapter-number jump box, font zoom in/out (reusing `QTextEdit`'s own
  `zoomIn`/`zoomOut`), and fullscreen -- the same control shape as the
  PDF reader, just chapter-granularity instead of page-granularity.
  A corrupt/unparseable EPUB falls back to the existing "open externally"
  message rather than a broken viewer. AZW3/MOBI still fall back too --
  they aren't real zip/OPF containers (see import_queue.py's own
  known-limitations note), so there's nothing here to read yet regardless.
- The open zip handle is closed in `closeEvent`, verified by a test that
  the handle actually becomes unusable after the window closes (not just
  that no exception occurred).

## 2026-09-17 — Fix cover search rate-limiting

Reproduced live: searching a real Vietnamese title ("Đắc Nhân Tâm") returns
zero Open Library results (confirmed separately, matches the earlier
"weak non-English coverage" finding) and hits `429 Too Many Requests` from
Google Books' public, unauthenticated search endpoint -- both sources are
free/keyless and rate-limited per IP, and Open Library's poor Vietnamese
coverage means nearly every search for this app's actual target audience
falls entirely onto Google Books, which trips that limit faster than an
English-heavy workload would. Added a short retry-with-backoff (up to 2
retries) for 429s on every network call in `cover_search.py`, and a
clearer message ("đang bị giới hạn tốc độ truy vấn, hãy thử lại sau ít
phút") when retries are exhausted, instead of a raw HTTP error that reads
as "broken."

## 2026-09-17 — Fix search, "All" filter priority, and hashtag-click focus jump

Three real bugs from a new report, root-caused by actually reproducing
each one (live scripted Qt interaction, not just re-reading the code):

- **Search "didn't work"**: reproduced by literally trying the omnibar's
  own placeholder text, "author:nam python". `DatabaseManager._sanitize_query`
  was stripping the `:` as an "unsafe" character before the query ever
  reached FTS5 -- but `field:term` is real, native FTS5 syntax (confirmed
  directly against SQLite) and the omnibar was advertising it as valid
  input the whole time. Fixed by recognizing a token shaped like
  `title:`/`author:`/`tags:`/`content:` + a term (a fixed whitelist, so
  nothing else can smuggle syntax into the MATCH expression) and preserving
  it as a column-filtered prefix match instead of sanitizing it into
  garbage.
- **"Tất cả tài liệu" not taking priority**: clicking it only cleared the
  selected collection while any active format/author/hashtag facet filter
  stayed combined in via AND, so "All" could still show a filtered view.
  Sidebar now also publishes an empty `FacetFilterChangedEvent()` when
  "Tất cả tài liệu" is clicked (selecting a *real* collection still
  correctly leaves facets combined in, per a new regression test for that
  case specifically).
- **Hashtag click visually "jumping" to Tác giả**: reproduced with a real
  simulated `QTest.mouseClick` on a hashtag item. The Faceted Filter
  Panel's tree items were natively selectable, and since every click
  rebuilds the whole tree (destroying and recreating every item to
  refresh counts/highlighting), Qt had nothing to keep as its own
  "current item" afterward and would auto-focus something -- typically
  the first selectable leaf, in Định dạng or Tác giả -- which is what
  looked like the click "jumping" there, even though the panel's own
  color-based selection state was correct the whole time. Fixed by
  turning off native selection entirely (`NoSelection` + non-selectable
  items) -- `itemClicked` still fires on click regardless of
  selectability, confirmed via the same live click simulation
  (`tree.currentItem()` is now `None` after a click, nothing left for Qt
  to auto-focus).

## 2026-09-17 — Separate "content font" from the app's own font

Settings gained a new "🔤 Font nội dung" tab, deliberately separate from
"🎨 Giao diện" -- per explicit request to split "cấu hình giao diện font
chữ, kiểu chữ, cỡ chữ, màu chữ của nội dung" (the content's font/style/
size/color) from "cấu hình của ứng dụng" (the app's own configuration).
"Giao diện" keeps Theme + the app's chrome font (menus/buttons/dialogs,
unchanged from before); the new tab has its own font family (QFontComboBox),
size, and a text color picker (QColorDialog + swatch, with a "Mặc định"
button to fall back to the current theme's own text color) -- three new
`AppConfig` fields: `content_font_family`, `content_font_size` (default
13), `content_text_color`.

Applied to document-content text specifically, not the whole app:
- **Library grid/list**: `LibraryModel`/`LibraryTableModel` now take an
  optional `context` and answer `Qt.FontRole`/`Qt.ForegroundRole` from it
  for title/author text (grid) and every cell (list) -- the idiomatic Qt
  way to give a model's items their own font/color without a custom
  delegate.
- **Document Detail Panel**: title/author now use the content font/size/
  color instead of the fixed 16px/13px baked into the old stylesheet.
  Hashtags follow the content font *size* too but keep the theme's accent
  *color* -- deliberately not `content_text_color`, so a tag still reads
  as a clickable link rather than as body text.

Like theme/app-font, these apply after Settings closes via the same
`appearance_changed` → MainWindow-rebuild path already in place (see the
"Live-apply Settings" entry above) -- not live mid-session, since the
values are baked into stylesheet strings at widget-construction time.

## 2026-09-17 — Collections: dedupe + counts; Faceted filters: click-based + Hashtag category

- **Collections:** creating one with a name that already exists (case/
  whitespace-insensitive) is now rejected with a warning instead of
  silently creating a second entry with the same name. The sidebar list
  now shows each collection's document count next to its name
  ("PDFs (12)"), including "Tất cả tài liệu" -- backed by the
  `count_documents_in_collection()`/`count_documents()` already added
  earlier. Reloading (e.g. on every `LibraryUpdatedEvent`, now subscribed
  to for live counts) preserves whichever collection was selected instead
  of snapping back to "Tất cả tài liệu" every time a document changes --
  incidentally also fixed that same reset happening after a rename, which
  was a latent bug from before this entry.
- **Faceted Filter Panel redesigned**: checkboxes replaced with
  click-to-select (click an option to filter by just that one; click it
  again to clear; clicking a different option in the same category
  switches to it) per explicit request to simplify the interaction. Gained
  a third category, "Hashtag" -- every distinct tag in the library,
  auto-populated with live counts via new `DatabaseManager.count_by_tag()`
  (tags are one comma-joined string per document, so this splits/
  aggregates in Python; SQLite has no clean way to explode a delimited
  column). The panel now also *subscribes* to `FacetFilterChangedEvent`
  (previously only published it), so a tag filter set from elsewhere (the
  detail panel, below) shows up as selected here too.
  - Found and fixed a real re-entrancy bug while building this: publishing
    an event the same panel also subscribes to, then rebuilding the tree
    (`clear()` + repopulate) from inside that subscription handler, was
    happening *while still inside the click handler that triggered it* --
    deleting the very `QTreeWidgetItem` the click handler was still
    holding a reference to (`RuntimeError: already deleted`). Fixed with a
    re-entrancy guard so the panel's own publish doesn't also trigger a
    second, nested rebuild.
- **Document Detail Panel**: "Thể loại" section renamed to "Hashtag";
  each tag now renders as plain clickable "#text" (no background/border --
  explicit request that chip styling was too heavy for quick scanning).
  Clicking one resets the collection selection to "Tất cả tài liệu" and
  filters the library to every document sharing that tag -- "equivalent
  to selecting it on the collection side," per the request -- via the same
  `FacetFilterChangedEvent(tags=...)` the sidebar's own Hashtag category
  uses, so both entry points feed the exact same filtering code path.

## 2026-09-17 — Fix Gemini 404, part 2: gemini-2.0-flash was fully retired

The header fix (previous entry) wasn't the whole story -- confirmed live
against the real API that `gemini-2.0-flash` itself now 404s regardless of
auth, because Google fully shut it down June 1, 2026 (not a soft
deprecation). Google's model lineup has moved fast this year
(2.0 → 2.5 → 3.5 → 3.8 within months), so this will very likely need
bumping again -- updated `_GEMINI_MODEL` to `gemini-3.8-flash` (the
current GA flash model) and left a comment pointing at
ai.google.dev/gemini-api/docs/models as the place to check next time.
Verified live: a garbage key against this model now gets a proper "API
key not valid" (400) instead of "Not Found" (404), confirming the model
itself is routable.

## 2026-09-17 — Fix Gemini 404 for Google's newer "AQ." API key format

Real bug hit immediately after shipping the connection-test feature: a
freshly-created Gemini key produced `404 Not Found` on
`generativelanguage.googleapis.com/v1beta/models/gemini-2.0-flash:generateContent`.

Root cause (confirmed via web search against matching reports from other
projects hitting the identical error): Google now issues API keys in a
newer format with an `AQ.` prefix by default (the older `AIzaSy…` format
still exists for old keys), and `AQ.`-format keys are only recognized via
the `x-goog-api-key` HTTP header -- sent the old way, as a `?key=` query
parameter, the request 404s instead of failing auth, which reads like a
broken endpoint/model name rather than what it actually is. Switched
`_call_gemini` to send the key via that header (works for both key
formats). OpenAI and Anthropic were unaffected -- both already used an
auth header, never a query param.

## 2026-09-17 — AI Summary follow-ups: setup guide, connection test, uncapped content

- **Settings' "AI Tóm tắt" tab gained a setup guide and a connection
  test.** Each provider now shows where to get a key (Google AI Studio /
  OpenAI platform / Anthropic console -- `application/ai_summary.PROVIDER_GUIDES`),
  updated live as the dropdown changes. A new "🔌 Kiểm tra kết nối" button
  makes a real minimal request with the entered key on a background
  thread and reports success/failure in place -- on failure, that
  provider's setup guide is appended to the error so a bad/missing key
  comes with a way to actually fix it, not just an error string.
- **AI Summary dialog now shows the request content, uncapped.** An
  earlier version capped extracted text at 6000 characters before sending
  it to the model; removed entirely per explicit request -- a partial
  excerpt cut off mid-paragraph produced less natural summaries. The full
  request text (title/author/tags + whatever was extracted) is now shown
  in its own editable box above the summary, so what's being sent is
  visible rather than a hidden implementation detail, and can be edited
  before generating. `generate_summary()` split into
  `build_request_content()` (exposed for the UI) and
  `generate_summary_from_content()` (takes the, possibly user-edited,
  text directly); `generate_summary()` itself is now a thin convenience
  wrapper over both. Already-saved summaries still display immediately on
  open, unchanged from before.

## 2026-09-17 — AI Summary (non-spoiler book overview, user's own API key)

The last item from this round of requests: TDD-016-style AI summaries,
but never implemented until now.

- **`application/ai_summary.py`**: generates a short (~100-150 word),
  Vietnamese, *non-spoiler* summary -- genre, tone, themes, who it's for
  -- explicitly instructed never to reveal plot, twists, or the ending.
  Calls whichever provider the user configured with their *own* API key
  (Google Gemini, OpenAI, or Anthropic Claude -- picked as the three most
  recognizable options rather than a generic "custom endpoint" field this
  app would have a much harder time getting right/secure). Uses the
  document's title/author/tags plus up to 6000 characters of extracted
  text when available (PDFs only today -- EPUB/AZW3/MOBI don't have body
  text extracted yet, so their summaries lean on title/author/tags alone;
  the prompt says so explicitly rather than pretending otherwise).
- **Settings gained an "AI Tóm tắt" tab**: provider dropdown + API key
  field (password-masked with a show/hide toggle). Applied live like
  everything else in Settings now -- no restart.
- **`presentation/ai_summary_dialog.py`**: generating and saving are
  separate, deliberate steps -- a fresh generation is only a preview
  (`DatabaseManager.ai_summary` column untouched) until the user reviews
  it and clicks "Lưu tóm tắt". New `DatabaseManager.update_ai_summary()`.
  Opened from the Document Detail Panel (a "✨ Tạo tóm tắt AI" / "🔄 Tạo lại
  tóm tắt AI" link, depending on whether one already exists) and the
  library view's right-click menu.
- Status bar's AI connection indicator (added in the previous entry) now
  reflects real configuration state end to end.

## 2026-09-17 — New app icon/brand mark, icon pass across the UI

- **Replaced the app icon** with the user-supplied brand mark (a cat
  reading a book) in place of the earlier programmatically-drawn
  document+magnifying-glass icon. The source export had the squircle
  centered on a canvas much wider than tall, with the "transparent" area
  baked in as an opaque checkerboard rather than real alpha, so a plain
  alpha-bbox crop wouldn't isolate it -- `packaging/process_brand_icon.py`
  finds the squircle's true bounding square via color saturation (the
  gradient border/cat are saturated, the checkerboard and white book pages
  aren't), crops to it, and stamps a clean rounded-rect alpha mask over the
  result so the corners are properly transparent regardless of whatever
  was sitting there in the source. Produces `app_icon.ico` (multi-res) and
  a `brand_logo.png` for in-UI use; both added to the PyInstaller spec's
  `datas`. `generate_icon.py` is kept as a fallback/reference, not deleted.
- **Brand header in the sidebar**: the logo + "SmartDoc Library" above the
  collections list.
- **Icon pass**: emoji icons added to the main menu bar (File/Edit/View/
  Tools), Settings' tab titles, and the Duplicate Finder's buttons, for a
  livelier/friendlier feel per the request -- left the rest of the UI
  alone rather than a wall-to-wall icon sweep, since it's a lower-priority
  polish item relative to the rest of this batch.

## 2026-09-17 — Live-apply Settings, bottom status bar, double-click reads, #tag, cover search fix

Second review pass over the same checklist's follow-up requests.

- **Cover Image Search actually finding results:** the earlier version only
  queried Open Library, whose catalog skews heavily English/Western --
  a Vietnamese-language book (this app's whole UI is Vietnamese, so
  presumably its main use case) would very often get zero matches, which
  looked like "search doesn't work" even though nothing was broken. Now
  also queries Google Books' public API and tops up the result list
  whenever Open Library alone comes back with fewer than the requested
  count (including zero) -- `CoverSearchResult` gained a `source` field so
  the UI shows which catalog each candidate came from.
- **Double-click now opens the in-app reader by default**, not the OS's
  own app -- "Mở bằng ứng dụng khác" (open with another app) moved to the
  right-click menu instead, next to "Đọc trong ứng dụng".
- **Detail panel tags are now hashtag-styled** ("#Python" instead of
  "Python") in both the display badges and the edit field's placeholder.
- **Settings no longer needs an app restart for anything:**
  - Worker thread count and the file-watcher debounce now apply live via
    new `ImportQueueManager.restart()` / `LibraryWatcher.set_debounce_seconds()`
    methods.
  - Theme and font can't be live-restyled onto already-built widgets that
    baked their colors into a stylesheet string at construction time --
    rather than a sprawling "every widget re-subscribes to a
    theme-changed event" refactor, `SettingsDialog` now just flags
    `appearance_changed`, and `MainWindow` rebuilds itself in place (same
    `AppContext`/watcher/import_manager, so no backend state or queued
    work is lost) once Settings closes. See `app.py`'s
    `on_appearance_changed`.
  - The file-watcher debounce no longer has a meaningfully low cap
    (0.5s–30s before, now 0.5s–86400s).
- **Bottom status bar** (`presentation/status_bar_panel.py`, a real
  `QStatusBar`): total documents + how many have complete vs. incomplete
  metadata, the current collection's document count (when one is
  selected), how many folders are being watched, Cloud Review / AI Summary
  connection status, and an "anhtiensinh" author credit. Refreshes on the
  same `LibraryUpdatedEvent`/`CollectionSelectedEvent` the library view
  itself reacts to. New `DatabaseManager.count_metadata_completeness()`
  and `.count_documents_in_collection()`; the latter's "(rule match) OR
  (manually added)" logic was factored out of `library_view.py` into
  `DatabaseManager.collection_where_fragment()` so the status bar's count
  and the library view's actual filtering can never drift apart.
- Re-verified (not just re-read) the reveal-in-Explorer fix from the
  previous entry against a real file on this machine -- the command runs
  without error and launches Explorer, though without a way to visually
  confirm the correct item gets highlighted, this is as far as it can be
  confirmed here.

## 2026-09-17 — Edit an existing Collection's rule, not just its name

`NewCollectionDialog` now doubles as an edit dialog: passing it an existing
`VirtualCollection` pre-fills the name/field/value and saving upserts the
same collection id instead of creating a new one. Wired into the sidebar's
right-click menu as "Chỉnh sửa điều kiện", alongside the rename/delete
added earlier today -- closes the gap between "đổi tên" (rename, already
covered) and "chỉnh sửa" (edit the actual rule), which the request listed
as two separate asks.

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
