# DEPLOY-HANDOFF.md — Oracle/Witness Stack Deployment (In Progress)

**Written:** 2026-07-06  
**Status:** Steps 1–5 complete. Next: Step 6 (lake publish).

---

## What This Is

Deploying the Oracle/Witness stack from Aneesh Sathe's CF account to Venkat's CF account, following `wm-infra/docs/VENKAT-DEPLOY.md`. PR #15 on `worldmachines/worldmachines` (Aneesh's frontend changes) must NOT be merged until the stack is live in Venkat's account.

**Venkat's CF account:**
- Account ID: `7026b5d7c1ad16cb808987576bb07ab2`
- workers.dev subdomain: `vgr-702.workers.dev`
- Wrangler OAuth token: already authenticated (`npx wrangler whoami` confirms)

---

## 5 Repos (all under `/Users/Venkat/Dropbox/Code/worldmachines/`)

| Repo | Path | Branch | Status |
|------|------|--------|--------|
| wm-infra | `worldmachines/wm-infra/` | main | clean |
| wm-oracle | `worldmachines/wm-oracle/` | main | clean |
| wm-encyclopedia-kb | `worldmachines/wm-encyclopedia-kb/` | main | clean |
| wm-feeder | `worldmachines/wm-feeder/` | main | clean |
| wm-site | `worldmachines/wm-site/` | main | clean |

---

## Completed Steps

### Step 1 — URL Rewrites (done, committed)

All `*.aneeshsathe.workers.dev` → `*.vgr-702.workers.dev` in:

| File | Change |
|------|--------|
| `wm-oracle/oracle/wrangler.jsonc` | `CATALOG_URL` env var |
| `wm-oracle/witness/wrangler.jsonc` | `CATALOG_URL` env var |
| `wm-oracle/evals/run.mjs` | `DEFAULT_URL` constant |
| `wm-oracle/.github/workflows/eval.yml` | `inputs.oracle_url.default` |
| `wm-encyclopedia-kb/config.yaml` | both `worker_url` entries |

### Step 2 — CODEOWNERS (done, committed)

`wm-infra/.github/CODEOWNERS`: all `@aneeshsathe` → `@vgururao`

### Step 3 — R2 Buckets Created (done)

Both buckets exist in Venkat's CF account:
- `wm-ducklake-dev`
- `wm-ducklake-personal-dev`

### Step 4 — Catalog deployed (done via CI)

Both workers deployed to Venkat's account via GitHub Actions `apply.yml`.
CI secret `CLOUDFLARE_API_TOKEN` set on the `dev` environment of `worldmachines/wm-infra`.

### Step 5 — Secrets set (done)

All secrets set on both workers before first request. Values in `wm-infra/.env.keys`.

---

## Remaining Steps (from VENKAT-DEPLOY.md)

**Step 6 — Publish the encyclopedia**

```bash
cd /Users/Venkat/Dropbox/Code/worldmachines/wm-encyclopedia-kb
source /Users/Venkat/Dropbox/Code/worldmachines/wm-infra/.env.keys
export R2_ACCOUNT_ID=$CLOUDFLARE_ACCOUNT_ID
export CF_ACCOUNT_ID=$CLOUDFLARE_ACCOUNT_ID

uv run lake publish shared --dry-run
uv run lake publish shared
uv run lake publish personal --dry-run
uv run lake publish personal
```

R2 catalog key is `_catalog/catalog.db` (not root `catalog.db`).

**Step 7 — Deploy Witness and Oracle**

```bash
cd /Users/Venkat/Dropbox/Code/worldmachines/wm-oracle
source /Users/Venkat/Dropbox/Code/worldmachines/wm-infra/.env.keys

# Witness first (Oracle depends on it)
npx wrangler deploy --config witness/wrangler.jsonc

EVIDENCE_TOKEN="$(openssl rand -hex 32)"
printf '%s' "$EVIDENCE_TOKEN" | npx wrangler secret put EVIDENCE_TOKEN --config witness/wrangler.jsonc
printf '%s' "$RETRIEVE_TOKEN_PERSONAL" | npx wrangler secret put RETRIEVE_TOKEN --config witness/wrangler.jsonc

# Then Oracle
npx wrangler deploy --config oracle/wrangler.jsonc

ASK_TOKEN="$(openssl rand -hex 32)"
printf '%s' "$RETRIEVE_TOKEN_SHARED" | npx wrangler secret put RETRIEVE_TOKEN --config oracle/wrangler.jsonc
printf '%s' "$ASK_TOKEN"             | npx wrangler secret put ASK_TOKEN --config oracle/wrangler.jsonc
printf '%s' "$EVIDENCE_TOKEN"        | npx wrangler secret put WITNESS_TOKEN --config oracle/wrangler.jsonc
printf '%s' "https://wm-witness-dev.vgr-702.workers.dev" | npx wrangler secret put WITNESS_URL --config oracle/wrangler.jsonc
```

Save EVIDENCE_TOKEN and ASK_TOKEN to `wm-infra/.env.keys`.

**Step 8 — Wire wm-site frontend**

