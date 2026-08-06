// notes.test.mjs — the note builders are the part that must be exactly right, so
// they are pure functions with no Worker dependencies and are tested with plain node:
//
//     node apps/scribe/test/notes.test.mjs
//
// Every assertion is about a repo convention (path shape, frontmatter key, wiki-link
// placement, [trivial] commit prefix, non-lossy edits), not about implementation
// detail — these are the things a refactor must not quietly break.

import assert from "node:assert/strict";
import {
  buildNote,
  updateNote,
  parseNote,
  extractWikiLinks,
  slugify,
  assertSafePath,
  editCommitMessage,
} from "../src/lib/notes.js";

const NOW = "2026-08-05T09:30:00Z";
const me = { handle: "aneesh", dir: "aneesh", name: "Aneesh Sathe", email: "a@example.com" };
const vgr = { handle: "vgr", dir: "venkat", name: "Venkat Rao", email: "v@example.com" };

let passed = 0;
const test = (name, fn) => {
  try {
    fn();
    passed++;
  } catch (err) {
    console.error(`✗ ${name}\n  ${err.message}`);
    process.exitCode = 1;
  }
};

/* ------------------------------------ book ------------------------------------ */

test("book note lands flat in the member's dir with source frontmatter", () => {
  const n = buildNote(
    {
      type: "book",
      title: "Scarcity is the baseline, not the exception",
      sourceId: "appleby-relentless-revolution",
      summary: "Appleby's delay puzzle read against the medieval machine.",
      tags: "capitalism, scarcity",
      body: "The interesting question is the four-thousand-year wait.",
      readingNotes: ["appleby-relentless-revolution-ch01-puzzle-of-capitalism"],
      now: NOW,
    },
    me
  );
  assert.equal(n.path, "raw-notes/aneesh/scarcity-is-the-baseline-not-the-exception.md");
  assert.ok(n.markdown.startsWith("---\nsummary: 'Appleby''s delay puzzle"), "apostrophes are YAML-escaped by doubling");
  assert.ok(n.markdown.includes("source: 'appleby-relentless-revolution'"));
  assert.ok(n.markdown.includes("- 'appleby-relentless-revolution'"), "source-id is auto-tagged");
  assert.ok(n.markdown.includes("last_updated: 2026-08-05"));
  assert.ok(n.markdown.includes("[[appleby-relentless-revolution-ch01-puzzle-of-capitalism]]"));
  assert.ok(n.commitMessage.startsWith("[trivial] "), "commit message must start with [trivial]");
  assert.equal(n.meta.wikiLinks.length, 1);
});

test("book note requires a source", () => {
  assert.throws(() => buildNote({ type: "book", title: "x", now: NOW }, me), /pick a book/);
});

/* ---------------------------------- glossary ---------------------------------- */

test("glossary entry is communal and carries term/status/contributors", () => {
  const n = buildNote(
    {
      type: "glossary",
      term: "Legibility Machine",
      aliases: "legibility-machine, legibility machines",
      status: "developing",
      summary: "A machine whose output is a readable state of the world.",
      body: "Working definition.",
      now: NOW,
    },
    vgr
  );
  assert.equal(n.path, "raw-notes/commons/glossary/legibility-machine.md");
  assert.ok(n.markdown.startsWith("---\nterm: 'Legibility Machine'\n"));
  assert.ok(n.markdown.includes("status: developing"));
  assert.ok(n.markdown.includes("contributors:\n- 'vgr'"), "author recorded in contributors, not by directory");
  assert.ok(n.markdown.includes("- 'glossary'"), "glossary tag is added automatically");
  assert.ok(n.markdown.includes("\n\n# Legibility Machine\n"));
  assert.ok(n.commitMessage.startsWith("[trivial] glossary: Legibility Machine (developing)"));
});

test("glossary status falls back to seed", () => {
  const n = buildNote({ type: "glossary", term: "Thing", status: "bogus", now: NOW }, me);
  assert.ok(n.markdown.includes("status: seed"));
});

/* --------------------------------- observation -------------------------------- */

test("observation gets a dated filename in the member's dir", () => {
  const n = buildNote({ type: "observation", title: "Clocks before factories", body: "Landes again.", now: NOW }, me);
  assert.equal(n.path, "raw-notes/aneesh/2026-08-05-clocks-before-factories.md");
  assert.ok(n.markdown.includes("# Clocks before factories"));
  assert.equal(n.commitMessage, "[trivial] notes(aneesh): Clocks before factories");
});

test("vgr's notes go to raw-notes/venkat/", () => {
  const n = buildNote({ type: "observation", title: "Prime radiant redux", now: NOW }, vgr);
  assert.equal(n.path, "raw-notes/venkat/2026-08-05-prime-radiant-redux.md");
});

