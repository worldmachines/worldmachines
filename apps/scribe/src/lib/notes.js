// notes.js — build the EXACT markdown file each note type would commit, and the
// exact path it would land at. Single source of truth: the dry-run preview is
// produced by this code, so what you review is byte-for-byte what gets written.
//
// Conventions were read off the repo, not invented:
//
//   • Frontmatter the corpus pipeline actually consumes is `summary`, `tags`,
//     `last_updated` (tools/notes-pipeline/notes_to_parquet.py). Everything else is
//     provenance for humans and the lake's canon layer.
//   • Emitted YAML mirrors raw-notes/commons/reading/*.md: single-quoted scalars,
//     block sequences, bare ISO date. (Personal notes in the repo also use the
//     inline `tags: [a, b]` form; yaml.safe_load reads both, and one house style
//     beats two.)
//   • A note's FILENAME STEM is its wiki-link id, kebab-case
//     (raw-notes/README.md). So slugs are ids, and ids must not collide.
//   • Personal prose lives flat in raw-notes/<dir>/. The concepts/ entities/
//     summaries/ synthesis/ folders are the REVIEW-GATED canon layer — pipelines
//     propose, curators commit — so Scribe deliberately never targets them.
//   • Shared reading notes live in raw-notes/commons/reading/<source-id>/ and are
//     written by the ingestion pipeline. A member's own reaction to a book stays in
//     their dir and [[links]] to the shared reading (raw-notes/commons/index.md).
//   • Glossary entries are communal: raw-notes/commons/glossary/<term-slug>.md.

/* ---------------------------------- helpers ---------------------------------- */

