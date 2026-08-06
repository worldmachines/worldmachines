# Scribe — architecture

One Cloudflare Worker. It serves an installable PWA from `public/` and a small JSON
API; the API turns a form into a markdown file and, when a token is configured,
commits it.

```
 phone  ──▶  Cloudflare Access  ──▶  Worker (wm-scribe)  ──▶  GitHub Contents API
              │                        │      │                  one file, one commit
              │                        │      └─ HANDLES KV  (email → handle)
              │                        └─ ASSETS      (the PWA + baked note index)
              └─ identity: email
```

Three things shape everything below:

1. **It is multi-user.** There is no "the owner" to pin to. Every request must resolve
   to one member before anything is generated, because the member's handle decides
   which directory the note belongs in.
2. **It writes into a repo other people read.** The corpus feeds a wiki and an oracle,
   so a note in the wrong shape is worse than no note. Path, frontmatter and links are
   all constrained.
3. **Dry-run is the resting state.** The interesting failure is a note written to the
   wrong place, so the app is built to show you the file before it can write one.

---

## 1. Auth flow

```
request
  │
  ├─ ACCESS_TEAM_DOMAIN + ACCESS_AUD set?      ── yes ─▶  verify the Access JWT
  │      (RS256, JWKS from the team domain,               email = verified claim
  │       aud/iss/exp/nbf/iat checked)                    DEV_USER_EMAIL ignored
  │
  ├─ no ─▶  Cf-Access-Authenticated-User-Email header     email = header
  │         └─ else CF_Authorization cookie payload
  │         └─ else DEV_USER_EMAIL                        (local dev only)
  │
  └─ nothing  ──▶ 401
                              │
                    email → HANDLES KV
                              │
                    no record ──▶ 403 not_registered
                              │
                    {handle, name, url, bio}
                              │
                    handle → directory  (vgr → venkat, else identity)
                              │
                    identity = { email, handle, name, dir, dirKnown }
```

**Why two modes.** The website's Pages Functions already trust
`Cf-Access-Authenticated-User-Email` (`website/functions/api/me.js`), so header mode
is consistent with what the project does today and works the moment Access is in
front. But a raw header is only as trustworthy as the guarantee that no un-gated
hostname can reach the Worker — which is why `workers_dev` is `false` and the only
route is the Access-gated custom domain. JWT mode removes the dependency on that
guarantee by verifying Access's signature in the Worker, so it is what a deploy should
run in. Setting the two `ACCESS_*` vars is the switch, and it also hard-disables
`DEV_USER_EMAIL` so a stray dev var cannot open a bypass.

**Why KV rather than a list in code.** `HANDLES` is the same namespace the website's
contributor registry uses (`website/wrangler.jsonc`, id `fc2ed69…`). One registry
means a member who can submit writing on worldmachines.org can capture notes here with
no second onboarding, and a curator adding someone through `website/admin/handles.html`
grants both at once. The handle→directory mapping is the one piece of local knowledge:
`venkat` writes as `vgr`, so that override lives in `identity.js` and everything else
is identity.

**Fail closed** is the whole point. No identity is a 401; an identity with no HANDLES
record is a 403 that names the fix. The dev fallback that invents a handle is
reachable only when Access is entirely unconfigured *and* the email came from
`DEV_USER_EMAIL` — three conditions that cannot all hold on a deployed Worker.

---

## 2. Write flow

```
POST /api/compose {type, fields…, dryRun}
        │
   buildNote(payload, identity)          src/lib/notes.js
        │   path      raw-notes/<dir>/… or raw-notes/commons/glossary/…
        │   markdown  frontmatter + body, byte-exact
        │   message   "[trivial] …"
        │
   danglingLinks(markdown)               src/lib/corpus.js
        │   any [[link]] with no target → 409 on a real save
        │
   writeNote(...)                        src/lib/github.js
        │   assertSafePath        path must start raw-notes/, end .md, no ".."
        │   assert message        must start "[trivial]"
        │
        ├─ dryRun || no token  ──▶  { committed:false, plan:{…} }   ← no fetch() at all
        └─ else                ──▶  PUT /repos/{repo}/contents/{path}
                                     one file · one commit · author = the member
```

**Contents API, not Git Data.** One note per commit means one file per commit, and
the Contents API does that in a single call. The six-call Git Data dance only earns
its complexity when several files must land atomically.

**`[trivial]` is enforced, not suggested.** The prefix is what lets a notes-only
change land on `main` without a devlog entry, and the guard sits next to the
`raw-notes/` path check so both are impossible to forget. Both throw *before* the
request is built — a guard that fires after a write is not a guard.

**Author attribution.** The commit's author is the member's name and Access email, so
`git log` shows who actually wrote the note rather than a shared bot identity.

**Editing is non-lossy on purpose.** A commons reading note carries `cites:`, `spans:`,
`level:` and `source:` that the ingestion pipeline resolved against a pinned extraction
with byte offsets. Round-tripping that through a YAML dumper would reorder and requote
all of it and silently change meaning. So `updateNote()` rewrites *only* the three keys
the editor shows — `summary`, `tags`, `last_updated` — with a line-level replacement,
and everything else is copied through untouched. The editor UI shows body/summary/tags
for the same reason: those are the fields it can safely own.

