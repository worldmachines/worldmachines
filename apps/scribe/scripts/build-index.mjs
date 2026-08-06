#!/usr/bin/env node
// build-index.mjs — bake a compact index of raw-notes/ into public/data/notes-index.json.
//
// The index is the OFFLINE fallback for three pickers in the PWA:
//   • wiki-link picker  (note ids + titles — so [[links]] are chosen, never typed)
//   • book picker       (source ids under raw-notes/commons/reading/)
//   • tag type-ahead    (every tag already in use, so a sixth spelling isn't minted)
//
// When GITHUB_TOKEN is configured the Worker serves these lists LIVE from the repo's
// git tree instead (see src/lib/github.js listTree). This baked copy exists so the
// pickers still work in dry-run, offline, and on first paint. It freezes at the commit
// it was generated from — regenerate with:
//
//     node apps/scribe/scripts/build-index.mjs
//
// Zero dependencies: reads the checkout with fs, parses only the few frontmatter
// fields the pickers need (no YAML engine).

import { readdir, readFile, writeFile, stat } from "node:fs/promises";
import { existsSync } from "node:fs";
import path from "node:path";
import { fileURLToPath } from "node:url";

const HERE = path.dirname(fileURLToPath(import.meta.url));
const APP = path.resolve(HERE, "..");
const REPO = path.resolve(APP, "..", "..");
const RAW = path.join(REPO, "raw-notes");
const OUT = path.join(APP, "public", "data", "notes-index.json");

/** Recursively list *.md under a directory (skipping dotfiles and empty files). */
async function walk(dir) {
  const out = [];
  let entries;
  try {
    entries = await readdir(dir, { withFileTypes: true });
  } catch {
    return out;
  }
  for (const e of entries) {
    if (e.name.startsWith(".")) continue;
    const p = path.join(dir, e.name);
    if (e.isDirectory()) out.push(...(await walk(p)));
    else if (e.isFile() && e.name.endsWith(".md")) {
      const s = await stat(p);
      if (s.size > 0) out.push(p);
    }
  }
  return out;
}

/** Pull the first H1 and the frontmatter `summary` / `tags` without a YAML parser. */
function peek(text) {
  let fm = "";
  let body = text;
  const m = text.match(/^---[ \t]*\r?\n([\s\S]*?)\r?\n---[ \t]*\r?\n?/);
  if (m) {
    fm = m[1];
    body = text.slice(m[0].length);
  }
  const h1 = body.match(/^#\s+(.+?)\s*$/m);

  // tags come in two shapes in this repo: `tags: [a, b]` and a block sequence.
  const tags = [];
  const inline = fm.match(/^tags:[ \t]*\[(.*)\][ \t]*$/m);
  if (inline) {
    for (const t of inline[1].split(",")) {
      const v = unquote(t);
      if (v) tags.push(v);
    }
  } else if (/^tags:[ \t]*$/m.test(fm)) {
    const lines = fm.split(/\r?\n/);
    let inTags = false;
    for (const line of lines) {
      if (/^tags:[ \t]*$/.test(line)) { inTags = true; continue; }
      if (!inTags) continue;
      const li = line.match(/^[ \t]*-[ \t]+(.*)$/);
      if (li) { const v = unquote(li[1]); if (v) tags.push(v); continue; }
      if (line.trim()) break; // next key ends the sequence
    }
  }
  const summary = unquote((fm.match(/^summary:[ \t]*(.*)$/m) || [, ""])[1]);
  return { title: h1 ? h1[1].trim() : "", tags, summary };
}

function unquote(s) {
  let v = String(s || "").trim();
  if (v.length >= 2 && ((v[0] === '"' && v.at(-1) === '"') || (v[0] === "'" && v.at(-1) === "'"))) {
    v = v.slice(1, -1).replace(/''/g, "'").replace(/\\"/g, '"');
  }
  return v.trim();
}

/** Human title for a source: the parenthetical in _chunks.yaml's header comment. */
async function sourceTitle(id, dir) {
  const sidecar = path.join(dir, "_chunks.yaml");
  if (existsSync(sidecar)) {
    const head = (await readFile(sidecar, "utf8")).split(/\r?\n/).slice(0, 8);
    const comment = head.filter((l) => l.startsWith("#")).map((l) => l.replace(/^#\s?/, "")).join(" ");
    const paren = comment.match(/\(([^)]+)\)/);
    if (paren) {
      // "The Relentless Revolution: A History of Capitalism, Joyce Appleby, …"
      const first = paren[1].split(",")[0].trim().replace(/^["“]|["”]$/g, "");
      if (first) return first;
    }
  }
  return id.replace(/-/g, " ").replace(/\b\w/g, (c) => c.toUpperCase());
}

const files = await walk(RAW);
const notes = [];
const tagCounts = new Map();

for (const abs of files) {
  const rel = path.relative(REPO, abs).split(path.sep).join("/");
  const parts = rel.split("/"); // raw-notes/<dir>/…/<file>.md
  if (parts.length < 3) continue; // raw-notes/README.md is not a note
  const dir = parts[1];
  const stem = path.basename(abs, ".md");
  if (stem === "index" || stem === "README") continue; // excluded from the lake
  const { title, tags } = peek(await readFile(abs, "utf8"));
  for (const t of tags) tagCounts.set(t, (tagCounts.get(t) || 0) + 1);
  notes.push({ i: stem, t: title || stem, p: rel, d: dir });
}

// Sources = the subdirectories of raw-notes/commons/reading/.
const sources = [];
const readingDir = path.join(RAW, "commons", "reading");
for (const e of (await readdir(readingDir, { withFileTypes: true }).catch(() => []))) {
  if (!e.isDirectory() || e.name.startsWith(".")) continue;
  const dir = path.join(readingDir, e.name);
  const noteCount = (await readdir(dir)).filter((f) => f.endsWith(".md")).length;
  sources.push({ id: e.name, title: await sourceTitle(e.name, dir), notes: noteCount });
}
sources.sort((a, b) => a.id.localeCompare(b.id));

const tags = [...tagCounts.entries()].sort((a, b) => b[1] - a[1] || a[0].localeCompare(b[0])).map(([t]) => t);

notes.sort((a, b) => a.p.localeCompare(b.p));

const index = {
  generated: new Date().toISOString(),
  note: "Baked from the local checkout. The Worker serves live data instead when GITHUB_TOKEN is set.",
  counts: { notes: notes.length, sources: sources.length, tags: tags.length },
  sources,
  tags,
  notes,
};

await writeFile(OUT, JSON.stringify(index), "utf8");
const bytes = Buffer.byteLength(JSON.stringify(index));
console.log(
  `wrote ${path.relative(REPO, OUT)} — ${notes.length} notes, ${sources.length} sources, ${tags.length} tags (${(bytes / 1024).toFixed(0)} KB)`
);
