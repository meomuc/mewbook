// SPDX-License-Identifier: AGPL-3.0-or-later
import assert from "node:assert/strict";
import { test } from "node:test";
import { headline, parseChangelog, parseKnownIssues, parseRoadmap, parseThemes, syncGallery } from "./update-content.js";

const CHANGELOG = `# Changelog

## [Unreleased]

### Fixed
- **Not shipped yet.** Details.

## [1.1.0] - 2026-10-01

### Added
- **Send to e-reader.** Long text
  continued on the next line.
- Plain item without bold. Second sentence.

### Fixed
- **A crash on start.** More.

## [1.0.0] - 2026-09-19

### Added
- **First.** x

## Pre-1.0 development history

### 2026-09-18 — old
- ignored
`;

test("parseChangelog reads released sections and stops at the pre-1.0 history", () => {
  const sections = parseChangelog(CHANGELOG);
  assert.deepEqual(sections.map((s) => s.ver), ["Unreleased", "1.1.0", "1.0.0"]);
  assert.equal(sections[1].date, "2026-10-01");
  assert.equal(sections[1].groups.Added.length, 2);
  assert.match(sections[1].groups.Added[0], /continued on the next line/);
});

test("headline prefers the bold lead, else the first sentence", () => {
  assert.equal(headline("**Send to e-reader.** Long text"), "Send to e-reader");
  assert.equal(headline("Plain item without bold. Second sentence."), "Plain item without bold");
  assert.equal(headline("**A `code` name.** x"), "A code name");
  assert.ok(headline(`**${"x".repeat(300)}.**`).length <= 120);
});

test("parseRoadmap keeps the next-release group apart from the rest", () => {
  const items = parseRoadmap("- [next] N | d | Kế hoạch\n- [planned] P");
  assert.deepEqual(items.map((i) => [i.title, i.status]), [["N", "next"], ["P", "planned"]]);
});

test("parseRoadmap skips done items and tolerates missing columns", () => {
  const items = parseRoadmap("- [planned] A | desc | Q1\n- [done] B | x | y\n- [doing] C\nnoise");
  assert.deepEqual(items, [
    { title: "A", desc: "desc", eta: "Q1", status: "planned" },
    { title: "C", desc: "", eta: "", status: "doing" },
  ]);
});

test("parseKnownIssues maps status names and defaults the priority", () => {
  const items = parseKnownIssues("- [open] Lỗi A | Cao\n- [investigating] Lỗi B\n- [closed] ignored | Cao");
  assert.deepEqual(items, [
    { desc: "Lỗi A", status: "Đang xử lý", priority: "Cao" },
    { desc: "Lỗi B", status: "Đang tìm hiểu", priority: "Vừa" },
  ]);
});

const THEME_PY = (accent, extra = "") => `
_FONTS = ("Georgia", "serif")
${extra}
ONE = ThemeColors(
    key="one",  # a comment
    display_name="Theme One",
    accent="${accent}",
    font_families=_FONTS,
)

TWO = ThemeColors(
    key="two",
    display_name="Theme Two",
    accent="#222222",
)

THEMES: dict[str, ThemeColors] = {
    "one": ONE,
    "two": TWO,
}
`;

test("parseThemes: names, comment edits are no change, colour and shared-constant edits are", () => {
  const base = parseThemes(THEME_PY("#111111"));
  assert.deepEqual(Object.keys(base), ["one", "two"]);
  assert.equal(base.one.name, "Theme One");
  assert.equal(parseThemes(THEME_PY("#111111").replace("# a comment", "# other")).one.hash, base.one.hash);
  const recolored = parseThemes(THEME_PY("#999999"));
  assert.notEqual(recolored.one.hash, base.one.hash);
  assert.equal(recolored.two.hash, base.two.hash);
  const refont = parseThemes(THEME_PY("#111111").replace('"Georgia"', '"Arial"'));
  assert.notEqual(refont.one.hash, base.one.hash);
});

test("syncGallery: baseline, new theme, changed theme, replaced picture, new picture file", () => {
  const themes = parseThemes(THEME_PY("#111111"));
  const hashes = { "one.webp": "a1", "two.webp": "b1" };
  const hashOf = (f) => hashes[f];
  const entry = (k) => ({ src: `/assets/gallery/${k}.webp`, title: k, caption: "", theme: k });

  // First run: today's themes are the baseline, nothing pending, src gets a cache-busting hash.
  let run = syncGallery([entry("one"), entry("two")], themes, ["one.webp", "two.webp"], hashOf);
  assert.deepEqual(run.pendingShots, []);
  assert.equal(run.gallery[0].src, "/assets/gallery/one.webp?v=a1");

  // A new theme with no picture is reported as "new".
  const withThree = { ...themes, three: { name: "Theme Three", hash: "zzz" } };
  run = syncGallery(run.gallery, withThree, ["one.webp", "two.webp"], hashOf);
  assert.deepEqual(run.pendingShots, [{ theme: "three", name: "Theme Three", reason: "new" }]);

  // A changed theme whose picture did not change is reported as "changed" ...
  const changed = parseThemes(THEME_PY("#999999"));
  run = syncGallery(run.gallery, changed, ["one.webp", "two.webp"], hashOf);
  assert.deepEqual(run.pendingShots.map((p) => [p.theme, p.reason]), [["one", "changed"]]);

  // ... and is cleared once its picture file is replaced.
  hashes["one.webp"] = "a2";
  run = syncGallery(run.gallery, changed, ["one.webp", "two.webp"], hashOf);
  assert.deepEqual(run.pendingShots, []);
  assert.equal(run.gallery[0].src, "/assets/gallery/one.webp?v=a2");

  // A picture named after a new theme is added automatically, with the theme's name.
  hashes["three.webp"] = "c1";
  run = syncGallery(run.gallery, { ...changed, three: withThree.three }, ["one.webp", "three.webp", "two.webp"], hashOf);
  const three = run.gallery.find((g) => g.theme === "three");
  assert.equal(three.title, "Theme Three");
  assert.deepEqual(run.pendingShots, []);
});
