# Raw notes — the shared contribution home

Working area for rough notes, reading notes, fragments, questions, meeting
follow-ups, and research dumps. Each person owns `raw-notes/<their-handle>/`
and writes there. One shared area — `raw-notes/commons/` — holds the
**AI-ingested reading notes** for the books and links the whole club works
through; those are communal, not owned by any one person.

## The one rule that matters: prose only, never source text

Everything in `raw-notes/` is **your own writing about** the material —
reading notes, summaries, arguments, questions. The **source text itself
never enters this repo**: not as an appendix, not pasted into a notes file,
not in a PR description. If you want a source retrievable verbatim by the
oracle, send it to the curator privately as a zip bundle — the exact layout
(manifest + source + chunk specs) is in
[RAG-SUBMISSIONS.md §1](https://github.com/worldmachines/wm-encyclopedia-kb/blob/main/docs/RAG-SUBMISSIONS.md).
The curator loads it into the retrieval lake behind the licensing firewall
(open / quotable / private); git never sees it.

## What goes where

```
raw-notes/<you>/            # your personal working area
  *.md                      # free-form notes — no polish required
  concepts/                 # ┐
  entities/                 # │ hand-written canon (wiki) proposals — the
  summaries/                # │ reviewed layer; see "Canon pages are
  synthesis/                # ┘ review-gated" below
  reading/<source-slug>/    # only for genuinely PRIVATE reading you're not
                            # sharing with the club

raw-notes/commons/          # SHARED — the club's communal ingested readings
  reading/<source-slug>/    # L1 reading notes: one note per section of a
                            # source (the ingestion pipelines land output here)
  concepts/ entities/       # ┐ canon derived from those shared sources
  summaries/ synthesis/     # ┘ (same review gate)
```

Everything under `raw-notes/commons/` is attributed to the pseudo-author
`commons` rather than a person — see `raw-notes/commons/index.md`.

Note filenames are kebab-case; a note's filename stem is its wiki-link id
(`[[some-note]]` points at `some-note.md`).

## Canon pages are review-gated

The `concepts/`, `entities/`, `summaries/`, `synthesis/` folders are the
wiki's canon layer — the pages the oracle treats as settled knowledge.
Nothing lands there automatically. The ingestion pipelines (below) generate
canon-page **proposals** as review material attached to a PR; a human
curator reads each proposal and commits only the ones they accept.
Hand-written canon pages follow the same path: open a PR, a curator
reviews and merges.

## Book club → the commons

Reading a book (or a shared link) with the club works in two layers:

- **AI-ingested reading notes** — the automated, section-by-section digestion
  of the source — land in the shared **`raw-notes/commons/reading/<slug>/`**,
  common to everyone, because we all read the same thing. A curator (or the
  ingestion pipeline) produces these; you don't write them by hand.
- **Your own reactions, arguments, and questions** stay under your personal
  folder as prose, and you `[[link]]` them to the shared reading — the lake
  resolves wiki-links by note-id across folders, so the connection lands.

The book's **text never enters git** either way (see the rule above). If the
club wants the book itself retrievable by the oracle, that's a private RAG
bundle to the curator — see
[RAG-SUBMISSIONS.md §1](https://github.com/worldmachines/wm-encyclopedia-kb/blob/main/docs/RAG-SUBMISSIONS.md).
Notes and bundle travel separately by design.

## How notes become wiki + oracle knowledge

- **Hand-written notes**: PR into your folder. AI agents may read them and
  propose wiki updates by PR.
- **Automated reading notes** (a whole paper or book digested into
  `commons/reading/<slug>/`): two pipelines produce the same shape —
  - the **local pipeline**, run as Claude Code agent stages on the
    curator's machine — the step-by-step playbook is
    [INGEST-LOCAL.md](https://github.com/worldmachines/wm-encyclopedia-kb/blob/main/docs/INGEST-LOCAL.md);
  - the **cloud path** ([wm-feeder](https://github.com/worldmachines/wm-feeder)):
    push a source under `raw_sources/` once the feeder workflow is enabled,
    and it opens a PR of reading notes into `raw-notes/commons/`.
- **Canon pages**: always through the review gate above — pipelines
  propose, people approve.

## Do I need other repos checked out?

No — contributing notes needs only this repo, and the guides linked above
are readable on GitHub. You only need local checkouts of
[wm-encyclopedia-kb](https://github.com/worldmachines/wm-encyclopedia-kb)
and [wm-feeder](https://github.com/worldmachines/wm-feeder) if you want to
run the local ingestion pipeline yourself —
[INGEST-LOCAL.md](https://github.com/worldmachines/wm-encyclopedia-kb/blob/main/docs/INGEST-LOCAL.md)
§1 lists its prerequisites.

## Rules

- Each person writes and pushes inside their own directory; `raw-notes/commons/`
  is the one shared area (AI-ingested club readings).
- Notes do not need to be polished.
- Prefer Markdown files with descriptive names.
- Include source links, dates, and context when useful.
- AI agents may read these notes and propose wiki updates by PR.

## GitHub usernames found

Queried GitHub repo collaborators / org members for `worldmachines/worldmachines`:

| Person | GitHub username | Raw notes directory |
| --- | --- | --- |
| Aneesh | `@aneeshsathe` | `aneesh/` |
| Florian | `@florianlohse` | `florian/` |
| Kyle | `@KyleAMathews` | `kyle/` |
| Venkat | `@vgururao` | `venkat/` |
| Ivo | TBD — not currently a repo/org member | `ivo/` |
| Patrick | TBD — not currently a repo/org member | `patrick/` |
| Sean | TBD — not currently a repo/org member | `sean/` |

## Directories

- `commons/` — **shared**: AI-ingested club readings (pseudo-author `commons`)
- `aneesh/`
- `florian/`
- `ivo/`
- `kyle/`
- `patrick/`
- `sean/`
- `venkat/`
