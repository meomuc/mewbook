# Contributing to MewBook

Thanks for wanting to help. MewBook ("Mèo Mực") is a free (AGPL-3.0-or-later) ebook and document manager for Windows.
Contributions in English or Vietnamese are welcome; the interface is Vietnamese, code comments are English.

Read `CODE_OF_CONDUCT.md` first. Be kind; this is a small project run by volunteers.

## Ways to help

- **Report a bug or a missing book format.** Use the issue templates. Attach the "support info" from *Help → About → Sao chép
  thông tin hỗ trợ* (version, Windows and Python versions; it contains no book titles or personal paths) and, if the app
  crashed, the relevant lines of `%APPDATA%\SmartDocLibrary\logs\mewbook.log`. **Never attach your library, your
  `settings.json`, `identity.dat`, `.secret.key` or an API key.**
- **Improve the docs or the Vietnamese wording.**
- **Fix a bug or add a feature.** For anything bigger than a small fix, open an issue first so we agree on the direction. The
  roadmap is in `docs/handoff/04_IMPLEMENTATION_PLAN.md`.

## Setup

```
uv sync --group dev
uv run smartdoc          # run the app
uv run pytest -q         # all tests (Qt runs offscreen; the suite takes about a minute and a half)
```

Optional: `tests/test_server_sql.py` (the Supabase SQL on a real PostgreSQL) skips itself unless you run
`uv pip install pgserver psycopg2-binary`; change `src/smartdoc/application/sql/` only with those tests run.

The project is Python 3.12, PySide6, SQLite FTS5 and PyMuPDF. `CLAUDE.md` describes the architecture and the conventions in
detail (it is written for an AI coding assistant but is the best short description of how the code is organised); the
essentials:

- Clean layers under `src/smartdoc/`: `core` -> `domain` -> `infrastructure` -> `application` -> `presentation`. Classes take
  `context: AppContext`; don't import singletons.
- Match the surrounding style. There is no formatter or linter: don't reformat files.
- Every module starts with a docstring that explains *why*; comments are English and say why, not what. User-visible strings
  are Vietnamese.
- Type hints on public signatures; specific exception types (`raise ... from exc`); no bare `except:`.
- **A bug fix gets a regression test that fails without the fix. A new behaviour gets tests.** Run the whole suite before you
  open a pull request.
- A user-visible change gets a line under `## [Unreleased]` in `CHANGELOG.md`.
- A new source file starts with `# SPDX-License-Identifier: AGPL-3.0-or-later` (SQL: `--`); see `docs/legal/SPDX_POLICY.md`.
- Never edit an existing database migration or the frozen `tests/data/schema_1_0_0.sql`; add a numbered `Migration` in
  `infrastructure/schema_migrations.py` (details in `CLAUDE.md`).

## Rules that protect the project (a pull request that breaks one will be declined)

1. **No DRM circumvention.** MewBook may *detect* DRM in order to refuse a file. It never removes, bypasses or links to tools
   that do (`docs/legal/DRM_POLICY.md`).
2. **Licences.** New dependencies must be compatible with AGPL-3.0-or-later; add them to `THIRD_PARTY_NOTICES.md` and
   `docs/legal/LICENSE_INVENTORY.md`. Don't paste code you cannot license under the AGPL.
3. **Data sources.** Only official or keyless public APIs, and every source needs a row in `docs/legal/DATA_SOURCES.md` and a
   switch in Settings. No scraping of web pages (in particular not google.com). A source whose terms are unclear ships switched off.
4. **No secrets, no personal data.** Never commit `.env`, keys, `identity.dat`, `*.db`, your library or your paths. Test data
   must be invented.
5. **Never touch the user's book files** except as `docs/METADATA_LOOKUP_SPEC.md` section 5 allows (explicit opt-in, backup
   first). Copying a file elsewhere is fine; moving, deleting or overwriting is not.

## Sign your commits (DCO)

MewBook uses the [Developer Certificate of Origin](DCO) (the full text is in the file `DCO`): by adding a `Signed-off-by` line
you state that you wrote the contribution or have the right to submit it under the project's licence.

```
git commit -s -m "Fix the cover search retry"
```

adds `Signed-off-by: Your Name <you@example.com>` using your `git config user.name` and `user.email`. Use the name and address
you are happy to have in the public history. There is no CLA: your contribution stays yours and is licensed to everyone under
`AGPL-3.0-or-later`, the same as the rest of the project.

## Pull requests

1. Fork, branch from `main`, keep the change focused.
2. Make sure `uv run pytest -q` passes and that your commits are signed off.
3. Describe what changed and why, and how you checked it (screenshots for UI changes: run the app, don't rely on offscreen
   rendering, which has no fonts).
4. A maintainer reviews it. Expect questions; small, well-tested changes are merged fastest.

## The name and the logo

The code is free software; the name "MewBook"/"Mèo Mực", the logo and the mascot are not licensed by the AGPL. If you publish a
modified version, rename it and use your own artwork. See `TRADEMARK.md`.

## Security

Please don't report vulnerabilities in a public issue: see `SECURITY.md`.
