# Mèo Mực — MewBook landing page

Vite + React + Tailwind. The look (weather-reactive Nắng/Mưa/Mây/Đêm, `#FFF8F0 #FF8C42 #5A3E36`, Quicksand +
Be Vietnam Pro, the cat) lives in `App.tsx`; the words that change with releases live in `content.json`.
`README-CLAUDE.md` is the original brief.

    npm install
    npm run dev                   # http://localhost:5173
    npm run build                 # tsc + vite build -> dist/ (deploy on any static host)
    npm test                      # tests of the content script
    npm run update-content        # refresh content.json
    npm run update-content:commit # ... and commit it as "chore: auto update content from GitHub"

## Weather
On load the page asks the browser for the visitor's location and reads the current weather from Open-Meteo
(`weather.ts`). Coordinates are rounded to ~11 km, go only to Open-Meteo and are not stored. If the visitor
declines or the request fails, the local clock decides (night after 18:00). Picking a theme by hand turns "auto" off.

## Content: where each part comes from (`scripts/update-content.js`)
| content.json | Source |
|---|---|
| `versions` | `CHANGELOG.md` released sections + `__version__`; download link = `meta.downloadUrl` (Google Drive folder) |
| `roadmap`  | `docs/ROADMAP.md` |
| `bugs`     | `docs/KNOWN_ISSUES.md` (open), `### Fixed` of released versions ("Đã sửa"), and GitHub Issues labelled `bug` when `--repo owner/name` or `MEWBOOK_GITHUB_REPO` is set |
| `gallery`  | the app's themes (`presentation/theme.py`) against the pictures in `public/assets/gallery/` |

**Interface check (every run).** The script fingerprints each theme (its definition plus the fonts/colours it uses,
comments ignored) and each picture file, and compares them with what `content.json → gallery` recorded:
- a picture replaced on disk: the entry is refreshed and its URL gets `?v=<hash>`, so browsers load the new one;
- a picture file with no entry: added to the gallery automatically (named after the theme if it is `<theme key>.webp`);
- a theme with no picture ("new"), or a theme that changed while its picture did not ("changed"): a warning, and the
  item is listed in `content.json → pendingShots`. Save a new picture as `public/assets/gallery/<theme key>.webp`
  (keys: `broadsheet woodshelf inkynight healing retro_tech japandi zen_dark`) and run the script again.

`packaging\build.ps1 -Release` runs the script with `--commit` at the end, so every release build updates the site
content. Set `"auto": false` on a version to keep its hand-written Vietnamese bullets (CHANGELOG entries are English).
Donate details go in `content.json` → `donate` (empty ones are hidden). Point the domain (mewbook.*) at wherever
`dist/` is hosted.

The pictures in `public/assets/gallery/` are the project owner's own work, confirmed on 2026-09-25 as fine to publish. The donate QR (`public/assets/donate-qr.png`) is published on purpose: the owner chose to show it on the donate section.
