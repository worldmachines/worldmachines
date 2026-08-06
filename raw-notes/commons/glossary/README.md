# The glossary — where the club builds its own definitions

This folder is the club's **shared vocabulary**: the terms our theories run on,
defined the way *we* use them. It is not a dictionary of received meanings. An
entry starts as somebody's rough take, gets argued with, and gets sharper — the
definition is a work in progress and the file says so out loud.

Published at **[worldmachines.org/wiki/glossary/](https://worldmachines.org/wiki/glossary/)**.
Every note anywhere in `raw-notes/` that wiki-links a term shows up as a
backlink on that term's page, so a glossary entry doubles as an index of where
the concept is actually being used.

## The rules

1. **One term per file.** Filename is kebab-case; the filename stem is the
   term's wiki-link id, so `world-machine.md` is linked as `[[world-machine]]`.
2. **Say what we mean, not what a dictionary means.** If the club's usage
   diverges from the standard one — and it usually does — the entry's job is to
   name the divergence.
3. **Cite the notes.** Link the notes and readings the definition came out of
   with `[[note-id]]`. Wiki-links resolve by exact, case-sensitive filename
   stem, so `[[The Thicket]]` and `[[the-thicket]]` are *not* the same link.
4. **Disagreement is content.** If two members use a term differently, write
   both readings into the entry under an "Open questions" or "Contested"
   heading. Do not average them into mush.
5. **Move the status forward, never silently.** Promoting `seed` →
   `developing` → `settled` is an editorial claim; make it in a PR someone can
   object to.
6. **Prose only.** Same rule as the rest of `raw-notes/`: no source text pasted
   in. Quote sparingly and attribute.

## Adding a term

Copy this template into `raw-notes/commons/glossary/<your-term>.md`:

```markdown
---
term: Your Term
aliases: ['Your Term', 'Alternate Spelling']
status: seed
contributors: [yourhandle]
summary: "One sentence a newcomer could read and not be lost."
last_updated: 2026-08-05
---

# Your Term

## Definition

> The one-or-two-sentence version, quotable and blunt.

Then the paragraph that unpacks it.

## Where it comes from

Which reading or note put this term into play — `[[note-id]]` links.

## How the club uses it

The distinctions that matter in practice; the near-misses it is not.

## Open questions

What is still unsettled. This section is a feature.
```

### Frontmatter fields

| Field | Required | Meaning |
| --- | --- | --- |
| `term` | yes | Display name of the term. |
| `aliases` | no | Other exact spellings that should resolve to this entry. An alias never overrides a real note with that filename stem — if `Legibility.md` exists, `[[Legibility]]` goes to the note, not here. |
| `status` | yes | `seed` · `developing` · `settled` (below). |
| `contributors` | yes | Handles of the people developing the definition — add yourself when you edit. |
| `summary` | yes | One sentence; it is what the glossary index shows. |
| `last_updated` | yes | ISO date of your edit. |

### The three statuses

- **`seed`** — a first draft, written to be argued with. Nobody has signed off.
- **`developing`** — in active use across several notes, definition still moving.
- **`settled`** — the club has converged; changing it now means changing the theory.

## How an entry evolves

Edit the file, bump `last_updated`, add your handle to `contributors`, and open
a PR. Small PRs, one term each. Anyone in the club may propose; the same review
gate as the rest of the canon applies. Rebuild the published pages with
`npm run build:wiki` and commit the generated HTML alongside your edit.

## Picking a good first term

Look for a phrase you keep typing that has no definition anywhere — check
whether other members are already using it with a slightly different meaning.
Those are the entries worth writing, because writing them settles an argument
nobody had noticed they were having.
