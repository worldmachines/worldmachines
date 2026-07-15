# DEPLOY-HANDOFF.md — Cutover: worldmachines → Aneesh's Cloudflare account

**Written:** 2026-07-15
**Direction:** move the *whole* stack from Venkat's CF account (`vgr-702`) **back** to
Aneesh's CF account, so Aneesh has complete control. Venkat re-points
`worldmachines.org` DNS once the new deployment is verified.
**Supersedes** the 2026-07-06 Aneesh→Venkat handoff (see git history of this file).

---

## What This Is

The July-6 move stood up a *parallel* copy of the Oracle/Witness/catalog stack
on Venkat's account but never tore down Aneesh's original — so **the backend is
already live on Aneesh's account** and needs only a data refresh. The work left
is the website layer (Pages project, buckets, KV) plus swapping deploy
credentials. This doc is the runbook; the *why* is in
`wm-infra/docs/VENKAT-DEPLOY.md` (same steps, mirrored account).

**Accounts**

| | account id | workers.dev subdomain |
|---|---|---|
| Aneesh (target) | `ebef79305d4b32a611e2946cc08f7bd6` | `aneeshsathe.workers.dev` |
| Venkat (current live) | `7026b5d7c1ad16cb808987576bb07ab2` | `vgr-702.workers.dev` |

---

## Current state (verified 2026-07-15)

**Already live on Aneesh's account** — no action needed:
- `wm-oracle-dev` / `wm-witness-dev` (Oracle + Witness workers) — `/api/ask` returns cited answers.
- `wm-ducklake-dev` / `wm-ducklake-personal-dev` (shared + personal catalogs, workers + R2 buckets).
- All catalog/oracle secrets (ADMIN / RETRIEVE / ASK / EVIDENCE / CF_AI) present in Aneesh's `.env`.

**Created 2026-07-15 on Aneesh's account** (empty, awaiting data):
- R2 `worldmachines-notes`, R2 `worldmachines-library`
- KV `HANDLES` → id `fc2ed69d95644b8298777e3318240e1c`
- Pages project `worldmachines` → `worldmachines-2rd.pages.dev` (no deploy yet)

**Config changes in THIS PR:**
- `website/wrangler.jsonc`: `HANDLES` id → the new Aneesh-account namespace; `ORACLE_URL` → `wm-oracle-dev.aneeshsathe.workers.dev`.

---

## ⚠️ Load-bearing order — do NOT merge this PR before the secret swap

`website/wrangler.jsonc` now points `HANDLES` at a namespace that exists **only
on Aneesh's account**. The `worldmachines` repo's GitHub Actions deploy secrets
(`CLOUDFLARE_API_TOKEN` / `CLOUDFLARE_ACCOUNT_ID`) still point at **Venkat's**
account. If this PR merges first, `rebuild.yml` will deploy the new binding to
Venkat's live Pages project, where that KV id doesn't exist → Functions crash
(1101). **Swap the secrets to Aneesh's account (step A2) BEFORE merging.**

---

## Venkat's action items

1. **Export the HANDLES KV** so Aneesh can load it into the new namespace
   (chosen approach: deploy empty first, backfill from your export). From a
   shell authenticated to your CF account:
   ```bash
   NS=ca021379904746528348029c242faaff   # the HANDLES namespace bound in wrangler.jsonc today
   npx wrangler kv key list --namespace-id "$NS" --remote > handles-keys.json
   : > handles-export.ndjson
   for k in $(jq -r '.[].name' handles-keys.json); do
     v=$(npx wrangler kv key get "$k" --namespace-id "$NS" --remote)
     jq -cn --arg key "$k" --arg value "$v" '{key:$key, value:$value}' >> handles-export.ndjson
   done
   ```
   Send `handles-export.ndjson` to Aneesh (it's contributor emails → profiles;
   share it privately, not via a public PR). Aneesh bulk-loads it into
   `fc2ed69d95644b8298777e3318240e1c`.

