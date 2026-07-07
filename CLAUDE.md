# worldmachines

> **All contributors — including AI agents — must read [`CONTRIBUTING.md`](CONTRIBUTING.md) before making any changes to this repository.**
>
> **For a full technical overview of the website stack (deployment, bindings, APIs, pipelines), read [`ARCHITECTURE.md`](ARCHITECTURE.md) before working on anything in `website/`.**

Collaborative project to develop psychohistorical models based on Venkatesh Rao's world machines theory.

The repository is organized into three collaboration zones:

1. `raw-notes/` — private-ish working areas, one directory per collaborator.
2. `wiki/` — AI-organized shared knowledge base generated from raw notes and reviewed by humans.
3. `website/` — Cloudflare Pages site and production publishing pipeline.

Live site: **worldmachines.org**.

## Repository zones and rules

### `raw-notes/`

- Each collaborator writes and pushes only inside their own subdirectory.
- Notes can be rough, idiosyncratic, incomplete, and written for future AI organization.
- Suggested note format: Markdown, short files, descriptive filenames, links/citations when available.
- Current directories:
  - `raw-notes/aneesh/`
  - `raw-notes/florian/`
  - `raw-notes/ivo/`
  - `raw-notes/kyle/`
  - `raw-notes/patrick/`
  - `raw-notes/sean/`
  - `raw-notes/venkat/`

### `wiki/`

- Shared knowledge layer: concepts, glossary entries, summaries, connections, bibliographic notes.
- Wiki edits should normally be proposed by AI-generated PRs derived from `raw-notes/`.
- Human review is required before merge. Any repo owner/admin may approve wiki PRs.
- Prefer small, reviewable PRs with links back to the raw notes that motivated each entry.

### `website/`

- Public website and deployed Cloudflare Pages app.
- Website changes must go through pull requests.
- Venkat must approve website PRs before merge.
- Do not push website changes directly to `main` except through approved automation.

This is a small high-trust group. `.github/CODEOWNERS` documents ownership and auto-requests reviewers on PRs. The repository ruleset requires pull requests into `main`, which prevents accidental direct pushes. Raw-notes PRs can be merged without required review. Wiki changes should go through PR review and may be approved by any repo owner/admin. Website changes should go through PR review and must be approved by Venkat. The `.github/workflows/approval-policy.yml` check enforces the wiki/website approval policy once it is required by the GitHub ruleset.

## Meeting-derived architecture summary

- The project is evolving from collective essay writing into a structured knowledge system.
- Proposed layers:
  - Raw chaotic reading/writing state.
  - Rough notes / research dumps as connective tissue between ideas.
  - Structured analysis using embeddings, statistical models, and time-aware simulation.
  - A future predictive “psychohistory” core with falsifiable claims.
- Use GitHub + Markdown/Obsidian-like structure as the source of truth.
- AI agents should help organize raw material, identify connections, mine glossary terms, and create PRs for human review.
- The website should remain separate from the working/wiki space.

## Website stack

> Full technical reference: [`ARCHITECTURE.md`](ARCHITECTURE.md)

- Static HTML · CSS · JS (no build framework)
- Cloudflare Pages (hosting + Pages Functions for serverless endpoints)
- Cloudflare Zero Trust / Access (authentication gate)
- Cloudflare KV (handle registry with full profile)
- GitHub Actions (article ingestion pipeline)
- Python + `trafilatura` (full-text extraction)

## Cloudflare bindings (`wrangler.jsonc`)

`website/wrangler.jsonc` is the **single source of truth** for all Cloudflare resource bindings (KV, R2, AI). The Pages project is a direct-upload project (not GitHub-connected), so the dashboard defers entirely to this file — any binding not declared here will be silently absent from `env` at runtime, causing Functions to crash with a 1101 error.

**When adding a new Cloudflare resource** (KV namespace, R2 bucket, D1 database, etc.), always add it to `wrangler.jsonc` first. Do not rely on the dashboard — the "Bindings" section in the Pages dashboard will show "managed by wrangler.toml" and ignore any manual additions.

