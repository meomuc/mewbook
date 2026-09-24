// SPDX-License-Identifier: AGPL-3.0-or-later
/**
 * Refreshes landing-mewbook/content.json (versions, roadmap, bugs) from the project's own sources of truth.
 * packaging/build.ps1 -Release runs it after a release build, so the site follows every release.
 *
 *   versions  <- CHANGELOG.md (released sections) + __version__ in src/smartdoc/__init__.py; the download link
 *                is meta.downloadUrl; the installer size is read from dist/installer/ when it exists
 *   roadmap   <- docs/ROADMAP.md            (`- [planned|doing|done] Title | description | when`)
 *   bugs      <- GitHub Issues labelled "bug" (only when a repo is given), docs/KNOWN_ISSUES.md (open),
 *                and the `### Fixed` sections of released CHANGELOG.md versions ("Đã sửa")
 *
 *   node scripts/update-content.js [--dry-run] [--commit] [--repo owner/name] [--download-url URL]
 *
 * --commit stages content.json only and commits it as "chore: auto update content from GitHub" when it changed.
 * GitHub is optional (this project has no public remote yet): pass --repo or set MEWBOOK_GITHUB_REPO, and
 * GITHUB_TOKEN to lift the anonymous rate limit. A GitHub failure never stops the update: the local sources win.
 * A version entry with "auto": false keeps its hand-written bullets (the CHANGELOG is in English, the page in
 * Vietnamese); everything else about it (date, download link, tag) is still refreshed.
 */
import { execFileSync } from "node:child_process";
import { createHash } from "node:crypto";
import { existsSync, readFileSync, statSync, writeFileSync } from "node:fs";
import path from "node:path";
import { fileURLToPath } from "node:url";

const LANDING = path.resolve(path.dirname(fileURLToPath(import.meta.url)), "..");
const REPO_ROOT = path.resolve(LANDING, "..");
const CONTENT_FILE = path.join(LANDING, "content.json");
const COMMIT_MESSAGE = "chore: auto update content from GitHub";

const MAX_BULLETS = 3;
const MAX_FIXED_BUGS = 8;
const MAX_TEXT = 120;

const TAG_NEW = "bg-[#FF8C42] text-white";
const TAG_STABLE = "bg-[#5A3E36] text-[#F5E6CC]";
const TAG_FIRST = "bg-white border text-[#8B6B5E]";

const STATUS_COLOR = { "Đã sửa": "bg-emerald-500", "Đang xử lý": "bg-amber-500", "Đang tìm hiểu": "bg-zinc-400" };
const ISSUE_STATUS = { open: "Đang xử lý", investigating: "Đang tìm hiểu" };

const log = (msg) => console.log(`[update-content] ${msg}`);
const warn = (msg) => console.warn(`[update-content] WARNING: ${msg}`);

function readText(...parts) {
  const file = path.join(REPO_ROOT, ...parts);
  return existsSync(file) ? readFileSync(file, "utf8").replace(/^﻿/, "") : null;
}