```bash
# 1. Swap Actions secrets on worldmachines/worldmachines GitHub repo:
#    CLOUDFLARE_API_TOKEN → Venkat's token
#    CLOUDFLARE_ACCOUNT_ID → 7026b5d7c1ad16cb808987576bb07ab2

# 2. Set Pages project secrets:
cd /Users/Venkat/Dropbox/Code/worldmachines/wm-site/website
npx wrangler pages secret put ASK_TOKEN --project-name worldmachines
# Set ORACLE_URL env var in Pages Settings → Environment variables:
#   https://wm-oracle-dev.vgr-702.workers.dev

# 3. Merge PR #15 on worldmachines/worldmachines

# 4. Deploy:
npx wrangler pages deploy . --project-name worldmachines --branch main
```

---

## Verification (after Step 7)

```bash
curl -sf "https://wm-ducklake-dev.vgr-702.workers.dev/healthz"
curl -sf "https://wm-ducklake-personal-dev.vgr-702.workers.dev/healthz"
# 12/12 golden evals:
cd /Users/Venkat/Dropbox/Code/worldmachines/wm-oracle
ORACLE_URL="https://wm-oracle-dev.vgr-702.workers.dev" ASK_TOKEN="<value>" npm run eval
```

---

## Security Notes

- **`QUACK_TOKEN` does not exist** — do not mint; any reference is stale (ADR 0004 D1)
- **Nothing carries over from Aneesh's account** — all credentials re-minted from scratch
- Voice feature (PR #15): **Approved by Venkat**

---

## Key Reference

Primary deploy doc: `/Users/Venkat/Dropbox/Code/worldmachines/wm-infra/docs/VENKAT-DEPLOY.md`  
PR to merge after deploy: `https://github.com/worldmachines/worldmachines/pull/15`

---

## 2026-07-06 Update — Oracle chat + MCP + soul document (Aneesh)

Three linked PRs land a coordinated change (all tested end-to-end on Aneesh's
dev stack — cloud copies of all three services run the new code there):

| Repo | Change |
|------|--------|
| `wm-infra` | catalog sidecar: `note_sources`/`source_titles` on `/api/retrieve` (maps notes to their source book), new `POST /api/note` (note body + graph edges) and `POST /api/chunks` (license-gated passages). All additive — old clients unaffected. |
| `wm-oracle` | `/api/ask` accepts `history` (multi-turn chat, ≤14 msgs); citations tagged with tier + book source; `prompts/soul.v1.md` persona layer (vgr_zirp soul-document pattern) prepended to the system prompt; **public** `POST /mcp` (MCP server: `search_corpus`, `get_note`, `get_chunks` — read-only, no generation, so no token; `/api/ask` keeps `ASK_TOKEN`); wrangler `main` moved to `src/worker.ts`; one retry on Workers-AI 504s. |
| `worldmachines` | `website/oracle.html` rewritten as a multi-turn chat (markdown rendering, waiting animation, concept chips + one source chip per book, MCP instructions); nav "Project Chat" → Discord. |

**Deploy order after merging (each step is the standard command):**

1. **wm-infra** — redeploy catalogs (CI `apply.yml`, or locally `make apply ENV=dev`,
   needs Docker). Then **roll both containers** — a live container survives
   deploys and keeps the old sidecar:

   ```bash
   source wm-infra/.env.keys
   curl -X POST https://wm-ducklake-dev.vgr-702.workers.dev/admin/roll \
     -H "Authorization: Bearer $ADMIN_TOKEN"            # shared
   curl -X POST https://wm-ducklake-personal-dev.vgr-702.workers.dev/admin/roll \
     -H "Authorization: Bearer $ADMIN_TOKEN_PERSONAL"   # personal
   ```

2. **wm-oracle** — `npx wrangler deploy --config oracle/wrangler.jsonc`.
   No new secrets. (Witness unchanged — no redeploy needed.)

3. **wm-site/website** — `npx wrangler pages deploy . --project-name worldmachines --branch main`.
   No new Pages env vars (`ORACLE_URL`/`ASK_TOKEN` unchanged).

**Verify:**

```bash
curl -s https://wm-oracle-dev.vgr-702.workers.dev/healthz
# MCP (public, no token):
curl -s -X POST https://wm-oracle-dev.vgr-702.workers.dev/mcp \
  -H 'Content-Type: application/json' \
  -d '{"jsonrpc":"2.0","id":1,"method":"tools/list"}'
# Multi-turn ask (history field is the new bit):
curl -s -X POST https://wm-oracle-dev.vgr-702.workers.dev/api/ask \
  -H "Authorization: Bearer $ASK_TOKEN" -H 'Content-Type: application/json' \
  -d '{"question":"what about China?","history":[{"role":"user","content":"what is a clock?"},{"role":"assistant","content":"A clock is..."}]}'
# Then /oracle on the site: chat, concept chips, one source chip per book.
```

Note: the MCP config printed on the site's /oracle page points at
`https://wm-oracle-dev.vgr-702.workers.dev/mcp` — it goes live when step 2
lands. The public MCP embeds queries via Workers AI on each search
(fractions of a cent); if abuse ever shows up, add an IP rate limit the way
ribbonfarm.com/mcp does.
