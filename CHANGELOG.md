# Changelog

All notable changes to MewBook ("Mèo Mực") are documented in this file.

The format is based on [Keep a Changelog 1.1.0](https://keepachangelog.com/en/1.1.0/),
and this project adheres to [Semantic Versioning 2.0.0](https://semver.org/spec/v2.0.0.html)
-- see "Versioning & releases" in README.md for how version numbers are chosen.

## [Unreleased]

New features, so the next release is a MINOR bump (1.1.0).

### Added
- **Cover dialog: paste an image link or choose an image from your computer.** Besides searching
  the internet, the cover dialog now has a box for an image URL (**"Tải về"**) and a
  **"Chọn ảnh từ máy..."** button. The image is checked (a real image, at most 15 MB), shown
  selected at the top of the results for a preview, and applied with "Dùng ảnh này" like any
  search result; searching again keeps it.
- **Filters redesigned: author, hashtag, format, collection and search now work as one.**
  - **"Đang lọc" bar** above the list shows every active filter as a chip you can remove
    (`Tác giả: Nhã Ca ✕`), how many books remain ("31 / 7.545 tài liệu"), **"Xóa lọc"**
    (clears everything, the search text included; also the Esc key in the list) and
    **"Lưu thành bộ sưu tập"** (keeps the current filter as a collection that updates itself
    when it can be expressed as rules, otherwise as a fixed list of the current books, and says
    which before saving). The author link and hashtags in the detail panel now show here too;
    before, the sidebar looked unfiltered while the list was filtered.
  - **One click = "show me this".** It switches that group to the clicked item and keeps the
    other groups, so filters narrow step by step. **Ctrl/Shift+click** (or "Thêm vào lựa chọn"
    in the right-click menu) adds to the selection; clicking the only selected item clears it.
    The double-click gesture is gone (it made the list reload twice and flicker).
    "Tất cả tài liệu" clears everything, search text included.
  - **Counts follow the filter.** Every number is "how many books if I pick this" given the
    other selections, and choices that would show nothing disappear, so a click in the sidebar
    can no longer lead to an empty list. Books without a hashtag get a **"Chưa phân loại"**
    entry.
  - **Authors, cleaned up on screen only** (no file or metadata is changed): spelling variants
    ("NHÃ CA", "Nhã Ca") are one person; a co-authored book ("A, B và C") counts for each of
    them, so the sidebar and the detail panel's author link give the same result; "Unknown",
    "nhiều tác giả" and similar are gathered into one "Không rõ / Nhiều tác giả" entry at the
    bottom. The list shows the top 8, and **"Xem tất cả …"** opens a searchable list of all.
    Renaming an author from the right-click menu now renames that person in every spelling
    and inside co-author lists.
  - **New sidebar section:** hashtags and formats are wrapping chips with counts, sections
    fold (and remember it), the "⋯" menu sorts and makes folders, and your existing folders
    show as 📂 chips that select all their members. The panel updates in place instead of
    rebuilding, so it no longer jumps or loses its scroll position.
  - **"Lọc nhanh" box** at the top of the sidebar, and suggestions under the main search
    box: type "nha" and get "Tác giả: Nhã Ca (12)", "Hashtag: …", collections and formats,
    accents and case ignored; Enter or a click turns it into a filter chip.
  - **"🧹 Gợi ý dọn tên tác giả"** (the "⋯" menu of the Tác giả section) suggests merging
    names that differ only by accents ("Nguyen Nhat Anh" / "Nguyễn Nhật Ánh") and flags
    usernames used as the author of many books ("CongThuc88", 369 books in a real library) so
    they can be set to "Không rõ". Nothing changes until you press the button and confirm, and
    only the library entries change, never the book files.
  - Collections made from a filter have several conditions, so "Chỉnh sửa điều kiện" is
    disabled for them (the one-rule dialog would flatten them); rename and delete still work.
- **Detail panel: author and "other books" on one line.** The author's name and the link to
  their other books are now a single line, "Tên tác giả (có 1 tài liệu cùng tác giả)"; the
  wording is shortened to fit a narrow panel, and the link moves under the name only when
  even the shortest form does not fit. The count no longer includes the book itself, and the
  link is hidden when the author has no other book. The author's name is also shown in full
  contrast and one size larger, instead of the muted caption grey.
- **Detail panel: page count, dates on one row.** The panel now shows the number of pages
  next to the format and size ("PDF · 1.9 MB · 320 trang"; an EPUB has no fixed pages, so
  its number is an estimate from the amount of text and is shown as "~412 trang"). Books
  imported earlier get theirs counted the first time they are selected, in the background
  (never for OneDrive files that are not downloaded yet). "Thêm" and "Sửa" dates now share
  one row; hover it for the exact time.
- **Metadata search (tìm metadata).** Right-click a book → "🔎 Tìm metadata..." (or
  "Tìm thông tin..." in the edit dialog) looks the book up, in this order: the
  book file itself, your own library (another copy of the same book), then the
  internet (Open Library, Google Books, Apple Books). Nothing changes until you
  review the differences and press "Áp dụng": only empty or placeholder fields
  are ticked for you, fields you typed by hand are never offered, and every
  change is recorded so "Hoàn tác" (undo) can take it back.
  - New book fields: publisher, publication year, language, ISBN, series and
    description (shown in the detail panel). The library upgrades in place.
  - **Optionally writes into the book file** (tick "Ghi vào file gốc", off by
    default; Settings → Quản lý File sets the default): EPUB takes all fields,
    PDF takes title and author. The file is backed up first, the new file is
    built beside it and checked before it replaces the original, and "Hoàn tác"
    restores the backup. MOBI/AZW3 and encrypted PDFs are never written.
  - Books get a `fingerprint` (a hash of the pages/chapters that does not change
    when metadata is written) so the same book is still recognised afterwards;
    books imported earlier get theirs in the background.
- **Smart classification and sorting (phân loại và sắp xếp thông minh).**
  Adds a category hashtag to each book and files it under a folder of the
  Hashtag tree in the sidebar, using a small offline model. Files are never
  moved, existing tags and your own folders are kept, and a run can be undone.
  - After files or folders are added, one compact popup with the import result
    asks whether to classify the new documents (ask / always / never, in
    Settings → Phân loại).
  - A "✨ Phân loại thông minh" button above the document list (also in the
    Tools menu and the right-click menu) applies to the list being viewed, as
    selected in the sidebar, and shows the document count first.
  - Reads the first 2,000 to 5,000 words of EPUB, PDF and MOBI books, plus title,
    author, tags, embedded subjects and chapter titles; Vietnamese is
    word-segmented with pyvi.
  - Runs in a separate low-priority process that only exists while classifying,
    and nothing is loaded at startup.
  - `train.py` trains and evaluates the model separately from the app; the app
    ships with a model trained on the author's library. New dependency: pyvi
    (brings scikit-learn, scipy and numpy, used only by the worker process and
    `train.py`; the Windows build grows accordingly).
- **Four "mood" themes** next to the original three, all in the same
  theme picker:
  - **Không Gian Chữa Lành** (Cottagecore): cream and sage colors, large
    rounded corners, a pill-shaped search box, warm soft cover shadows, a
    detail panel rounded on one side, a 🌿 brand mark, "Góc đọc sách"
    labels and a faint film-grain overlay.
  - **Hoài Niệm Kỹ Thuật Số** (Lo-Fi Retro-Tech): monospace everywhere
    (Consolas fallback), a fake old-OS title bar with three pastel dots,
    flat bordered pastel covers, neon glow on the selected cover,
    `// bộ_sưu_tập` code-style labels and `[ action ]` buttons.
  - **Japandi Tối Giản**: light sans-serif with wide letter spacing, flat
    earth-tone covers, no shadows or rounded buttons, text-link actions,
    a borderless sidebar, wide margins, and an asymmetric grid where the
    page's first book is shown large beside the others.
  - **Zen Dark Mode**: dark teal (not black) background, a soft turquoise
    glow on the selected cover and title, deep low-saturation covers, and
    slow (~500 ms) fades on hover and selection.
- **Theme previews:** the theme pickers (menu bar corner and Settings)
  show a small picture of each theme.
- **Theme style options** (`ThemeColors`): font stack and weight, letter
  spacing, corner radii, cover shadow, border, flat or gradient covers,
  selection style, action style, search style, title bar, grain overlay,
  motion and grid layout. Every default reproduces the original themes
  exactly, and every theme is validated automatically, including WCAG
  contrast and readable text on placeholder covers.

### Changed
- **MewBook is free software under the AGPL-3.0-or-later.** The repository now has a `LICENSE`
  (AGPL-3.0) and `pyproject.toml` declares it. Help → About states the licence and that there is
  no warranty, links to the source of the running version (once the public repository is set in
  `APP_SOURCE_URL_TEMPLATE`), and its legal page has three tabs: **Quyền riêng tư**,
  **AGPL-3.0-or-later** (the full text) and **Bên thứ ba** (third-party notices). The copyright
  line no longer says "Bảo lưu mọi quyền".
- **Installer and exe carry the licence.** The installer's licence page shows `LICENSE` instead
  of a generated EULA; `LICENSE`, `THIRD_PARTY_NOTICES.md` and every dependency's licence files
  (`*.dist-info`) are bundled with the app.
- **Sources can be switched off; Tiki and Apple Books are off by default.** Settings → Ảnh bìa has a checkbox for each
  keyless source (Open Library, Google Books, Apple Books, Tiki). A source that is off is never contacted,
  by cover search, its title-only fallback or metadata lookup, and searching with every source off says
  so instead of returning nothing. Tiki (an undocumented shop API with no published terms) and Apple Books (its terms only allow the
  artwork to promote the store) start off for everyone; tick them again to use them. Per-source terms: `docs/legal/DATA_SOURCES.md`.
- **Chính sách DRM** (`docs/legal/DRM_POLICY.md`): DRM is only ever detected to refuse a file, never removed.

- **Bundled classification model retrained without release-site boilerplate or rare names.** A word must now
  occur in at least 5 distinct books (10 if it only comes from titles, authors or tags), and website,
  social-media, e-mail and ebook-group boilerplate is excluded. Accuracy on held-out books is unchanged within
  run-to-run noise (70.3% vs 71.2%, precision 85.5%); the vocabulary shrank from 60,000 to 51,046 words. Your
  own trained model (`train.py`) is unaffected, except that the boilerplate list now applies to it too.

### Fixed
- **PDF reading is now serialised across import threads** (a lock around every PyMuPDF call), because MuPDF is
  not thread-safe and several import workers read PDFs at once. A precaution against rare native crashes during
  bulk imports; it was not proven to be the cause of the one crash seen in the tests.
- **Startup crash on a `settings.json` saved with a BOM** (Notepad and Windows PowerShell 5 add one),
  and **the library being created in the current folder when `settings.json` had no `db_path`**; it now
  falls back to the app data folder like a fresh install.
- **Freeze after selecting a book in the List view.** Painting a selected row raised an
  error on every repaint (`QPalette.Text` was read from an instance, where PySide6 has no
  such attribute), and the crash dialog opened from inside that paint, so each repaint
  stacked another dialog and the window went "Not Responding". The row now paints, and the
  crash dialog shows at most once at a time and only after the failing call has returned.
- A random test-suite crash (access violation) when leftover widgets were
  garbage-collected on an import worker thread. Widgets are now destroyed
  on the GUI thread after each test.
- The pagination "go to page" box was white with light text on dark
  content areas.
- **Cover search returned a jumble of unrelated covers**, and titles ran
  on without wrapping. Results now have to match the title (and author)
  at least 80%: subtitle and edition notes count as the same book,
  different books that merely share a word do not, and a matching title
  with the wrong author is dropped. Each result is a fixed cell with the
  title wrapped to three lines, then author, source and match score. A
  "Hiện cả kết quả khớp dưới 80%" checkbox brings back the weak matches
  for rare books.
- **Closing the app while it was busy showed a crash popup.** The window
  closed the database before the events its workers had just published were
  handled, so every widget that refreshed on them failed with "Cannot operate
  on a closed database". The database is now closed only after the event loop
  has ended. Closing while documents are being imported or smart
  classification is running now asks first ("Đang xử lý ... Bạn vẫn muốn
  thoát?"); saying no keeps everything running, saying yes stops the work
  and the window waits, with a busy cursor, until it has fully stopped.
- **Cover search missed books the catalogs do hold** (for example "Gia-Định
  Thành Thông-Chí"), for three reasons, each now fixed:
  - Hyphens and other punctuation in the title were sent to the catalogs
    as typed, so "Gia-Định Thành Thông-Chí" did not find "Gia Định thành
    thông chí". Queries are now cleaned first.
  - Google Books' free daily quota often runs out (error 429), which silenced
    the best source for Vietnamese books. Its keyless Atom feed, which draws
    on the same catalog and has no such quota, now takes over.
  - Tiki, a large Vietnamese bookshop, is now a source for Vietnamese titles,
    with high-resolution covers. At most three results come from any one
    source, so near-identical shop listings cannot crowd out the rest.
- **File-format label on covers** (PDF, EPUB...) moved to the bottom-right
  corner, drawn as solid letters with a thin contrasting outline at 7.5% of
  the cover's height, so it stays sharp on light and dark covers. Placeholder
  covers keep their title clear of it.
- **Changing the theme now changes the font too.** Every theme has its own
  typeface (the four that shared one serif font each got theirs), and a font
  saved in Settings earlier no longer sticks to the new theme: it is cleared
  on a theme change unless you pick a font in the same visit. The font boxes
  in Settings show the theme's font while no font is chosen.

## [1.0.0] - 2026-09-19

First release. From this version on, every release gets a
SemVer number (`src/smartdoc/__init__.py` is the single source of truth)
and an entry in this file.

### Added
- **Cover search: Apple Books source.** Free, keyless and stable; returns
  publisher artwork at 600px and covers many Vietnamese titles that Open
  Library/Google Books don't carry (the Vietnamese store is queried too
  when the title has Vietnamese diacritics).
- **Cover search: match ranking.** All sources are queried in parallel and
  every candidate is scored by title/author similarity (accent- and
  case-insensitive, subtitle-aware); the best match is shown first with
  its match percentage. Duplicates are dropped.
- **Cover search: download validation.** Each image is checked to decode
  as a real image of plausible cover size before it's offered, so broken
  links, HTML error pages and 1x1 placeholders never appear.
- **AI summary: 5 more providers** -- Groq, OpenRouter, Mistral (all with
  free tiers), DeepSeek, and **Ollama** (runs locally, free, no key, no
  data leaves the machine). A **Model** field in Settings overrides the
  provider's default model.
- **AI summary: summary options.** Choose the kind (non-spoiler intro, key
  points, full summary, review & audience, discussion questions), the
  length (short/medium/long) and the language (Vietnamese/English). The
  last choice is remembered.
- **Anonymous user identity.** On first run each installation generates a
  random secret identity, stored encrypted in `identity.dat`. It is used
  to own reviews and nicknames without any sign-up; uninstalling removes
  it, so a reinstall gets a new one. No personal data is involved.
- **Reviews: unique nicknames.** A nickname belongs to the first
  installation that used it; anyone else gets "nick name đã có người
  dùng". "Ẩn danh" stays shared.
- **Reviews: update or post new.** If you already reviewed a book,
  submitting asks whether to update your earlier review or post a new one.
- **Reviews: colored display.** Gold stars in the review list, an average
  rating summary at the top, your own reviews marked "Bạn", dates, and
  "(đã sửa)" on edited reviews.
- **Settings → Đánh giá cộng đồng: "Sao chép SQL nâng cấp"** copies the
  server upgrade script (`application/sql/001_reviewer_identity.sql`).
- **Crash reporting and logs.** Rotating log at
  `%APPDATA%\SmartDocLibrary\logs\mewbook.log`; uncaught errors are
  logged with a full traceback and shown as a friendly dialog.
- **Single instance.** Starting the app while it's already running shows a
  notice instead of opening a second copy on the same database.
- **About dialog:** version, copyright, anonymous install ID, "Sao chép
  thông tin hỗ trợ" and "Thư mục nhật ký".
- **Release packaging:** version resource embedded in `MewBook.exe`,
  Inno Setup installer script (`packaging/MewBook.iss`), one-command
  build (`packaging/build.ps1`), `THIRD_PARTY_NOTICES.md`.

### Changed
- **List view columns** now fill the table: Title stretches to take the
  remaining width, the other columns are sized to their content in the
  current font, numbers/dates are aligned, and long text is elided
  instead of wrapping.
- Cover search requests larger images (Open Library "-L", Google Books
  ~480px) so saved covers aren't upscaled from tiny thumbnails.
- Cover search retries 5xx errors as well as 429, honors `Retry-After`,
  stops retrying once a daily quota is exhausted, caches results for 30
  minutes and retries title-only when author-filtered results are few.
  Google Books uses your Google API key (Settings → Ảnh bìa) when one is
  set, giving it its own daily quota.
- Anthropic's default model is now `claude-haiku-4-5`.
- The reviewer nickname is only saved after the server accepts it.

### Security
- Reviews are written only through the server-side `submit_review`
  function, which derives the author from the installation's secret
  token, so authorship can't be forged and only the author can edit a
  review. **Server action required:** run the upgrade SQL (see above)
  -- until then, submitting shows instructions instead of posting.

## Pre-1.0 development history

Chronological notes kept during development, newest first. Not
versioned; kept so the project can be understood as one coherent story.

### 2026-09-18 — Walnut Library redesign to match the mockup

- **Header.** Filter chips are pills: the active one is solid accent,
  the others light grey. "Tất cả" shows its count on the chip; the other
  chips show theirs in a tooltip. A new "★ Sẽ đọc" chip shows only the
  reading list. There is a "＋ Thêm mới" button (opens the Add Document
  dialog), and the cover-size slider is hidden in this theme.
- **Sidebar.** The heading is "THƯ VIỆN" and the first row is "Tất cả".
  Rows are taller, with outline icons drawn per row (a box for "Tất cả", a
  folder for collections, a star for the reading list) in place of emoji.
  The selected row shows its count in a small tinted pill. Row text is
  plain "name (count)" in every theme now; the icons and pills are drawn
  by the delegate. In all themes, the collections list fits its rows
  instead of sitting in a scrolling box.
- **Grid.** Covers are 160px wide, and the gutter grows with the cover
  size. All themes use a paperback-like cover ratio of 1.42 (was 1.33).
  Placeholder covers are painted at 180px and scaled down, so their text
  stays sharp on large covers.
- **Action bar.** Spans the full window width along the bottom (under the
  sidebar too). Larger mini cover with a shadow, 16px title,
  "author · EPUB · size", and plain "Mở sách" (filled) / "Chỉnh sửa"
  (outlined) / "⋯" buttons without emoji.

### 2026-09-18 — Editorial Light redesign to match the mockup; theme names

- **Theme names.** "Tờ Báo Sáng" / "Kệ Sách Gỗ" / "Mực Đêm" are now shown as
  "Editorial Light" / "Walnut Library" / "Midnight Ink". The config keys
  (`broadsheet` / `woodshelf` / `inkynight`) are unchanged, so saved
  settings keep working.
- **Header bar.** Logo, name, search, grid/list toggle, sort and cover size
  now sit in one bar across the whole window (they used to be in the
  sidebar and above the grid). Search has a magnifier icon and flatter
  corners.
- **Book cards.** The grid is drawn by a card delegate: the cover with a
  soft shadow, cropped to one shape so rows line up; the title in two
  lines under it, the author muted below; when selected, an accent outline
  and accent text instead of a filled blue block.
- **Placeholder covers.** Covers without art now show the title and author
  on the cover, use richer colours, and have a thin spine band. Two bugs
  fixed: the spine was solid black because QColor can't parse CSS
  `rgba()`, and each book's colour changed between launches because
  `hash()` is salted per process (crc32 now). The format badge moved to
  the top-left corner so it doesn't cover the title.
- **Sidebar.** Section headings are small caps ("BỘ SƯU TẬP", "TÁC GIẢ"),
  counts are right-aligned and muted, and the selected row is a tinted
  band with an accent stripe (`presentation/sidebar_style.py`). The facet
  tree no longer shows expand arrows on its category roots.
- **Detail panel.** No "Chi tiết" header row (refresh is a small icon
  now). The cover has a drop shadow, the title is larger, and
  HASHTAG / TÓM TẮT AI use the same section headings.
- **Pagination.** Centred under the grid: flat arrows and one filled
  "Đến" button. Scrollbars across the window are thin, with no arrows.
- **Midnight Ink fix.** Text typed in the search box was dark on the dark
  header; it's light now.

### 2026-09-18 — Duplicate finder no longer freezes the app

- **Cause.** The fuzzy (similar title/author) tier compared every pair of
  documents with difflib -- O(n^2) -- inside the dialog's constructor on
  the GUI thread, after loading every row with `SELECT *` (full extracted
  text included). ~43 s at 1,600 documents, close to an hour at 15,000.
- **Fix.** `application/duplicate_finder.py` now normalises titles
  (case, Vietnamese diacritics, punctuation), finds candidate pairs through
  an inverted index of each title's rarest words (prefix filtering), and
  runs difflib's cheap upper bounds before the full ratio: 1,600 documents
  in ~50 ms with no pair missed versus the full comparison, 16,000 in ~3 s.
  Titles whose numbers differ ("Tập 4" / "Tập 5") are no longer flagged --
  they're different volumes, and the "select duplicates" button would have
  marked them for deletion. The dedup queries only read the columns shown.
- **Dialog.** Exact matches (one SQL query) appear immediately; the fuzzy
  scan runs on a background thread with a progress bar and is cancelled
  when the dialog closes. The worker never touches SQLite or a Qt object --
  rows are read on the GUI thread first and results are picked up by a
  timer owned by the dialog -- so closing mid-scan can't crash. Deleting
  files updates the lists in place instead of rescanning.

### 2026-09-18 — Faster loading, multi-select filters, facet groups, reading list, MOBI reading

- **Loading performance.** Measured on a 15,000-document library with real
  covers: opening the main window went from 420 ms to 115 ms, the GUI
  thread's work per page of covers from 186 ms to 6 ms, and 50 back-to-back
  import events from 820 ms to 32 ms. Two causes: covers were decoded
  synchronously inside the models' data() on the GUI thread (now decoded
  on a small thread pool by `presentation/cover_loader.py`, placeholder
  first, most-recently-requested first, queue dropped on page change), and
  every imported file made the sidebar, facet tree, status bar and chip bar
  each redo a full refresh (now coalesced into one per burst; user clicks
  still apply instantly).
- **Hashtag filter fixed.** Filtering used `tags LIKE '%tag%'`, so a tag
  also matched every longer tag starting with it ("Khoa hoc" pulled in
  "Khoa hoc vien tuong"). Now matched as a whole list element. The facet
  tree also keeps its scroll position across rebuilds, which is what made a
  click far down the list look like it jumped back up to "Tác giả".
- **Sidebar selection: single click combines, double click isolates** --
  for both the facet tree (OR within a category, AND across) and the
  collections list (union of the selected collections).
- **Facet tree management (right-click):** rename an author or hashtag
  (rewrites every document's metadata; similarly-named tags untouched),
  delete a hashtag from all documents, sort each category by name/count,
  and user-made **groups** -- create, rename, delete, move values in and
  out; clicking a group selects all its members. Groups are purely
  organisational and follow renamed values.
- **★ "Sẽ đọc" reading list:** a star on every cover (grid) and title
  cell (list) files the book into a built-in collection pinned under "Tất
  cả tài liệu". Found by a fixed id, so renaming it doesn't break the stars.
- **"Thêm vào bộ sưu tập" → "Tạo bộ sưu tập mới..."** from the same menu.
- **Detail panel author link:** "Xem N tài liệu của …" shows every
  document by that person *including co-authored ones*, splitting author
  fields on ",", ";", "&", "và", "and" and matching whole names (so
  "Nguyễn Nhật Ánh" doesn't match "Nguyễn Nhật Ánh Hai").
- **Reader:** at most 5 reader windows at once (`reader_manager.py`);
  re-opening an already-open book raises its window instead of a second
  copy. Reader windows now actually free their memory on close
  (WA_DeleteOnClose) -- before, closing only hid them.
- **MOBI/AZW3 can be read in the app**: unpacked to a temporary EPUB/HTML
  via the `mobi` package and shown in the existing readers; the temp copy
  is removed when the window closes. Unreadable files (e.g. DRM) still fall
  back to "open with another app".

### 2026-09-18 — Themes Phase 2: per-theme layouts, connection tests, reader navigation, popup sizing

Completes the staged theme work (Phase 1 below shipped the tokens and
palettes; this is the structural half), plus a batch of fixes around it:

- **Each theme now has its own layout, not just its own palette.**
  "Kệ Sách Gỗ" drops the right-hand detail panel entirely in favour of a
  pill-chip filter bar on top (`presentation/filter_chips.py`, built from
  the formats actually in the library, not a hardcoded list) and a
  selection action bar along the bottom
  (`presentation/selection_action_bar.py`: mini cover, title/author, Mở
  sách / Chỉnh sửa / overflow menu). "Mực Đêm" collapses its sidebar to a
  64px icon rail with a slide-out flyout
  (`presentation/icon_rail_sidebar.py`), the active icon filled solid
  cyan. Cover size is now a per-theme default too (84px / 130px / 120px).
  The collections list was extracted into a reusable `CollectionListPanel`
  so the rail's flyout shows the *same* list the full sidebar does rather
  than a second implementation.
- **A theme picker now sits in the menu bar's right corner**, so switching
  look-and-feel doesn't mean going three clicks deep into Settings. It
  goes through the same save + rebuild path the Settings tab uses.
- **Connection testing for every feature that declares a connection.**
  "Ảnh bìa" (Google Custom Search) and the new "☁️ Đánh giá cộng đồng"
  (Supabase) tabs each got a "Kiểm tra kết nối" button plus a full
  step-by-step setup guide. Supabase had *no settings UI at all* before
  this -- the only way to configure it was hand-editing settings.json.
  Its test checks the `reviews` table and the `review_stats` view
  separately, because they fail independently: a library can submit and
  read reviews fine while "Được đánh giá cao nhất" is broken purely
  because that view (an easily-missed second SQL step) was never created,
  which previously surfaced only as a raw PGRST205 JSON error.
- **Reader navigation**: ←/→/Space/Backspace page through documents,
  prev/next buttons float over the reading area when you scroll and fade
  back out when you stop, and the toolbar's controls now have even
  widths/padding instead of hugging their (very differently sized)
  labels.
- **Popup sizing is now enforced app-wide** (`presentation/dialog_size.py`),
  including Qt's own message/file dialogs, instead of per-dialog pixel
  caps. Capping `maximumSize` alone never worked: a layout's *minimum*
  size wins over it, and one long unwrapped label (a file path, a raw API
  error) pushed that minimum past the screen -- so the guard also wraps
  those labels and releases the layout's minimum constraint.
- The cover format label (PDF/EPUB) lost its dark plate: it now sits
  directly on the artwork, semi-transparent with a 1px shadow for
  legibility -- readable, but no longer competing with the cover.
- "Font nội dung" moved from its own Settings tab into a section of
  "Giao diện", where everything else about appearance already lives.
- Fixed a latent crash in bulk imports: Pillow loads its format plugins
  lazily on first use, and several import worker threads hitting that at
  once is a genuine import race (it showed up as a hard "Windows fatal
  exception: access violation" mid-run). Plugins are now registered once
  at module import, on the main thread.

### 2026-09-18 — Three named themes (Phase 1): tokens, List view, Add Document dialog, reader reskin

Phase 1 of a staged rollout (Phase 2 -- Woodshelf's pill-chip filter bar +
bottom sticky action bar, Inky Night's collapsed icon-rail sidebar, a real
reader table-of-contents + reading-progress bar -- is future work, not
started here):

- Replaced the generic light/dark theme pair with 3 named, fully-designed
  themes -- **Tờ Báo Sáng** (Broadsheet, default), **Kệ Sách Gỗ**
  (Woodshelf), **Mực Đêm** (Inky Night) -- sharing one design language
  (paper content background, a single cyan accent `#0088b0`, hairline
  borders, gradient cover placeholders) via a much richer `ThemeColors`
  token set in `presentation/theme.py`. Inky Night keeps its grid/list
  *content* area light while every other surface (sidebar, top chrome,
  detail panel, status bar) goes dark -- the one theme where "chrome" and
  "content" genuinely need different backgrounds, handled via a new
  `content_bg` token mapped onto `QPalette.Base` rather than a second live
  palette. Old configs migrate automatically (`light` → `broadsheet`,
  `dark` → `inkynight`).
- Cover art placeholders (grid, List view thumbnail, Document Detail
  Panel) are now a deterministic-per-book gradient block with a "book
  spine" shadow (`presentation/cover_placeholder.py`) instead of one flat
  gray rectangle shared by every coverless document.
- List view: new default columns (cover thumbnail, Định dạng, Dung lượng)
  alongside Title/Author/Ngày thêm; the previous defaults (tags/rating/
  review count/ngày chỉnh sửa) are still available via the existing
  column-picker, not removed. Selected rows now get the shared "selected
  item" look (cyan tint + left border) via a small custom item delegate,
  since plain QSS can't paint a left-border-only accent per row in a
  QTableView.
- New **"Thêm tài liệu"** modal (`presentation/add_document_dialog.py`,
  replacing the File menu's old bare file picker): drag-and-drop or browse
  multiple files, optionally set a Title/Author override (single file
  only) plus a Collection and Hashtag applied to the whole batch at
  add-time -- previously only possible one document at a time, after the
  fact, via the metadata editor. `DocumentIndexedEvent`/
  `ImportBatchCompletedEvent` gained a `batch_id` field so this dialog
  only ever tags doc_ids from its own batch, never an unrelated import
  running concurrently (e.g. a watched folder catching up in the
  background) -- covered by a dedicated regression test.
- Reader window: one fixed dark-chrome/warm-paper reading look (not tied
  to the 3 library themes), replacing the previous unstyled black-on-white
  default.
- App-wide font now defaults to a Source Serif 4 fallback stack (the exact
  font isn't bundled yet -- dropping real `.ttf`/`.otf` files into a new
  `presentation/assets/fonts/` later would get pixel-exact fidelity)
  instead of the bare OS default, while the user's own font override in
  Settings still works exactly as before.
- Verified at 15,000 synthetic documents: page load and a full page's
  worth of grid/list icon rendering both stay well under 15ms, confirming
  the gradient placeholders don't regress the existing pagination +
  icon-cache performance strategy.

### 2026-09-18 — Rebrand to MewBook, EULA/Privacy notice, encrypted API keys, Google Images cover search

- Rebranded the in-app display name to **"Mèo Mực"** (window title, sidebar
  header), product name **MewBook** elsewhere (packaging output, README,
  About dialog). Display-only: the internal `smartdoc` package, import
  paths, and the on-disk `%APPDATA%/SmartDocLibrary` folder are unchanged
  on purpose, so existing installs don't lose settings/database/cover
  cache on upgrade. `packaging/SmartDocLibrary.spec` renamed to
  `packaging/MewBook.spec`, producing `dist/MewBook/MewBook.exe`.
- New first-launch EULA/Privacy dialog (`presentation/eula_dialog.py`),
  gating entry to the main window on an explicit "Tôi đã đọc và Đồng ý"
  click (`AppConfig.eula_accepted`, asked once per install). The same text
  is reachable any time after that from a new Help menu -> "Giới thiệu"
  (About) dialog's "Điều khoản pháp lý" page.
- **API keys are now encrypted at rest**: `ai_api_key` and the new
  `google_image_api_key` are stored encrypted in `settings.json`
  (`core/secret_store.py`, a per-install Fernet key file) -- plaintext in
  memory for the app's own use, only the file on disk is protected. A
  legacy plaintext key from before this change still loads correctly and
  gets encrypted on the next save. Settings now shows a note about this
  under both key fields, and the Review dialog shows a note above "Gửi
  đánh giá" that reviews sync to the community library.
- Cover search: added an optional Google Custom Search (Image Search)
  source (Settings -> "🖼️ Ảnh bìa"), tried first when configured with the
  user's own API key + Search Engine ID -- searches the whole web rather
  than just a books catalog, which is what actually finds a cover for a
  Vietnamese title Open Library/Google Books don't carry. Without a key
  configured, cover search behaves exactly as before (Open Library +
  Google Books, no setup required).
- AI Tóm tắt: a transient 429/5xx from the provider (e.g. the reported
  Gemini "503 Service Unavailable") is now retried automatically before
  failing, with a friendlier message if it still doesn't come through.
- Cover grid's format badge ("PDF"/"EPUB") font size is now 10% of the
  cover's own height instead of a fixed 9px, so it stays proportionally
  sized at any cover-size setting instead of shrinking to near-invisible
  on large covers.
- Status bar: the author credit now reads "Auth:Anhtiensinh", and a small
  scrolling donate ticker next to it opens a QR popup
  (`presentation/donate_dialog.py`) for a voluntary coffee donation.
- Omnibar placeholder text rewritten as a clearer usage hint.
- Several dialogs (Cài đặt, Tìm ảnh bìa, Tóm tắt AI, Đánh giá, Dọn dẹp
  trùng lặp) now cap their maximum size instead of being free to grow
  unbounded with their content; the new EULA/About/Donate dialogs are
  fixed-size from the start.

### 2026-09-18 — Status bar: divider from the panel above, function vs. status colors

- The status bar now has a top border, separating it visually from
  whatever's directly above it (it spans the full window width, under
  both the library view and the detail panel).
- The "☁️ Review" / "🤖 AI Tóm tắt" connection indicators previously read
  as one flat run of text ("Review: ✓ Đã kết nối"). The feature name is
  now muted/secondary text and the status is colored (green when
  connected, crimson when not) and bold -- same green/crimson language
  Settings' own connection-test button already uses, so "connected" means
  the same color everywhere in the app.

### 2026-09-17 — Send files to a USB-connected e-reader

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

### 2026-09-17 — Edit menu: clear selection, edit, delete, copy/cut/paste files

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

### 2026-09-17 — File-type badge, panel refresh button, clearer dividers/action colors

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

### 2026-09-17 — In-app EPUB reading (not just PDF)

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

### 2026-09-17 — Fix cover search rate-limiting

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

### 2026-09-17 — Fix search, "All" filter priority, and hashtag-click focus jump

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

### 2026-09-17 — Separate "content font" from the app's own font

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

### 2026-09-17 — Collections: dedupe + counts; Faceted filters: click-based + Hashtag category

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

### 2026-09-17 — Fix Gemini 404, part 2: gemini-2.0-flash was fully retired

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

### 2026-09-17 — Fix Gemini 404 for Google's newer "AQ." API key format

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

### 2026-09-17 — AI Summary follow-ups: setup guide, connection test, uncapped content

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

### 2026-09-17 — AI Summary (non-spoiler book overview, user's own API key)

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

### 2026-09-17 — New app icon/brand mark, icon pass across the UI

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

### 2026-09-17 — Live-apply Settings, bottom status bar, double-click reads, #tag, cover search fix

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

### 2026-09-17 — Edit an existing Collection's rule, not just its name

`NewCollectionDialog` now doubles as an edit dialog: passing it an existing
`VirtualCollection` pre-fills the name/field/value and saving upserts the
same collection id instead of creating a new one. Wired into the sidebar's
right-click menu as "Chỉnh sửa điều kiện", alongside the rename/delete
added earlier today -- closes the gap between "đổi tên" (rename, already
covered) and "chỉnh sửa" (edit the actual rule), which the request listed
as two separate asks.

### 2026-09-17 — In-app Document Reader window

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

### 2026-09-17 — Cover Image Search (Open Library)

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

### 2026-09-17 — Duplicate Finder redesign + Settings expansion (font/threads/scan timing)

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

### 2026-09-17 — Import dedup/summary, manual Collections, detail panel inline edit, bug fixes

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

### 2026-09-17 — List View QTableView + Document Detail Side Panel

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

### 2026-09-17 — Milestones A–E (Windows Phase 1) + Cloud Review System

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

### What's next

See the "Not yet implemented" list in `README.md`'s Status section for the
standing backlog. New work in progress: list view columns + alignment,
sort by highest-rated (Supabase-backed), a document detail/edit side
panel, drag-and-drop import, an in-app reader, cover image search, and an
AI-generated non-spoiler book summary (Google Gemini).