/** "**Bold lead.** more text" -> "Bold lead"; without bold, the first sentence; markdown stripped, capped. */
export function headline(itemText) {
  const flat = itemText.replace(/\s+/g, " ").trim();
  const bold = flat.match(/^\*\*(.+?)\*\*/);
  let text = bold ? bold[1] : flat.split(/(?<=[.!?])\s/)[0];
  text = text.replace(/`([^`]*)`/g, "$1").replace(/\*\*/g, "").replace(/[.:\s]+$/, "").trim();
  return text.length > MAX_TEXT ? `${text.slice(0, MAX_TEXT - 1).trimEnd()}…` : text;
}

/** Keep-a-Changelog text -> [{ ver, date, groups: { Added: [item...], Fixed: [...] } }]; stops at the pre-1.0 history. */
export function parseChangelog(text) {
  const sections = [];
  let section = null;
  let group = null;
  let item = null;
  const flush = () => {
    if (item && section && group) (section.groups[group] ||= []).push(item.join(" "));
    item = null;
  };
  for (const line of text.split(/\r?\n/)) {
    const head = line.match(/^## \[([^\]]+)\](?:\s*-\s*(\d{4}-\d{2}-\d{2}))?/);
    if (head) {
      flush();
      section = { ver: head[1], date: head[2] || null, groups: {} };
      sections.push(section);
      group = null;
      continue;
    }
    if (/^## /.test(line)) {
      flush();
      section = null;
      continue;
    }
    if (!section) continue;
    const grp = line.match(/^### (\w+)/);
    if (grp) {
      flush();
      group = grp[1];
      continue;
    }
    if (/^- /.test(line)) {
      flush();
      item = [line.slice(2)];
    } else if (item && /^\s+\S/.test(line)) {
      item.push(line.trim());
    } else if (!line.trim()) {
      flush();
    }
  }
  flush();
  return sections;
}

export function parseRoadmap(text) {
  const items = [];
  for (const line of text.split(/\r?\n/)) {
    const m = line.match(/^- \[(planned|doing|done)\]\s+(.+)$/);
    if (!m) continue;
    const [title, desc = "", eta = ""] = m[2].split("|").map((s) => s.trim());
    if (m[1] !== "done" && title) items.push({ title, desc, eta, status: m[1] });
  }
  return items;
}

export function parseKnownIssues(text) {
  const items = [];
  for (const line of text.split(/\r?\n/)) {
    const m = line.match(/^- \[(open|investigating)\]\s+(.+)$/);
    if (!m) continue;
    const [desc, priority = "Vừa"] = m[2].split("|").map((s) => s.trim());
    if (desc) items.push({ desc, status: ISSUE_STATUS[m[1]], priority });
  }
  return items;
}

/** Stable short id, so a bug keeps its "#" name between runs. */
const shortId = (text) => `#${createHash("sha1").update(text).digest("hex").slice(0, 4).toUpperCase()}`;

function bugRow({ id, desc, status, priority, url }) {
  const row = { id, desc, status, priority, color: STATUS_COLOR[status] };
  if (url) row.github_url = url;
  return row;
}

function currentVersion() {
  const src = readText("src", "smartdoc", "__init__.py") ?? "";
  const m = src.match(/^__version__\s*=\s*"([^"]+)"/m);
  if (!m) throw new Error("__version__ not found in src/smartdoc/__init__.py");
  return m[1];
}

function installerInfo(version) {
  const file = path.join(REPO_ROOT, "dist", "installer", `MewBook-Setup-${version}.exe`);
  if (!existsSync(file)) return null;
  return { size: `${Math.round(statSync(file).size / (1024 * 1024))} MB` };
}

function buildVersions(sections, latest, existing, downloadUrl) {
  const byVer = new Map(existing.map((v) => [v.ver, v]));
  const released = sections.filter((s) => s.ver !== "Unreleased" && /^\d+\.\d+\.\d+/.test(s.ver));
  if (!released.some((s) => s.ver === latest)) {
    // Release built before the CHANGELOG was rolled over: describe it from [Unreleased].
    const pending = sections.find((s) => s.ver === "Unreleased");
    released.unshift({ ver: latest, date: new Date().toISOString().slice(0, 10), groups: pending ? pending.groups : {} });
    warn(`CHANGELOG.md has no [${latest}] section; using [Unreleased] and today's date.`);
  }
  return released.map((s, i) => {
    const ver = `v${s.ver}`;
    const old = byVer.get(ver) ?? {};
    const auto = [...(s.groups.Added ?? []), ...(s.groups.Changed ?? [])].slice(0, MAX_BULLETS).map(headline);
    const download = { win: downloadUrl };
    const installer = installerInfo(s.ver);
    if (installer) download.size = installer.size;
    else if (old.download?.size) download.size = old.download.size;
    return {
      ver,
      date: s.date ?? old.date,
      tag: i === 0 ? "Mới" : i === released.length - 1 ? "Khởi đầu" : "Ổn định",
      tagColor: i === 0 ? TAG_NEW : i === released.length - 1 ? TAG_FIRST : TAG_STABLE,
      ...(old.auto === false ? { auto: false } : {}),
      bullets: old.auto === false && old.bullets?.length ? old.bullets : auto,
      link: old.link ?? "",
      download,
    };
  });
}