2. **Re-point `worldmachines.org` DNS** to Aneesh's Pages deployment, once he
   confirms `worldmachines-2rd.pages.dev` is verified. Two options:
   - *Preferred:* move the `worldmachines.org` zone to Aneesh's account, then add
     the custom domain in his `worldmachines` Pages project (auto-creates DNS).
   - *Or:* keep the zone on your account and point it at his Pages project via a
     CNAME (`worldmachines.org` → `worldmachines-2rd.pages.dev`); Aneesh adds the
     custom domain on his side and you approve the validation record.

3. **(Optional, deferred) `worldmachines-library` PDFs.** The gated team-library
   set lives in your `worldmachines-library` bucket, which Aneesh can't read.
   Deferred for now (C1). If/when wanted, copy `public/` + `private/` +
   `_manifests/` to Aneesh, or hand him the source PDFs.

4. **Approve this PR** (touches `website/` → `approval-policy` requires @vgururao).

5. **(After cutover verified) Tear down** the `vgr-702` copy of the stack if you
   no longer want it billing to your account.

---

## Aneesh's steps (this side)

**A · Refresh data + deploy (needs the R2 API token; local, using wrangler OAuth)**
1. Mint an R2 API token (Admin R&W, all buckets) → `R2_ACCESS_KEY_ID` / `R2_SECRET_ACCESS_KEY`.
2. Point the lake at this account: `wm-encyclopedia-kb/config.yaml` `worker_url` → `aneeshsathe`; `wm-oracle` `CATALOG_URL` → `aneeshsathe` (deployed workers already use it; this syncs git).
3. Full local publish (moves all notes + the 1,721 RAG chunks, current):
   ```bash
   cd wm-encyclopedia-kb && set -a && source .env && set +a
   export R2_ACCOUNT_ID=$CLOUDFLARE_ACCOUNT_ID CF_ACCOUNT_ID=$CLOUDFLARE_ACCOUNT_ID
   uv run lake sync && uv run lake embed
   uv run lake publish shared --dry-run && uv run lake publish shared
   uv run lake publish personal --dry-run && uv run lake publish personal
   ```
4. Deploy the site to Aneesh's Pages project + set its secrets:
   ```bash
   cd website
   npx wrangler pages secret put ASK_TOKEN --project-name worldmachines   # = oracle's ASK_TOKEN (.env ASK_TOKEN_DEV)
   # ORACLE_URL is a var, already in wrangler.jsonc
   npx wrangler pages deploy . --project-name worldmachines --branch main
   ```

**A2 · Swap the `worldmachines` repo GitHub Actions secrets → Aneesh's account**
(`CLOUDFLARE_API_TOKEN`, `CLOUDFLARE_ACCOUNT_ID`, `CF_AI_TOKEN`, `CF_R2_TOKEN`).
**Do this before merging this PR** (see ⚠️ above). Needs a broad CF API token
on Aneesh's account (Workers Scripts:Edit, Pages:Edit, Workers AI:Read, R2:Edit,
KV:Edit, Containers).

**B · Backfill HANDLES** from Venkat's export into `fc2ed69d…`.

**C · Notes→catalog CI** (the original ask): a workflow in `wm-encyclopedia-kb`
that runs `lake sync/embed/publish shared --only notes,edges` on `raw-notes/**`
changes (scoped so it never wipes the curator-built chunks). Secrets on that repo.

**D · Verify → tell Venkat to re-point DNS.**

---

## Verification (run before DNS cutover)

```bash
# catalogs
curl -sf https://wm-ducklake-dev.aneeshsathe.workers.dev/healthz
curl -sf https://wm-ducklake-personal-dev.aneeshsathe.workers.dev/healthz
# oracle golden evals (12/12)
cd wm-oracle
ORACLE_URL=https://wm-oracle-dev.aneeshsathe.workers.dev ASK_TOKEN=<value> npm run eval
# site
open https://worldmachines-2rd.pages.dev
```

---

## Notes

- `QUACK_TOKEN` does not exist (ADR 0004 D1) — do not mint.
- The catalog's R2 key is `_catalog/catalog.db`, not root `catalog.db` (`lake/r2.py`).
- `wm-infra` GitOps + `wm-feeder` deploy are phase-2 (direct deploy works now
  since the workers are already live on Aneesh's account).
