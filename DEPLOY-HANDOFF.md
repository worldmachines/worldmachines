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
