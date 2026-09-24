// SPDX-License-Identifier: AGPL-3.0-or-later
import assert from "node:assert/strict";
import { test } from "node:test";
import { headline, parseChangelog, parseKnownIssues, parseRoadmap } from "./update-content.js";

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
