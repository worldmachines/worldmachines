# Raw notes — the shared contribution home

Working area for rough notes, reading notes, fragments, questions, meeting
follow-ups, and research dumps. Each person owns `raw-notes/<their-handle>/`
and writes only there.

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
raw-notes/<you>/
  *.md                      # free-form notes — no polish required
  reading/<source-slug>/    # L1 reading notes: one note per section of a
                            # source (ingestion pipelines land output here)
  concepts/                 # ┐
  entities/                 # │ canon (wiki) pages — the reviewed layer;
  summaries/                # │ see "Canon pages are review-gated" below
  synthesis/                # ┘
```

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

## Book club → book notes

Reading a book with the club? Write your notes as prose under your own
folder — a single `raw-notes/<you>/book-notes/<book-slug>.md`, or a
`reading/<book-slug>/` folder with one note per chapter if you're being
thorough. Your reactions, arguments, and questions belong here; the book's
text does not (see the rule above). If the club wants the book itself in
the oracle's retrieval layer, that's a private RAG bundle to the curator —
see [RAG-SUBMISSIONS.md §1](https://github.com/worldmachines/wm-encyclopedia-kb/blob/main/docs/RAG-SUBMISSIONS.md).
Notes and bundle travel separately by design.

## How notes become wiki + oracle knowledge

- **Hand-written notes**: PR into your folder. AI agents may read them and
  propose wiki updates by PR.
- **Automated reading notes** (a whole paper or book digested into
  `reading/<slug>/`): two pipelines produce the same shape —
  - the **local pipeline**, run as Claude Code agent stages on the
    curator's machine — the step-by-step playbook is
    [INGEST-LOCAL.md](https://github.com/worldmachines/wm-encyclopedia-kb/blob/main/docs/INGEST-LOCAL.md);
  - the **cloud path** ([wm-feeder](https://github.com/worldmachines/wm-feeder)):
    push a source under `raw_sources/` once the feeder workflow is enabled,
    and it opens a PR of reading notes back into your folder.
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

- Each person writes and pushes only inside their own directory.
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

- `aneesh/`
- `florian/`
- `ivo/`
- `kyle/`
- `patrick/`
- `sean/`
- `venkat/`