**Current bindings:**

| `env` variable | Type | Resource |
|----------------|------|----------|
| `HANDLES` | KV | `handles` namespace — contributor email → handle/profile registry |
| `NOTES` | R2 | `worldmachines-notes` bucket — notes Parquet for Oracle |
| `LIBRARY` | R2 | `worldmachines-library` bucket — full PDFs and private article manifest |
| `AI` | Workers AI | Oracle embedding + chat models |

**Deploying:** Pages does not auto-deploy on git push. Always deploy manually after structural changes:

```bash
cd website
wrangler pages deploy . --project-name worldmachines --branch main
```

GitHub Actions only handles rebuilding static HTML from `blurbs.md`/`devlog.md` — it does not deploy to Pages.

## Website structure

```text
website/
  index.html                  ← blurb-only landing page, generated by website/scripts/build.py
  contributions.html          ← sortable list of contributions, generated by website/scripts/build.py
  resources.html              ← sortable list of resources, generated by website/scripts/build.py
  submit.html                 ← submission form (Access-gated); greets by name, links to /profile
  profile.html                ← standalone profile edit page (Access-gated)
  contributors.html           ← contributor list; links website, loaded from /api/contributors
  oracle.html                 ← multi-turn Oracle chat (server-side wm-oracle /api/ask via functions/api/ask.js proxy; public MCP instructions in footer)
  style.css                   ← shared styles
  blurbs.md                   ← front-page prose
  admin/handles.html          ← handle registry admin UI
  join.html                   ← public join-request form → GitHub issue; pre-fills email from session
  supplements/                ← rendered HTML versions of supplement documents (generated one-off, committed as static)
  functions/mcp.js            ← public MCP proxy → wm-oracle worker /mcp (search_corpus, get_note, get_chunks)
  functions/api/              ← Cloudflare Pages Functions
    me.js                     ← auth state: 200+profile if registered, 403+email if not, 401 if unauthenticated
    join.js                   ← POST join request → creates GitHub issue with wrangler KV approval command
    pdf/[[key]].js            ← serves files from LIBRARY R2; public/ unrestricted, private/ requires CF Access JWT
    library/private.js        ← returns team-only article manifest after checking both JWT and HANDLES KV
  scripts/                    ← ingest/build/backfill scripts
  content/articles/           ← one JSON file per submitted article (license:team_only articles excluded from static HTML)
new_writing_inbox.md          ← direct-push submission inbox (repo root, not in website/)
.github/workflows/ingest.yml  ← article submission workflow (web form → repository_dispatch)
.github/workflows/inbox.yml   ← inbox workflow (push to new_writing_inbox.md → ingest + deploy)
```

## Article JSON schema

Each file in `website/content/articles/` contains:

```json
{
  "slug": "the-modernity-machine-20260504-abc123",
  "url": "https://...",
  "title": "Extracted or fallback title",
  "handle": "vgr",
  "submitted_at": "2026-05-04T18:00:00Z",
  "type": "contribution | resource",
  "format": "essay | short story | paper | book",
  "published_at": "2025-01-26",
  "description": "Optional submitter note",
  "extraction_success": true,
  "extracted_text": "Full article text (or null if extraction failed)",
  "author": "Author Name (books/resources only)",
  "section": "Optional section/grouping label",
  "license": "public_domain | cc_by | cc_by_nc | cc_by_sa | cc_by_nc_sa | cc | team_only | null",
  "pdf_key": "public/filename.pdf | private/filename.pdf | null",
  "format": "essay | short story | paper | book | supplement"
}
```

`license` and `pdf_key` are optional. When `pdf_key` is set and `license` is an open license, resources.html shows a PDF download badge. Articles with `license: "team_only"` are excluded from static HTML and served dynamically to authenticated users.

## Library (PDF hosting)

Full PDFs are stored in the `worldmachines-library` R2 bucket:
- `public/` prefix → freely downloadable, no auth
- `private/` prefix → requires CF Access JWT (same cookie as web form)
- `_manifests/private-articles.json` → JSON array of `team_only` article objects