/* ------------------------------------ link ------------------------------------ */

test("link note writes connects: frontmatter AND body wiki-links", () => {
  const n = buildNote(
    {
      type: "link",
      title: "Legibility runs through both",
      connects: ["dante-legible-cosmos", "the-legible-commonwealth"],
      body: "Two readings, one mechanism.",
      now: NOW,
    },
    me
  );
  assert.equal(n.path, "raw-notes/aneesh/legibility-runs-through-both.md");
  assert.ok(n.markdown.includes("connects:\n- 'dante-legible-cosmos'"));
  // The lake reads edges out of the BODY, so the links must appear there too.
  assert.ok(n.markdown.includes("- [[dante-legible-cosmos]]"));
  assert.ok(n.markdown.includes("- [[the-legible-commonwealth]]"));
  assert.deepEqual(n.meta.wikiLinks.sort(), ["dante-legible-cosmos", "the-legible-commonwealth"]);
});

test("link note needs at least one connection", () => {
  assert.throws(() => buildNote({ type: "link", title: "x", now: NOW }, me), /at least one note/);
});

/* ------------------------------------ edit ------------------------------------ */

const EXISTING = `---
summary: 'Old summary.'
tags:
- 'capitalism-origins'
- 'england'
last_updated: 2026-07-19
level: reading
source: 'appleby-relentless-revolution'
cites:
- 'appleby-relentless-revolution#u01-c1'
---

# The Puzzle Is Delay

Original prose.
`;

test("edit rewrites only the fields the editor shows", () => {
  const { markdown } = updateNote(
    EXISTING,
    { body: "# The Puzzle Is Delay\n\nRevised prose with [[modernity-machine]].", summary: "New summary.", tags: "capitalism-origins, delay" },
    new Date(NOW)
  );
  assert.ok(markdown.includes("summary: 'New summary.'"));
  assert.ok(markdown.includes("- 'delay'"));
  assert.ok(markdown.includes("last_updated: 2026-08-05"), "last_updated is touched");
  // Everything the ingestion pipeline resolved must survive byte-identical.
  assert.ok(markdown.includes("level: reading"));
  assert.ok(markdown.includes("source: 'appleby-relentless-revolution'"));
  assert.ok(markdown.includes("cites:\n- 'appleby-relentless-revolution#u01-c1'"));
  assert.ok(markdown.includes("Revised prose"));
  assert.ok(!markdown.includes("Original prose"));
});

test("edit with no changes is a no-op apart from the date", () => {
  const { markdown } = updateNote(EXISTING, { touchDate: false });
  assert.equal(markdown, EXISTING);
});

test("parseNote recovers the editor's fields", () => {
  const p = parseNote(EXISTING);
  assert.equal(p.title, "The Puzzle Is Delay");
  assert.equal(p.summary, "Old summary.");
  assert.deepEqual(p.tags, ["capitalism-origins", "england"]);
});

test("editing a note with no frontmatter still works", () => {
  const { markdown } = updateNote("# Bare note\n\nNo frontmatter here.\n", { body: "# Bare note\n\nEdited." }, new Date(NOW));
  assert.ok(markdown.startsWith("---\nlast_updated: 2026-08-05\n---\n\n# Bare note"));
});

test("edit commit messages are [trivial] and name the file", () => {
  assert.equal(editCommitMessage("raw-notes/aneesh/history-machine.md", me), "[trivial] notes(aneesh): edit history-machine");
  assert.equal(editCommitMessage("raw-notes/commons/glossary/world-machine.md", me), "[trivial] glossary: edit world-machine");
});

/* ----------------------------------- guards ----------------------------------- */

test("paths outside raw-notes/ are refused", () => {
  assert.throws(() => assertSafePath("website/index.html"), /outside raw-notes/);
  assert.throws(() => assertSafePath("raw-notes/../website/x.md"), /unsafe path/);
  assert.throws(() => assertSafePath("raw-notes/aneesh/x.txt"), /\.md files/);
  assert.equal(assertSafePath("raw-notes/aneesh/x.md"), "raw-notes/aneesh/x.md");
});

test("slugify produces wiki-link ids", () => {
  assert.equal(slugify("Einfühlung & the “Machine”"), "einfuhlung-the-machine");
  assert.equal(slugify("  --Hello, World!--  "), "hello-world");
});

test("extractWikiLinks strips anchors and aliases", () => {
  assert.deepEqual(extractWikiLinks("see [[a-note#section]] and [[b-note|B]] and [[a-note]]").sort(), ["a-note", "b-note"]);
});

console.log(`${passed} passing${process.exitCode ? " (with failures above)" : ""}`);
