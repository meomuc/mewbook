# CLAUDE.md — MewBook ("Mèo Mực")

## 1. Project Overview & Architecture
Windows desktop ebook/document manager: Python 3.12, PySide6 (Qt 6) UI, SQLite FTS5, PyMuPDF/EPUB extractors, watchdog, requests; built with uv + hatchling, packaged with PyInstaller + Inno Setup.
Clean Architecture under `src/smartdoc/`: `core/` (AppContext, EventBus, ConfigManager, diagnostics) → `domain/` (models, taxonomy, classifier) → `infrastructure/` (DatabaseManager, extractors, cover cache) → `application/` (file watcher, import queue, smart classifier, cover search, cloud reviews, AI summary) → `presentation/` (all Qt widgets). `app.py` is the composition root.
Flow: file watcher / import workers (background threads) → `EventBus.publish()` → `QtEventBridge` marshals onto the GUI thread → widgets re-query `context.db.query_documents()` (the single read path: FTS text + parameterized WHERE).
What the library is filtered by (search text, collections, hashtags, authors, formats) is **one** immutable `LibraryFilter` owned by `context.filters` (`FilterService`); every widget changes it through the service (`select/remove/set_query/clear`) and listens to the single `FilterChangedEvent`; live sidebar counts come from `context.facets` (`FacetCounter`); SQL for it is `db.filter_where()`. Don't publish the legacy `SearchRequestedEvent`/`FacetFilterChangedEvent`/`CollectionSelectedEvent` — see `docs/FILTER_REDESIGN_SPEC.md`.
Every class takes `context: AppContext` and reaches `context.db / .config / .event_bus`; never construct collaborators or import a singleton. More detail: `README.md` (Architecture), `docs/THEME_DESIGN_BRIEF.md`, module docstrings (they explain *why*).

## 2. Build & Test Commands
```
uv sync --group dev                     # install (run.bat sets UV_PROJECT_ENVIRONMENT to a venv outside OneDrive)
uv run smartdoc                         # run the app (or run.bat)
uv run pytest -q                        # all tests (QT_QPA_PLATFORM=offscreen is set by tests/conftest.py)
uv run pytest tests/test_x.py -q -k name
powershell -ExecutionPolicy Bypass -File packaging\build.ps1   # tests + exe + installer
```
- **No linter/formatter is configured** (no ruff/black/mypy). Don't add config or reformat files; match the surrounding style (lines up to ~120 chars).
- Offscreen Qt has **no fonts installed**: font-dependent assertions need stubbing; use the real platform (unset `QT_QPA_PLATFORM`) to eyeball rendering.
- Known env issue: the SVM trainer tests need scikit-learn/numpy (they come with `pyvi`) and skip themselves without. The timing-based tests (`test_file_watcher`, `test_import_queue`) were made robust to a starved CPU (S1-08); if one still fails, rerun it alone before suspecting your change. **Unresolved:** a native heap-corruption crash (`Windows fatal exception: code 0xc0000374`, top frame `Garbage-collecting` in `tests/conftest.py`) once killed the whole run at `tests/test_add_document_dialog.py` right after an unrelated change (reading `PRAGMA user_version` three times instead of once); it is sensitive to allocation layout, not root-caused, and did not reproduce in a minimal script. If a full run dies that way, it is this, not your change: rerun, and tell the owner. PyMuPDF is now guarded by a lock (`infrastructure/pymupdf_lock.py`) as a precaution.

