# Third-party notices

MewBook ("Mèo Mực") 1.0.0 is built on the open-source components below. The
Windows build (PyInstaller) redistributes them; their license texts are
included in each package's `*.dist-info` folder inside the installed app's
`_internal` directory.

MewBook itself is released under the **GNU Affero General Public License,
version 3 or (at your option) any later version** (`AGPL-3.0-or-later`; see
`LICENSE`, project decisions D1 and O4). New source files carry an SPDX header
(`docs/legal/SPDX_POLICY.md`). This file records the third-party side. The full
audit, with the reasoning and the open questions, is in
`docs/legal/LICENSE_INVENTORY.md`.

| Component | Version | License |
|---|---|---|
| PySide6 / PySide6-Essentials / PySide6-Addons / Shiboken6 (Qt for Python) | 6.11.2 | LGPL-3.0-only (or GPL-2.0-only / GPL-3.0-only) |
| PyMuPDF | 1.28.2 | **AGPL-3.0** or Artifex commercial license (MewBook uses the AGPL option) |
| mobi | 0.4.1 | **GPL-3.0-only** |
| Pillow | 12.3.0 | MIT-CMU (HPND) |
| Fonts: Be Vietnam Pro, Lora, Montserrat, Playfair Display, Oswald (bundled in `presentation/assets/fonts`, licence texts beside them) | google/fonts | SIL OFL 1.1 |
| watchdog | 6.0.0 | Apache-2.0 |
| requests | 2.34.2 | Apache-2.0 |
| urllib3 | 2.8.0 | MIT |
| certifi | 2026.7.22 | MPL-2.0 |
| idna | 3.19 | BSD-3-Clause |
| charset-normalizer | 3.5.1 | MIT |
| cryptography | 50.0.1 | Apache-2.0 or BSD-3-Clause |
| cffi | 2.1.1 | MIT-0 |
| pycparser | 3.0 | BSD-3-Clause |
| loguru | 0.7.3 | MIT |
| colorama | 0.4.6 | BSD (see its `dist-info`) |
| win32-setctime | 1.2.0 | MIT |
| standard-imghdr | 3.13.0 | PSF-2.0 |
| pyvi (Vietnamese word segmentation) | 0.1.1 | MIT |
| scikit-learn | 1.9.1 | BSD-3-Clause |
| NumPy | 2.5.3 | BSD-3-Clause AND 0BSD AND MIT AND Zlib AND CC0-1.0 |
| SciPy | 1.18.1 | BSD-3-Clause (bundles GPL-3.0-or-later WITH GCC-exception-3.1 runtime libraries; see its `dist-info`) |
| joblib | 1.6.0 | BSD-3-Clause |
| cloudpickle | 3.1.2 | BSD-3-Clause |
| narwhals | 2.26.0 | MIT |
| threadpoolctl | 3.7.0 | BSD-3-Clause |
| python-crfsuite / sklearn-crfsuite | 0.9.12 / 0.5.0 | MIT |
| tabulate | 0.10.0 | MIT |
| tqdm | 4.70.1 | MPL-2.0 AND MIT |

Build tools (not part of the application code): PyInstaller (its bootloader is
embedded in `MewBook.exe`), Inno Setup, hatchling, pytest, uv.

## Obligations that come with these licenses

This section describes obligations, not legal advice; a lawyer reviews it
before the first public release.

1. **PyMuPDF (AGPL-3.0) and mobi (GPL-3.0-only).** Distributing MewBook with
   these libraries requires offering the **complete corresponding source
   code** of that exact version under the AGPL-3.0, and keeping their
   copyright and license notices. Both licenses allow being combined with
   each other (GPLv3 §13, AGPLv3 §13). The source link and license text are
   shown in Help → About.
2. **PySide6 (LGPL-3.0).** Qt is linked dynamically (PyInstaller's one-folder
   build), so users can replace the Qt libraries; the LGPL notice and license
   text ship with the app.
3. **Apache-2.0, MPL-2.0, BSD, MIT and similar.** Keep each package's
   copyright notice and license text (they are inside each `dist-info`). MPL-2.0
   files (certifi, tqdm) stay under MPL-2.0.
4. **Online services.** The cover sources (Open Library, Google Books, Apple
   iTunes Search API, Tiki, Google Custom Search) and the AI providers each
   have their own terms of use. MewBook calls them from the user's own
   machine, using the user's own keys where a key is needed. Per-source terms
   are tracked in `docs/legal/DATA_SOURCES.md`.
5. **Artwork is not covered by the AGPL.** The MewBook name, logo and mascot
   artwork are governed separately (see `TRADEMARK.md` once added, S0-07).