**Concurrent edits.** `/api/note` returns the blob `sha`; `/api/save` sends it back.
GitHub rejects a stale sha with a 422, so two people editing the same commons note get
an error rather than a silent overwrite.

---

## 3. Dry-run design

Dry-run happens for two independent reasons, and they are checked in this order:

1. `dryRun: true` in the request — the Preview button. Short-circuits **before any
   network call**, even when a token is configured. Preview can never write.
2. No `GITHUB_TOKEN` (or no `GITHUB_REPO`) — the shipping state. Everything is a plan.

Both return the same shape, so the UI has one code path:

```json
{ "path": "raw-notes/aneesh/2026-08-06-clocks-before-factories.md",
  "markdown": "---\ntags:\n- 'landes'\n…",
  "commitMessage": "[trivial] notes(aneesh): Clocks before factories",
  "dangling": [],
  "commit": { "committed": false, "dryRun": true, "reason": "GITHUB_TOKEN not configured — …",
              "plan": { "method": "PUT", "api": "https://api.github.com/repos/…",
                        "mode": "create", "bytes": 118, "author": {…} } } }
```

The preview is generated by **the same function** a real commit uses, so there is no
second implementation to drift. What you read is what would be written.

`/api/config` reports `commitsEnabled`, and the front-end disables "Save to repo"
until it is true — the prototype cannot commit even by accident.

---

## 4. The note index, and why it has two sources

Three pickers depend on knowing what already exists: books, wiki-link targets, and
tags. Each prevents a specific kind of drift, and one of them is load-bearing —
a `[[link]]` to a note that does not exist is invisible to **both** repo validators
and case-sensitivity makes it easy to produce (`[[prime-radiant]]` does not resolve
to `Prime Radiant.md`). So links are picked from real ids, and every generated note is
re-checked before a save.

| Source | Has | Freshness |
|---|---|---|
| `public/data/notes-index.json` (baked by `scripts/build-index.mjs`) | ids, **titles**, tags, book titles | frozen at generation |
| the repo's git tree via the GitHub API | every path that exists now | live, cached 5 min |

They are merged: titles come from the bake, existence from the tree. A note added
since the bake appears (titled from its filename); a deleted one disappears. With no
`GITHUB_REPO`, or when GitHub is unreachable, the bake carries on alone — a picker
that breaks capture when the network is slow would be worse than a slightly stale one.
The Me tab says which is in use.

The bake is also what makes the installed PWA useful offline: it is precached with the
shell, so the link picker still works on a train.

---

## 5. Security notes

- **`workers_dev: false`.** A `*.workers.dev` hostname is not behind Access; leaving
  it on would publish an origin where anyone could set the identity header themselves.
- **Path containment.** Every write path is checked to start with `raw-notes/`, end in
  `.md`, and contain no `..` or `//`. Handles are slugified to `[a-z0-9_-]` before they
  become a directory name, so a malformed KV record cannot traverse.
- **Directory ownership.** You may edit your own directory and `raw-notes/commons/`.
  Anything else is 403 — the rule `raw-notes/README.md` states.
- **Review gate.** Canon folders (`concepts`, `entities`, `summaries`, `synthesis`)
  cannot be direct-committed even inside your own directory; preview works so the
  result can go into a PR.
- **The token is a Worker secret** and is never sent to the browser. The front-end
  only ever learns the boolean `commitsEnabled`.
- **No caching of API responses** — everything under `/api/` is `no-store`, since it
  is per-member and mode-dependent. The service worker never caches `/api/` either.

---

## 6. What is deliberately not here

- **No offline write queue.** Drafts persist in `localStorage`, but a note is only
  written when you are online and press Save. A queue that commits later would commit
  things you have stopped agreeing with.
- **No canon-page authoring.** Scribe writes prose. The canon layer is generated by
  the ingestion pipelines and gated by review; a capture app should not be a second
  door into it.
- **No source text, ever.** The rule that matters in `raw-notes/README.md`: this repo
  holds your writing *about* material, never the material. Scribe has no import path,
  no paste-a-chapter field, and nothing that would encourage one.
- **No image upload.** The corpus is text; the Oracle indexes text.

---

## 7. Open questions for the club

1. **Hostname.** `scribe.worldmachines.org` assumes the zone is in the account the
   Worker deploys to. If the domain transfer is still in flight, a `*.workers.dev`
   host behind a Cloudflare Access self-hosted app is not possible — the fallback is
   deploying under whichever zone is available today.
2. **Access policy.** Should it be the same allowlist as the site, or a group? The
   Worker double-checks against `HANDLES` either way, so a looser Access policy is
   safe but produces confusing 403s for non-members.
3. **Book notes are flat.** They land as `raw-notes/<you>/<slug>.md` because that is
   how members actually name files today. If someone wants per-book folders
   (`raw-notes/<you>/reading/<source-id>/`, the shape `raw-notes/README.md` reserves
   for *private* reading), that is a one-line change in `notes.js`.
4. **Glossary template.** `term` / `aliases` / `status` / `contributors` was built to
   match what a parallel branch is defining. If that branch settles on different keys,
   `buildGlossary()` is the one place to change.
5. **Who may edit commons?** Currently everyone, since it is the shared area. Reading
   notes there are machine-generated with resolved character offsets, so hand-edits to
   `cites`/`spans` would be wrong — the editor cannot touch those keys, but it can
   change prose that cites them.
