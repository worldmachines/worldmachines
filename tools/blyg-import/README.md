# blyg-import

Publishes the repo's notes (`raw-notes/**/*.md` and `wiki/**/*.md`) as items on the
World Machines blyg (<https://blyg.worldmachines.org/>, Blygger Studio v0.49.1).
Each note's `[[wikilinks]]` become blyg internal links (`[[id | text]]`), so the
notes are cross-referenced on the blyg. Python 3 standard library only.

It is a **dry run unless you pass `--execute`**, and it is safe to run again: a re-run
writes only the notes that changed.

```sh
# Dry run: corpus statistics, the plan, and a sample of transformed notes. No network.
python3 tools/blyg-import/blyg_import.py
python3 tools/blyg-import/blyg_import.py --report /tmp/blyg-report.json   # full unresolved/collision lists

# First real slice: 50 notes, published.
export BLYG_TOKEN=...            # Studio → More → Client access → REST API, scopes owner:read, owner:draft, owner:publish
python3 tools/blyg-import/blyg_import.py --execute --publish --limit 50 --only 'raw-notes/commons/glossary/*' --only 'raw-notes/commons/reading/more-utopia/*' --only 'raw-notes/commons/reading/voltaire-candide/*'

# Everything (about 2,600 items; roughly 1.5–2 hours at the delegated write budget).
python3 tools/blyg-import/blyg_import.py --execute --publish

# After editing authors.json (e.g. adding someone's blyg URL):
python3 tools/blyg-import/blyg_import.py --execute --update-attribution

# Tests
python3 -m unittest discover -s tools/blyg-import/tests
```

## Files

| File | What |
|---|---|
| `blyg_import.py` | CLI, sync engine, state file, statistics |
| `corpus.py` | Parsing, link resolution, rendering, splitting (no network) |
| `blyg_client.py` | The only HTTP code: three Studio calls, pacing, 429 back-off |
| `config.json` | Globs, item kind, size budget, write pacing, publish notes |
| `authors.json` | `raw-notes/<dir>` → `{name, blyg}`, plus handle → dir (`vgr` → `venkat`). Names only, never emails |
| `state.json` | Created by `--execute`: note key → `{id, content_sha, byline_sha, published_version, published_sha}`. Commit it after a real run so the next run (from any machine) updates the same items instead of creating new ones |

## Flags

| Flag | Effect |
|---|---|
| `--dry-run` | Default. No writes; prints stats, plan and `--sample N` transformed notes (ids in the sample are stand-ins) |
| `--execute` | Write to the blyg. Needs `BLYG_TOKEN` |
| `--publish` | Publish items. Without it, items are created or updated as drafts only |
| `--limit N` | First N selected notes, in path order |
| `--only GLOB` | Notes whose repo path matches (repeatable, fnmatch, `*` crosses `/`) |
| `--update-attribution` | Only items whose byline changed since the last write; republishes those already published |
| `--state PATH` | State file (default `tools/blyg-import/state.json`). A state file is bound to one API base and refuses another |
| `--api-base URL` | Overrides `BLYG_API_BASE` and `config.json` (default `https://blyg.worldmachines.org/api`; an open Studio PR moves `/api` under the mount) |
| `--interval S` | Seconds between writes (default 1.1) |
| `--report PATH` | Full statistics as JSON |

## What a note becomes

```
# <title>                         ← frontmatter title/term, else first H1, else the filename
                                     (Studio uses a leading H1 as the item's link text)
*By [Name](blyg-url)*             ← or *By Name* when blyg is null; omitted for shared notes
Part 2 of 3. Previous: … Next: …  ← only for split notes
<body>                            ← frontmatter stripped, the leading H1 removed (it is the title)
---
**Connects:** … · **Supports:** … ← frontmatter connects/supports/contradicts, as links
```

* **Kind.** Items are created as `thread`. Studio caps a *fragment* at 1,000 characters
  (`FRAGMENT_MAX_CHARS`, enforced at publish); threads have no Studio cap, and a thread with
  no `![[…]]` directive is valid.
* **Attribution.** `raw-notes/<dir>/…` is attributed to that collaborator through
  `authors.json`. `raw-notes/commons/contributions/…` (member essays) is attributed by the
  frontmatter `author:` handle. Other commons notes, `wiki/` and top-level files get no byline.
  Unknown dirs/handles get none. To point a byline at someone's blyg later, set `blyg` and run
  `--update-attribution`.
* **Links.** `[[target]]`, `[[target|alias]]`, `[[target#heading]]` (and links wrapped onto a
  second line) resolve by filename basename (case-insensitive), then frontmatter/H1 title and
  aliases, then a punctuation-insensitive slug. Essay mirrors titled "X (part 1 of N)" also
  answer to "X". When several notes share a name: same directory, then the same top-level
  author dir, then commons, then path order; every such case is printed. A resolved link becomes
  `[[id | text]]`, where text is the alias, or the target as written (Studio's grammar supports
  the label, decision #70). `#heading` is dropped (blyg links name items, not anchors). A link to
  a split note goes to part 1. Unresolved and self links become plain text.
* **Other syntax.** Link syntax inside code spans and fenced blocks is left alone (blyg treats it
  as literal too). `![[file.png]]`-style embeds become an "embedded file not imported" note;
  `![[note]]` becomes a plain link, never a transclusion. Literal `[TK]`, `[/TK]`, `[=]` (Studio's
  generation grammar, which would fail publish) are backslash-escaped. The corpus currently has
  no embeds and no TK tokens.
* **Splitting.** A note whose rendered text would exceed `max_chars` (100,000) is split at
  paragraph boundaries (never inside a code fence) into numbered parts that link to each other.
  Part 1 keeps the note's key, so links and state survive a later split.
* **Empty files** (8 empty Obsidian stubs today) are skipped.

## Order of operations, and why

Studio resolves `[[id]]` **at publish time, not when the draft is saved**
(`src/model.ts` `publish()` → `resolveInternalLinks` → `resolveTarget`, `src/transclusion.ts`):

* `PATCH /items/{id}` does not look at links, so a draft may contain `[[id]]` pointing at
  another draft.
* At publish, a target that is a draft fails with "item is a draft, not published"; a withdrawn
  target fails too. Any failure aborts the whole publish (`TransclusionResolveError`) and nothing
  is written. Spec 0.4 §10.1: an unresolvable link MUST be a publish error.
* Links do not check for cycles (only thread transclusion does), so mutual links are fine once
  both items are published.

So the importer:

1. creates every missing item, targets first (DFS post-order over the link graph), each draft
   already linking the items created before it;
2. publishes in the same order, writing a link only when its target is already published
   (others are plain text for now);
3. runs a second round that republishes only the items that had a deferred link (link cycles,
   and the previous/next links between parts). In the test slice that was 2 of 38 items.

A re-run renders every selected note against the current state and writes only what differs.
Notes outside `--only`/`--limit` that a selected note links to are linked if they already have a
published item, else written as plain text and upgraded when a later run publishes them.

State is written (atomically) after every successful call. If a run dies, run it again. The one
gap: a create whose response is lost (network drop after the server committed) leaves an
orphan draft, so creates are never retried blind.

## Limits

* **Item size.** No `content_md` length limit in the API schema for threads. The owner API body
  limit is 8 MiB (`API_BODY_LIMIT`). Each version row stores both markdown and HTML in D1, whose
  row limit is about 2 MB, hence the 100,000-character budget. One note splits today
  (`raw-notes/aneesh/index.md`, 155 KB → 3 parts).
* **Rate.** Owner writes are 120/minute (`API_WRITE_LIMIT`); a token (delegated grant) gets 120/minute
  per grant but **60/minute shared by every grant** (`API_DELEGATED_WRITE_LIMIT`); reads 1,200 and
  600. `src/security-budgets.ts`, `docs/api.md`. Writes are paced at 1.1 s, and a 429's
  `Retry-After` is honoured (the local test hit one and resumed). Expect about 2 writes per
  note: ~5,200 writes, about 1.5–2 hours for the whole corpus.
* **Token** lifetime is 30 days (manual tokens have no refresh).

## The public feed

There is no way to publish quietly. Checked in Studio v0.49.1:

* **No backdating.** `published_at` is the server clock (`nowIso()` in `publish()`), and the
  publish body takes only `note`, `note_generated` and `change_category`.
* **No "don't announce" or unlisted flag.** Every publish is a version event. `feed.xml` carries
  the last 50 version events (`FEED_WINDOW`), so after an import the RSS feed is entirely
  imported notes, and every republish (including the second round and `--update-attribution`)
  is a new event.
* **Home page order** (`feed_order` setting, migration 0029; `PATCH /settings`, needs
  `owner:manage`): `pace-layered` (the default for fresh installs) or `reverse-chronological`
  (kept for nodes that had published before 0029). Either way the home page shows 100 cards
  (`FEED_PAGE_SIZE`). Under pace-layered, each new item enters at depth 0 and sinks the others, so
  2,600 imports bury existing posts there too.
* **A static front page** (Settings, `src/front-page.ts`) can put one chosen thread at the mount
  root, so the stream of imports lives at `/posts/` instead of the landing page. It does not
  change `feed.xml`.
* Links between our own items send no mentions (`remoteReferences` covers other origins only).

## Testing against a local Studio

What was done to prove this, and how to repeat it:

```sh
git clone --branch v0.49.1 --depth 1 <blygger-studio> studio && cd studio
npm install --legacy-peer-deps && npm run build
printf 'OWNER_PASSWORD=...\nCOOKIE_SECRET=...\n' > .dev.vars      # no AI binding: wrangler.jsonc has none by default
npx wrangler d1 migrations apply DB --local
npx wrangler dev --local --port 8799
# log in, then mint a REST token with the owner cookie:
curl -c jar -d 'password=...&return_to=/studio' http://127.0.0.1:8799/studio/login
curl -b jar -H 'Content-Type: application/json' -H 'Origin: http://127.0.0.1:8799' \
  -d '{"name":"import","scope":["owner:read","owner:draft","owner:publish"],"resource":"api"}' \
  http://127.0.0.1:8799/api/authorizations          # → access_token
BLYG_TOKEN=... python3 tools/blyg-import/blyg_import.py --execute --publish \
  --api-base http://127.0.0.1:8799/api --state /tmp/local-state.json --interval 0.5 --only '...'
```

Then fetch `/items/<id>.json` and `/t/<id>/` for each item in the state file and check that
every `[[id]]` became an `<a href=".../t/<id>/">` whose page answers 200.