## 3. Code Style & Conventions
- Every module: `from __future__ import annotations`, a top docstring explaining purpose and design decisions, type hints on signatures. Many modules end with a runnable `if __name__ == "__main__":` demo.
- Naming: `snake_case` functions/modules, `PascalCase` classes, `_private` helpers and module constants (`_UPPER`); public tunables are `UPPER_CASE` (e.g. `MIN_MATCH_SCORE`). Events are frozen dataclasses ending in `Event` in `core/event_bus.py`.
- Licence: the code is `AGPL-3.0-or-later` (`LICENSE`). Every **new** source file starts with `# SPDX-License-Identifier: AGPL-3.0-or-later` (SQL: `--`), before the module docstring -- `docs/legal/SPDX_POLICY.md`. Never add a dependency with a licence incompatible with AGPL-3.0 (`docs/legal/LICENSE_INVENTORY.md`).
- Comments are English and explain *why*; user-facing UI strings are **Vietnamese**.
- **State:** config lives in the `AppConfig` dataclass via `ConfigManager` (secrets encrypted through `SecretStore`, fields listed in `_ENCRYPTED_FIELDS`); cross-widget communication goes through events, not direct references. The only module-level state is the applied theme (`theme.current_colors()`). Widgets never branch on a theme key — add options to `ThemeColors` instead (`test_theme_contract.py` validates every theme automatically).
- **Threading:** a widget reacting to an event must subscribe through `QtEventBridge`, never directly. DB writes go through `DatabaseManager` (holds `write_lock`).
- **Errors:** define a specific exception per module (`CoverSearchError`, `AISummaryError`, `CloudReviewError` → `NicknameTakenError`, `EpubReadError`, `TaxonomyError`…), raise with `from exc`, catch the specific type. A broad `except Exception` is allowed only to isolate one independent source/worker, with `# noqa: BLE001 -- reason` and `logger.exception(...)`. Log with `logging.getLogger(__name__)`; uncaught errors are captured by `core/diagnostics.py` into `%APPDATA%/SmartDocLibrary/logs/mewbook.log` (read it first when debugging a user-reported crash).
- **Shutdown order:** `MainWindow.closeEvent` stops workers but must **not** close the DB; `app.py` calls `context.shutdown()` after `app.exec()` returns (queued events still query the DB).
- Tests: `tests/test_<module>.py`, use the `app_context` / `qapp` fixtures (in-memory DB); bug fixes get a regression test that fails before the fix.
- Every user-visible change → entry under `## [Unreleased]` in `CHANGELOG.md`. The version's single source is `__version__` in `src/smartdoc/__init__.py`; never edit it elsewhere.

## 4. Guardrails (do NOT)
- Never commit secrets: `.env`, `service_account*.json`, `credentials.json`, `token.json`, `*.pem`, `*.key`, `identity.dat`, API keys/Supabase keys in code or tests, or `*.db` files (all covered by `.gitignore` — don't weaken it). Secrets stay in `%APPDATA%/SmartDocLibrary`, encrypted.
- Never edit an existing migration: `src/smartdoc/application/sql/001_*.sql` (Supabase) is immutable — add `002_*.sql`. In `DatabaseManager._migrate_add_missing_columns` only *append* new columns; never rename/drop/alter existing ones (users' `library.db` must upgrade in place). Anything else -- a new table, a changed column -- is a numbered `Migration` in `infrastructure/schema_migrations.py` (`PRAGMA user_version`; one transaction each; never edit a released one; a database newer than the build is refused). `tests/data/schema_1_0_0.sql` is the frozen 1.0.0 schema: never edit it.
- Typing (the Python equivalent of "no `any`"): no untyped public signatures, no bare `except:`, avoid `typing.Any` unless the value truly is dynamic (JSON, Qt variants).
- Don't move or delete users' original ebook files. Writing *metadata* into EPUB/PDF is allowed only as specified in `docs/METADATA_LOOKUP_SPEC.md` §5 (explicit per-run opt-in, backup first, temp file + verify + `os.replace`); no other code path may modify them.
- No DRM support (`docs/legal/DRM_POLICY.md`): never add, call, bundle, document or link a tool or code that removes or bypasses DRM. DRM may only be *detected* in order to refuse the file. Format conversion reads the original read-only, writes elsewhere, and never overwrites the source.
- Don't scrape google.com or add sources that violate a service's terms; use official/keyless public APIs (see `cover_search.py`). Every external source needs a row in `docs/legal/DATA_SOURCES.md` (terms, key, limits, status) and a switch in Settings → Ảnh bìa (`disabled_cover_sources`); a source whose terms are unclear ships switched off.
- Don't add a dependency without checking licence impact (`THIRD_PARTY_NOTICES.md`: PyMuPDF is AGPL, mobi is GPL) or importing `pyvi`/numpy outside the classification worker process (keeps the GUI process light).
- Don't run destructive git commands (`stash`, `reset --hard`, `checkout --`) on the working tree without asking — it holds many uncommitted changes.
- Don't commit `dist/`, `build_pyinstaller/`; don't push or tag releases unless asked (release steps: `README.md` → Versioning & releases).