**To add a private article's PDF:**
1. Upload PDF: `wrangler r2 object put worldmachines-library/private/<name>.pdf --file <path> --content-type application/pdf --remote`
2. Create article JSON with `license: "team_only"` and `pdf_key: "private/<name>.pdf"`
3. Regenerate and upload the private manifest:
   ```bash
   # From website/
   /opt/homebrew/bin/python3 scripts/build_private_manifest.py  # (not yet written)
   wrangler r2 object put worldmachines-library/_manifests/private-articles.json \
     --file /tmp/private-articles.json --content-type application/json --remote
   ```
4. Run `build.py` and deploy.

## Submission pipelines

**Web form (Access-gated):**
1. Collaborator visits `worldmachines.org/submit` → Cloudflare Access email OTP gate.
2. Form POSTs to `/api/submit`.
3. Function looks up submitter's handle+name from KV, fires `repository_dispatch` to GitHub.
4. `ingest.yml` runs `scripts/ingest.py` then `scripts/build.py` from `website/`.
5. Commits article JSON + rebuilt HTML, deploys to Cloudflare Pages.

**Writing inbox (direct push, no login needed):**
1. Collaborator adds lines to `new_writing_inbox.md` (repo root) and pushes to `main`.
2. Format: `handle | type | url` or `handle | type | url | description`
3. `inbox.yml` runs `scripts/ingest_inbox.py` then `scripts/build.py`.
4. Commits article JSONs + rebuilt HTML + cleared inbox, deploys to Cloudflare Pages.
5. Bot commits are guarded (`github.actor != 'github-actions[bot]'`) to prevent loops.

**HANDLES KV:** maps contributor email → `{handle, name, url, bio}`. Managed via
`worldmachines.org/admin/handles` (Access-gated) or `wrangler kv key put --binding HANDLES --remote`.

**Adding contributors:** CF Access should be set to allow any email OTP (no allowlist). New contributors
visit `/join`, submit a request, and a GitHub issue is created with the exact `wrangler kv key put` command
to approve them. Approving the HANDLES KV entry is the only admin step required.

## Local credentials

`.env.keys` at the repo root holds Cloudflare API tokens for local development and
manual CI re-runs. It is gitignored and Dropbox-ignored (`com.dropbox.ignored`).

| Variable | Scope | Used by |
|----------|-------|---------|
| `CF_AI_TOKEN` | Workers AI: Edit | `tools/notes-pipeline/notes_to_parquet.py --embed` |
| `CF_R2_TOKEN` | Workers R2 Storage: Edit | `wrangler r2 object put worldmachines-notes/notes.parquet` |

The same values are stored as GitHub Actions secrets `CF_AI_TOKEN` and `CF_R2_TOKEN`.

## Session wrap-up

Run this checklist at the end of every working session:

1. **Devlog** — prepend an entry to `website/devlog.md` summarising what changed and why it matters. Or add `[trivial]` to your commit message for minor changes. The `rebuild.yml` workflow auto-rebuilds and deploys `devlog.html` on push — no manual build step needed.

2. **CLAUDE.md** — if anything structural changed (new pages, new workflows, new conventions, stack changes), update this file so future sessions start with accurate context.

3. **Secrets check** — before committing, run `git diff --staged` and scan for anything that looks like an API key or token. `.env` and `.env.keys` are gitignored, but credentials can end up hardcoded in scripts or notes. See the Security section in `CONTRIBUTING.md`.

4. **Push** — GitHub Actions handles rebuild and deployment automatically for `devlog.md` and `blurbs.md` changes. For website structural changes (`oracle.html`, new pages, functions), run `wrangler pages deploy` manually after pushing.

## Rebuilding the site locally

```bash
cd website
/opt/homebrew/bin/python3 scripts/build.py
# then open index.html, contributions.html, resources.html in browser to verify
wrangler pages deploy . --project-name worldmachines --commit-dirty=true
```
