# commons — shared reading notes

AI-ingested reading notes from sources the whole group works through: book-club
books and member-submitted links/articles. Notes here are **communal** — not
owned by any one person. The knowledge lake attributes every note in this tree
to the pseudo-author `commons` (the folder name), instead of an individual.

## Layout

- `reading/<source-slug>/` — L1 reading notes, one file per section (lake level: `reading`)
- `concepts/ · entities/ · summaries/ · synthesis/` — L2 canon derived from these
  sources, when a run builds it (lake level: `canon`)

## Linking from your own notes

Your personal notes stay in `raw-notes/<you>/`. To connect your own thinking to
a shared reading, just wiki-link it — `[[some-source-slug]]` — from anywhere in
your dir. The lake resolves links by note-id regardless of folder, so the edge
lands whether the target lives here or in someone's personal tree.

## How notes get here

The AI ingestion pipeline (see `wm-encyclopedia-kb/docs/INGEST-LOCAL.md` and
`docs/dispatch/prompt-ingest-a-book.md`) writes here when run with
`author_dir: commons`. This `index.md` is excluded from the lake by
`config.yaml` (the `raw-notes/*/index.md` exclude rule), so it is never ingested
as a note.