async function githubBugs(repo) {
  const headers = { Accept: "application/vnd.github+json", "User-Agent": "mewbook-landing-update" };
  if (process.env.GITHUB_TOKEN) headers.Authorization = `Bearer ${process.env.GITHUB_TOKEN}`;
  const res = await fetch(`https://api.github.com/repos/${repo}/issues?state=all&labels=bug&per_page=30`, { headers });
  if (!res.ok) throw new Error(`GitHub answered ${res.status}`);
  const rows = [];
  for (const issue of await res.json()) {
    if (issue.pull_request) continue;
    const labels = issue.labels.map((l) => (typeof l === "string" ? l : l.name).toLowerCase());
    const priority = labels.some((l) => /high|cao/.test(l)) ? "Cao" : labels.some((l) => /low|thấp/.test(l)) ? "Thấp" : "Vừa";
    const status = issue.state === "closed" ? "Đã sửa" : labels.some((l) => /investigat|tìm hiểu/.test(l)) ? "Đang tìm hiểu" : "Đang xử lý";
    rows.push(bugRow({ id: `#${issue.number}`, desc: issue.title, status, priority, url: issue.html_url }));
  }
  return rows;
}

async function buildBugs(sections, repo) {
  const bugs = [];
  if (repo) {
    try {
      bugs.push(...(await githubBugs(repo)));
      log(`GitHub Issues (${repo}): ${bugs.length} bug(s)`);
    } catch (err) {
      warn(`GitHub Issues skipped: ${err.message}`);
    }
  }
  const known = readText("docs", "KNOWN_ISSUES.md");
  for (const issue of known ? parseKnownIssues(known) : []) bugs.push(bugRow({ id: shortId(issue.desc), ...issue }));
  // Only released sections: a fix that sits in [Unreleased] is not in the build people download yet.
  const fixed = sections.filter((s) => s.ver !== "Unreleased").flatMap((s) => (s.groups.Fixed ?? []).map(headline));
  for (const desc of fixed) bugs.push(bugRow({ id: shortId(desc), desc, status: "Đã sửa", priority: "Vừa" }));

  const seen = new Set();
  const unique = bugs.filter((b) => !seen.has(b.desc.toLowerCase()) && seen.add(b.desc.toLowerCase()));
  const open = unique.filter((b) => b.status !== "Đã sửa");
  return [...open, ...unique.filter((b) => b.status === "Đã sửa").slice(0, MAX_FIXED_BUGS)];
}

function commit() {
  const rel = path.relative(REPO_ROOT, CONTENT_FILE).split(path.sep).join("/");
  const git = (...args) => execFileSync("git", ["-C", REPO_ROOT, ...args], { encoding: "utf8" });
  if (!git("status", "--porcelain", "--", rel).trim()) {
    log("content.json unchanged, nothing to commit");
    return;
  }
  // The pathspec keeps anything else the user has staged out of this commit.
  git("add", "--", rel);
  git("commit", "-m", COMMIT_MESSAGE, "--", rel);
  log(`committed: ${COMMIT_MESSAGE}`);
}

async function main() {
  const args = process.argv.slice(2);
  const flag = (name) => args.includes(name);
  const value = (name) => (args.includes(name) ? args[args.indexOf(name) + 1] : undefined);

  const existing = JSON.parse(readFileSync(CONTENT_FILE, "utf8"));
  const meta = { ...existing.meta };
  const downloadUrl = value("--download-url") ?? meta.downloadUrl;
  if (!downloadUrl) throw new Error("meta.downloadUrl is missing in content.json (or pass --download-url)");
  const latest = currentVersion();
  const sections = parseChangelog(readText("CHANGELOG.md") ?? "");

  const roadmapText = readText("docs", "ROADMAP.md");
  const content = {
    ...existing,
    meta: { ...meta, latest, downloadUrl },
    versions: buildVersions(sections, latest, existing.versions ?? [], downloadUrl),
    roadmap: roadmapText ? parseRoadmap(roadmapText) : existing.roadmap ?? [],
    bugs: await buildBugs(sections, value("--repo") ?? process.env.MEWBOOK_GITHUB_REPO),
  };
  const out = `${JSON.stringify(content, null, 2)}\n`;

  if (flag("--dry-run")) {
    log(`dry run, would write ${content.versions.length} version(s), ${content.roadmap.length} roadmap item(s), ${content.bugs.length} bug(s)`);
    return;
  }
  if (out !== readFileSync(CONTENT_FILE, "utf8")) writeFileSync(CONTENT_FILE, out);
  log(`content.json: v${latest}, ${content.versions.length} version(s), ${content.roadmap.length} roadmap item(s), ${content.bugs.length} bug(s)`);
  if (flag("--commit")) commit();
}

if (process.argv[1] && path.resolve(process.argv[1]) === fileURLToPath(import.meta.url)) {
  main().catch((err) => {
    console.error(`[update-content] failed: ${err.message}`);
    process.exit(1);
  });
}
