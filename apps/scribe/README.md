# Scribe — note capture for the World Machines book club

A mobile-first, installable **PWA + Cloudflare Worker** for writing notes into this
repo's `raw-notes/` tree from a phone. Every member captures into **their own**
directory; the glossary is shared.

Lives under `apps/scribe/` — a new top-level app directory, so nothing in
`website/`, `wiki/` or `raw-notes/` is affected by it existing.

Design notes and the reasoning behind the auth and write models are in
[`ARCHITECTURE.md`](./ARCHITECTURE.md).

---

## Run it locally

```sh
cd apps/scribe
npx wrangler dev
```

Open the printed URL (default **http://localhost:8787**). There is no login screen:
in production Cloudflare Access establishes who you are, and locally `.dev.vars`
fakes it.

```ini
# apps/scribe/.dev.vars — committed on purpose, contains no secrets
DEV_USER_EMAIL = "dev@worldmachines.local"
DEV_HANDLE     = "aneesh"      # change to test as another member — try "vgr"
DEV_NAME       = "Dev User"
```

`DEV_USER_EMAIL` stands in for the `Cf-Access-Authenticated-User-Email` header. It is
**ignored the moment `ACCESS_TEAM_DOMAIN` and `ACCESS_AUD` are set**, so it cannot
weaken a deployed Worker. `DEV_HANDLE`/`DEV_NAME` only apply when the local KV has no
record for the email — with a seeded KV the real record wins:

```sh
npx wrangler kv key put --binding HANDLES --local \
  'you@example.com' '{"handle":"vgr","name":"Venkat Rao"}'
curl -s -H 'Cf-Access-Authenticated-User-Email: you@example.com' localhost:8787/api/me
```

**Nothing in this app can write to GitHub until `GITHUB_TOKEN` is set.** Until then
every save returns the exact file, path and commit plan it *would* produce, and makes
no network call at all.

### Install it on a phone

Open in Chrome/Safari → *Add to Home Screen*. `manifest.webmanifest` + `sw.js` are
wired; the shell and the note index are precached, so it opens offline and drafts
persist in `localStorage`. PWA install needs a secure context — `localhost` counts,
otherwise use the deployed https host.

---

## What it writes

| Type | Path | Notes |
|---|---|---|
| **Thought** | `raw-notes/<you>/YYYY-MM-DD-<slug>.md` | Quick capture. Dated filename keeps the day it was thought. |
| **Book note** | `raw-notes/<you>/<slug>.md` | Your reaction to a shared reading. `source:` names the source-id under `commons/reading/`; picked section notes become `[[links]]`. |
| **Glossary** | `raw-notes/commons/glossary/<term>.md` | Communal. `term` / `aliases` / `status` (seed·developing·settled) / `contributors`. |
| **Link note** | `raw-notes/<you>/<slug>.md` | `connects:` frontmatter plus the same ids as `[[wiki-links]]` in the body, where the lake reads edges from. |
| **Edit** | any of the above | Rewrites body/summary/tags only; every other frontmatter key survives byte-for-byte. |

Your directory comes from your **handle**, not your email: `vgr` → `raw-notes/venkat/`.

Conventions were read off the repo rather than invented — `summary`/`tags`/
`last_updated` are what `tools/notes-pipeline/notes_to_parquet.py` consumes, the YAML
is quoted the way `raw-notes/commons/reading/*.md` quotes it, and a note's filename
stem is its wiki-link id.

**Every commit message starts with `[trivial]`** and every path is inside
`raw-notes/` — both are asserted before any request is built, so a bug cannot put a
note in `website/`. `[trivial]` is the repo's prefix for a change that needs no devlog
entry, and raw-notes-only changes are pre-authorised to land on `main`.

### Two things it deliberately refuses

- **Dangling `[[wiki-links]]`.** Links are checked against the live note index and a
  real save is blocked until they resolve. Wiki-links are case-sensitive and both repo
  validators miss broken ones, so this is the only place it gets caught.
- **Direct commits to canon pages** (`concepts/`, `entities/`, `summaries/`,
  `synthesis/`) — even inside your own directory. `raw-notes/README.md` puts
  hand-written canon behind PR review. Preview still works and gives you the exact
  file to put in the PR.

---

## Smoke test

With `wrangler dev` running:

```sh
B=http://127.0.0.1:8787

curl -s $B/api/config                  # mode, repo, auth mode — the only open route
curl -s $B/api/me                      # your identity + where notes would land
curl -s "$B/api/notes?scope=mine&q=legibility&limit=5"
curl -s $B/api/corpus | head -30       # books, tags, index freshness

# a dry-run of each note type
curl -s -X POST $B/api/compose -H 'content-type: application/json' -d '{
  "type":"observation","title":"Clocks before factories",
  "tags":"landes","body":"Demand-pull twice over.","dryRun":true}'

curl -s -X POST $B/api/compose -H 'content-type: application/json' -d '{
  "type":"book","title":"Scarcity is the baseline",
  "sourceId":"appleby-relentless-revolution",
  "readingNotes":["appleby-relentless-revolution-ch01-puzzle-of-capitalism"],
  "body":"The real question is the wait.","dryRun":true}'

curl -s -X POST $B/api/compose -H 'content-type: application/json' -d '{
  "type":"glossary","term":"Legibility Machine","status":"developing",
  "body":"Working definition.","dryRun":true}'

curl -s -X POST $B/api/compose -H 'content-type: application/json' -d '{
  "type":"link","title":"Legibility runs through both",
  "connects":["dante-legible-cosmos","the-legible-commonwealth"],"dryRun":true}'

# fails closed
curl -s -H 'Cf-Access-Authenticated-User-Email: stranger@example.com' $B/api/me   # 403
curl -s -X POST $B/api/save -H 'content-type: application/json' \
     -d '{"path":"website/index.html","body":"x","dryRun":true}'                  # 400
```

Unit tests for the note builders (paths, frontmatter, non-lossy edits, guards):

```sh
node test/notes.test.mjs
```

---

## API

| Route | Auth | Does |
|---|---|---|
| `GET /api/config` | open | Booleans about configuration. Nothing else. |
| `GET /api/me` | member | Identity, handle, target directory. |
| `GET /api/corpus` | member | Books, tag vocabulary, index freshness. |
| `GET /api/notes` | member | Note index. `scope=mine\|commons\|all`, `q`, `prefix`, `limit`. |
| `GET /api/note?path=` | member | One note's text + blob sha, for editing. |
| `POST /api/compose` | member | Build (and optionally commit) a new note. |
| `POST /api/save` | member | Edit an existing note. Needs the sha it was read with. |
| `POST /api/links/check` | member | Which `[[links]]` in a draft resolve. |

`dryRun` defaults to **true** on both write routes: a caller has to ask for a real
commit explicitly.

---

## Layout

```
apps/scribe/
├── README.md · ARCHITECTURE.md
├── wrangler.jsonc          ← Worker + assets + HANDLES KV; vars documented inline
├── .dev.vars               ← fake local identity (no secrets, never uploaded)
├── package.json
├── src/
│   ├── index.js            ← routes; the identity gate everything sits behind
│   └── lib/
│       ├── identity.js     ← Access email → HANDLES KV → handle → directory
│       ├── notes.js        ← the four note builders + the non-lossy editor
│       ├── github.js       ← Contents API writes, dry-run plans, the two guards
│       └── corpus.js       ← merged live+baked index behind the pickers
├── public/                 ← the PWA
│   ├── index.html · app.js · styles.css
│   ├── manifest.webmanifest · sw.js · icons/
│   └── data/notes-index.json   ← baked index (offline fallback for the pickers)
├── scripts/build-index.mjs ← regenerates that index from the checkout
└── test/notes.test.mjs     ← builder tests, plain node, no deps
```

### Refreshing the baked index

```sh
node apps/scribe/scripts/build-index.mjs
```

It only matters when `GITHUB_REPO` is unset or GitHub is unreachable — otherwise the
Worker reads the repo's git tree live and merges the two, so a note written five
minutes ago is already in the picker. The Me tab says which source is in use.

---

## Shipping it

Deploying is the orchestrator's job. In order:

1. **Create the Cloudflare Access application** for the hostname you'll use
   (`scribe.worldmachines.org` is the natural one — it sits beside the site and the
   Access policy can reuse the existing member allowlist). Policy: the same emails
   that are in the `HANDLES` KV.
2. **Uncomment the `routes` block** in `wrangler.jsonc` with that hostname.
   `workers_dev` is `false` on purpose — a `*.workers.dev` host is *not* behind
   Access, and the Worker trusts the header Access injects.
3. **Add the Access identifiers** to `vars` in `wrangler.jsonc`:
   `ACCESS_TEAM_DOMAIN` (host only, no scheme) and `ACCESS_AUD` (the application's
   Audience tag). This upgrades identity from "trust the header" to "verify the JWT",
   and disables `DEV_USER_EMAIL`.
4. **Set the token** — a fine-grained PAT on `worldmachines/worldmachines` with
   *Contents: Read and write*:
   ```sh
   npx wrangler secret put GITHUB_TOKEN
   ```
   Leave this until step 3 is done. Without it the app is a preview tool, which is a
   perfectly good first week.
5. ```sh
   cd apps/scribe && npx wrangler deploy
   ```
6. Check `/api/config` reports `"auth": "access-jwt"` and `"commitsEnabled": true`,
   then write one real note and look at the commit.

Nothing else needs provisioning: the `HANDLES` KV namespace already exists and is
shared with the website, so every registered member can use Scribe immediately.