/** kebab-case slug — the note id. */
export function slugify(input) {
  return String(input || "")
    .toLowerCase()
    .normalize("NFKD")
    .replace(/[̀-ͯ]/g, "") // strip accents
    .replace(/['’"]/g, "")
    .replace(/[^a-z0-9]+/g, "-")
    .replace(/^-+|-+$/g, "")
    .slice(0, 80)
    .replace(/-+$/, "");
}

const p2 = (n) => String(n).padStart(2, "0");

/** `YYYY-MM-DD` in UTC — the shape `last_updated` and dated filenames use. */
export function isoDate(d) {
  return `${d.getUTCFullYear()}-${p2(d.getUTCMonth() + 1)}-${p2(d.getUTCDate())}`;
}

/** Single-quoted YAML scalar (internal single quotes doubled), as commons/ uses. */
function q(s) {
  return `'${String(s ?? "").replace(/'/g, "''")}'`;
}

/** A YAML block sequence: `key:` then `- 'item'` lines. Omitted when empty. */
function seq(key, items) {
  const list = (items || []).map((s) => String(s).trim()).filter(Boolean);
  if (!list.length) return [];
  return [`${key}:`, ...list.map((i) => `- ${q(i)}`)];
}

/** Normalise a free-text tag field into clean, kebab-ish tags. */
export function parseTags(input) {
  const raw = Array.isArray(input) ? input : String(input || "").split(/[,\n]/);
  const seen = new Set();
  const out = [];
  for (const t of raw) {
    const v = String(t).trim().replace(/^#/, "");
    if (!v) continue;
    const key = v.toLowerCase();
    if (seen.has(key)) continue;
    seen.add(key);
    out.push(v);
  }
  return out;
}

/** Every `[[wiki-link]]` id in a body (anchors/aliases stripped, same regex the
 *  parquet pipeline uses so what we validate is what the lake will resolve). */
export function extractWikiLinks(text) {
  const re = /\[\[([^\]\|#]+?)(?:[#\|][^\]]*)?\]\]/g;
  const out = new Set();
  let m;
  while ((m = re.exec(String(text || "")))) out.add(m[1].trim());
  return [...out];
}

/** Reject anything that could escape the note tree before it reaches GitHub. */
export function assertSafePath(path) {
  const p = String(path || "");
  if (!p.startsWith("raw-notes/")) throw new Error(`refusing to write outside raw-notes/: ${p}`);
  if (p.includes("..") || p.includes("//") || p.startsWith("/")) throw new Error(`unsafe path: ${p}`);
  if (!p.endsWith(".md")) throw new Error(`notes must be .md files: ${p}`);
  return p;
}

export const GLOSSARY_DIR = "raw-notes/commons/glossary";
export const GLOSSARY_STATUSES = ["seed", "developing", "settled"];
export const NOTE_TYPES = ["book", "glossary", "observation", "link"];

// The canon layer. raw-notes/README.md: these folders hold "hand-written canon
// (wiki) proposals — the reviewed layer", and "Hand-written canon pages follow the
// same path: open a PR, a curator reviews and merges." Scribe never creates into
// them, and it will not direct-commit an edit to one either — it shows the diff so
// the member can take it to a PR. Prose capture is the job; the review gate is not
// Scribe's to open.
export const CANON_DIRS = ["concepts", "entities", "summaries", "synthesis"];

/** Is this path in the review-gated canon layer? (raw-notes/<who>/<canon>/…) */
export function isCanonPath(path) {
  const parts = String(path || "").split("/");
  return parts.length > 3 && parts[0] === "raw-notes" && CANON_DIRS.includes(parts[2]);
}

/* --------------------------------- builders ---------------------------------- */

/**
 * buildNote — payload → { path, markdown, commitMessage, meta }.
 *
 * payload = {
 *   type: "book" | "glossary" | "observation" | "link",
 *   title, body, summary, tags,            // common
 *   sourceId, readingNotes[],              // book
 *   term, aliases, status,                 // glossary
 *   connects[],                            // link
 *   slug?, now?                            // overrides (now = ISO string, for tests)
 * }
 * identity = the resolved member record from lib/identity.js.
 */
export function buildNote(payload, identity) {
  const type = NOTE_TYPES.includes(payload.type) ? payload.type : "observation";
  const now = payload.now ? new Date(payload.now) : new Date();
  const today = isoDate(now);
  const dir = identity.dir;
  const handle = identity.handle;
  const tags = parseTags(payload.tags);
  const summary = String(payload.summary || "").trim();
  const prose = String(payload.body || "").trim();

  if (type === "glossary") return buildGlossary({ payload, identity, now, today, tags, summary, prose });

  const title = String(payload.title || "").trim();
  if (!title) throw new Error("a title is required — it becomes the note's H1 and its wiki-link id");

  const stem = slugify(payload.slug || title);
  if (!stem) throw new Error(`"${title}" does not reduce to a usable filename`);

  const fm = ["---"];
  if (summary) fm.push(`summary: ${q(summary)}`);

  const bodyParts = [`# ${title}`, ""];
  let path;
  let commitMessage;
  const meta = { type, handle, dir, stem, title, tags };

  if (type === "book") {
    const sourceId = slugify(payload.sourceId || "");
    if (!sourceId) throw new Error("pick a book — a book note records which source it is about");
    // The source-id joins this note to the shared reading in commons/reading/, the
    // same way commons reading notes carry `source:`.
    const autoTags = tags.includes(sourceId) ? tags : [sourceId, ...tags];
    meta.tags = autoTags;
    meta.sourceId = sourceId;
    fm.push(...seq("tags", autoTags));
    fm.push(`last_updated: ${today}`);
    fm.push(`source: ${q(sourceId)}`);
    const reading = (payload.readingNotes || []).map((s) => String(s).trim()).filter(Boolean);
    if (reading.length) fm.push(...seq("reads", reading));
    fm.push("---");

    path = `raw-notes/${dir}/${stem}.md`;
    if (prose) bodyParts.push(prose, "");
    if (reading.length) {
      // Wiki-links live in the BODY because that is where the lake reads edges from
      // (notes_to_parquet.py scans the body, not the frontmatter).
      bodyParts.push("## Reading", "");
      for (const r of reading) bodyParts.push(`- [[${r}]]`);
      bodyParts.push("");
    }
    commitMessage = `[trivial] notes(${handle}): ${title} — reading note on ${sourceId}`;
  } else if (type === "link") {
    const connects = (payload.connects || []).map((s) => String(s).trim()).filter(Boolean);
    if (!connects.length) throw new Error("a link note needs at least one note to connect");
    meta.connects = connects;
    fm.push(...seq("tags", tags));
    fm.push(`last_updated: ${today}`);
    // `connects:` is the shape commons canon pages use for their outbound edges.
    fm.push(...seq("connects", connects));
    fm.push("---");

    path = `raw-notes/${dir}/${stem}.md`;
    if (prose) bodyParts.push(prose, "");
    bodyParts.push("## Connects", "");
    for (const c of connects) bodyParts.push(`- [[${c}]]`);
    bodyParts.push("");
    commitMessage = `[trivial] notes(${handle}): ${title} — connects ${connects.length} note${connects.length === 1 ? "" : "s"}`;
  } else {
    // observation — quick capture, dated filename so the day it was thought survives
    // even when the title is vague.
    fm.push(...seq("tags", tags));
    fm.push(`last_updated: ${today}`);
    fm.push("---");
    path = `raw-notes/${dir}/${today}-${stem}.md`;
    meta.stem = `${today}-${stem}`;
    if (prose) bodyParts.push(prose, "");
    commitMessage = `[trivial] notes(${handle}): ${title}`;
  }

  const markdown = `${fm.join("\n")}\n\n${bodyParts.join("\n").replace(/\n+$/, "")}\n`;
  meta.wikiLinks = extractWikiLinks(markdown);
  return { path: assertSafePath(path), markdown, commitMessage, meta };
}

/**
 * Glossary entries are COMMUNAL (raw-notes/commons/glossary/<term-slug>.md), so the
 * author is recorded in `contributors:` rather than by which directory the file sits
 * in. `status` tracks how settled the definition is: seed → developing → settled.
 */
function buildGlossary({ payload, identity, today, tags, summary, prose }) {
  const term = String(payload.term || payload.title || "").trim();
  if (!term) throw new Error("a glossary entry needs a term");
  const stem = slugify(payload.slug || term);
  if (!stem) throw new Error(`"${term}" does not reduce to a usable filename`);
  const status = GLOSSARY_STATUSES.includes(payload.status) ? payload.status : "seed";
  const aliases = parseTags(payload.aliases);
  const contributors = parseTags(payload.contributors);
  if (!contributors.includes(identity.handle)) contributors.push(identity.handle);
  const glossTags = tags.includes("glossary") ? tags : ["glossary", ...tags];

  const fm = ["---"];
  fm.push(`term: ${q(term)}`);
  if (aliases.length) fm.push(...seq("aliases", aliases));
  fm.push(`status: ${status}`);
  fm.push(...seq("contributors", contributors));
  if (summary) fm.push(`summary: ${q(summary)}`);
  fm.push(...seq("tags", glossTags));
  fm.push(`last_updated: ${today}`);
  fm.push("---");

  const body = [`# ${term}`, ""];
  if (prose) body.push(prose, "");

  const markdown = `${fm.join("\n")}\n\n${body.join("\n").replace(/\n+$/, "")}\n`;
  const path = assertSafePath(`${GLOSSARY_DIR}/${stem}.md`);
  return {
    path,
    markdown,
    commitMessage: `[trivial] glossary: ${term} (${status}) by ${identity.handle}`,
    meta: {
      type: "glossary",
      handle: identity.handle,
      dir: "commons",
      stem,
      title: term,
      term,
      status,
      aliases,
      contributors,
      tags: glossTags,
      wikiLinks: extractWikiLinks(markdown),
    },
  };
}

/* ----------------------------- edit an existing note --------------------------- */

/** Split a note into its frontmatter block (without the `---` fences) and body. */
export function splitNote(markdown) {
  const text = String(markdown || "");
  const m = text.match(/^---[ \t]*\r?\n([\s\S]*?)\r?\n---[ \t]*\r?\n?/);
  if (!m) return { fm: null, body: text };
  return { fm: m[1], body: text.slice(m[0].length) };
}

/** Read the few frontmatter fields the editor exposes, plus the H1 title. */
export function parseNote(markdown) {
  const { fm, body } = splitNote(markdown);
  const block = fm || "";
  const h1 = body.match(/^#\s+(.+?)\s*$/m);
  const summary = unquoteYaml((block.match(/^summary:[ \t]*(.*)$/m) || [, ""])[1]);

  const tags = [];
  const inline = block.match(/^tags:[ \t]*\[(.*)\][ \t]*$/m);
  if (inline) {
    for (const t of inline[1].split(",")) {
      const v = unquoteYaml(t);
      if (v) tags.push(v);
    }
  } else {
    let inTags = false;
    for (const line of block.split(/\r?\n/)) {
      if (/^tags:[ \t]*$/.test(line)) { inTags = true; continue; }
      if (!inTags) continue;
      const li = line.match(/^[ \t]*-[ \t]+(.*)$/);
      if (li) { const v = unquoteYaml(li[1]); if (v) tags.push(v); continue; }
      if (line.trim()) break;
    }
  }

  return {
    hasFrontmatter: fm !== null,
    frontmatter: block,
    body: body.replace(/\s+$/, ""),
    title: h1 ? h1[1].trim() : "",
    summary,
    tags,
    wikiLinks: extractWikiLinks(body),
  };
}

function unquoteYaml(v) {
  let s = String(v == null ? "" : v).trim();
  if (s.length >= 2 && s[0] === '"' && s.at(-1) === '"') return s.slice(1, -1).replace(/\\"/g, '"');
  if (s.length >= 2 && s[0] === "'" && s.at(-1) === "'") return s.slice(1, -1).replace(/''/g, "'");
  return s;
}

/**
 * Replace ONE key in a frontmatter block, leaving every other line byte-identical.
 * `lines` is the replacement rendering (e.g. ["tags:", "- 'a'"]); an empty array
 * deletes the key. Handles both scalar keys and block sequences; appends when absent.
 *
 * Editing must not be lossy: commons reading notes carry `cites:`, `spans:`, `level:`
 * and `source:` that the ingestion pipeline resolved against a pinned extraction.
 * Round-tripping through a YAML dumper would reorder and requote all of it, so the
 * editor rewrites only the fields it actually shows and never touches the rest.
 */
function replaceKey(block, key, lines) {
  const src = block.split(/\r?\n/);
  const out = [];
  let i = 0;
  let replaced = false;
  const keyRe = new RegExp(`^${key}:(?:[ \\t]|$)`);
  while (i < src.length) {
    if (keyRe.test(src[i])) {
      const isBlock = /^[A-Za-z0-9_]+:[ \t]*$/.test(src[i]);
      i++;
      if (isBlock) while (i < src.length && /^[ \t]*-[ \t]+/.test(src[i])) i++;
      out.push(...lines);
      replaced = true;
      continue;
    }
    out.push(src[i]);
    i++;
  }
  if (!replaced && lines.length) out.push(...lines);
  return out.filter((l, idx, arr) => !(l === "" && idx === arr.length - 1)).join("\n");
}

/**
 * updateNote — rewrite an existing note for the edit flow.
 *
 * original: the file's current text (from GitHub).
 * changes:  { body?, summary?, tags?, touchDate? } — only the provided keys change.
 * Returns { markdown, changed, wikiLinks }.
 */
export function updateNote(original, changes = {}, now = new Date()) {
  const { fm, body } = splitNote(original);
  let block = fm === null ? "" : fm;

  if (typeof changes.summary === "string") {
    const s = changes.summary.trim();
    block = replaceKey(block, "summary", s ? [`summary: ${q(s)}`] : []);
  }
  if (changes.tags !== undefined) {
    block = replaceKey(block, "tags", seq("tags", parseTags(changes.tags)));
  }
  if (changes.touchDate !== false) {
    block = replaceKey(block, "last_updated", [`last_updated: ${isoDate(now)}`]);
  }

  const newBody = typeof changes.body === "string" ? changes.body.replace(/\s+$/, "") + "\n" : body;
  const markdown = block.trim() ? `---\n${block.trim()}\n---\n\n${newBody.replace(/^\n+/, "")}` : newBody;
  return { markdown, changed: markdown !== String(original), wikiLinks: extractWikiLinks(markdown) };
}

/** Commit message for an edit. Always `[trivial]` — raw-notes-only edits land on main. */
export function editCommitMessage(path, identity) {
  const stem = path.split("/").pop().replace(/\.md$/, "");
  const where = path.startsWith(`${GLOSSARY_DIR}/`) ? "glossary" : `notes(${identity.handle})`;
  return `[trivial] ${where}: edit ${stem}`;
}
