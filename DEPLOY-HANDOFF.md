# DEPLOY-HANDOFF.md — Cutover: worldmachines → Aneesh's Cloudflare account

**Written:** 2026-07-15
**Direction:** move the *whole* stack from Venkat's CF account (`vgr-702`) **back** to
Aneesh's CF account, so Aneesh has complete control. Venkat re-points
`worldmachines.org` DNS once the new deployment is verified.
**Supersedes** the 2026-07-06 Aneesh→Venkat handoff (see git history of this file).

---

## Update 2026-07-17 — apex-CNAME incident + revised DNS plan (zone transfer, not `www`)

PR #25 merged 2026-07-17, bindings cut over correctly. Venkat then pointed the
`worldmachines.org` apex CNAME directly at `worldmachines-2rd.pages.dev`
(Aneesh's project) rather than following the `www` + redirect stopgap below —
Cloudflare rejected it: **apex proxied CNAME to a Pages project on a different
account is banned cross-account (error 1014, "CNAME Cross-User Banned").** Site
was down for ~1–2 hours.

**Mitigation (done):** apex CNAME reverted to `worldmachines.pages.dev`
(Venkat's own project, same account as the zone — no cross-user restriction).
Site is back up on the **pre-cutover bindings** (Venkat's account) as of
2026-07-17. This is intentionally the old, working state — not the PR #25
deployment.

**Decision:** skip the `www` + redirect interim (Venkat's action item 2,
below) in favor of doing the **full zone transfer** now instead. Rationale:
avoids a permanent `www` in the address bar, and the interim was itself the
thing that caused today's incident — better to do the real cutover once.

### Zone transfer plan

1. **Venkat** exports current DNS records as a backup (Cloudflare dashboard →
   `worldmachines.org` zone → DNS → Records → Export, BIND format) before
   transferring — the zone transfer moves everything, including MX/email
   records.
2. **Venkat** initiates a cross-account zone transfer from his Cloudflare
   account to Aneesh's (`ebef79305d4b32a611e2946cc08f7bd6`) — Account Home (or
   the zone's own settings) → "Transfer domain to another account."
3. **Aneesh** accepts the incoming transfer request on his account.
4. **Whoever controls the registrar** checks whether the zone's assigned
   nameservers changed post-transfer (currently `andronicus.ns.cloudflare.com`
   / `connie.ns.cloudflare.com`). If they changed, the registrar's NS records
   must be updated to match, or the domain drops off the internet — this is
   the one step that can cause a real outage if missed. If unchanged, skip.
5. **Aneesh**, once the zone is on his account, adds `worldmachines.org` as an
   **apex** custom domain directly on his `worldmachines` Pages project —
   same-account now, so it validates normally (no TXT/DCV dance, no `www`
   redirect needed).
6. Verify site loads at `worldmachines.org` on the PR #25 bindings, then this
   doc's job is done.

**Until the transfer completes, the site continues serving the pre-cutover
(Venkat's-account) version.** Do not re-attempt a direct apex CNAME to
Aneesh's project — it will 1014 again.

Also still outstanding regardless of DNS: **Aneesh needs to import the
HANDLES KV export** Venkat sent him (contributor emails → handles/profiles)
into namespace `fc2ed69d95644b8298777e3318240e1c`. No rush from the site's
perspective — the export is a point-in-time snapshot and isn't blocking the
DNS work above.

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
- Pages project `worldmachines` → `worldmachines-2rd.pages.dev` (site deployed 2026-07-15; Oracle verified end-to-end through the site `/api/ask` proxy)

**Config changes in THIS PR:**
- `website/wrangler.jsonc`: `HANDLES` id → the new Aneesh-account namespace; `ORACLE_URL` → `wm-oracle-dev.aneeshsathe.workers.dev`.

---

## ✅ Deploy secrets swapped (2026-07-15) — merge this PR promptly

The `worldmachines` repo's GitHub Actions deploy secrets (`CLOUDFLARE_API_TOKEN`,
`CF_R2_TOKEN`, `CLOUDFLARE_ACCOUNT_ID`, `CF_AI_TOKEN`) now point at **Aneesh's**
account, so GitHub-Actions deploys land on Aneesh's Pages project. This PR fixes
`website/wrangler.jsonc` bindings (`HANDLES` id + `ORACLE_URL`) to match.

**Until this PR merges, `main` still carries the OLD bindings.** So don't push
`devlog.md` / `blurbs.md` / an article submission to `main` before merging — a
`main` auto-deploy would push the stale `HANDLES` id onto Aneesh's account and
1101 the HANDLES functions. Merging this PR is itself the corrective deploy
(it touches `devlog.md`, so `rebuild.yml` redeploys with the correct bindings).

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

2. **Point `worldmachines.org` at Aneesh's Pages deployment.**
   **Chosen approach (2026-07-15): interim CNAME — the zone stays on your
   account; you keep the registrar.** (When Aneesh tried to add the apex as a
   custom domain on *his* Pages project, Cloudflare demanded a full zone
   transfer — apex custom domains require the zone to live on the same account
   as the project. We're avoiding that registrar move for now.)

   The catch: because of that apex restriction, Aneesh cannot register the bare
   `worldmachines.org` on his project cross-account. So the interim uses a
   **`www` subdomain (which Cloudflare *does* allow cross-account) plus an apex
   redirect**:

   1. **Aneesh** adds `www.worldmachines.org` as a custom domain on his
      `worldmachines` Pages project. Cloudflare shows a **CNAME target** and a
      **TXT (DCV) verification** record — he sends you both values.
   2. **You** (zone on your account) add, in the `worldmachines.org` zone:
      - the **TXT** DCV record exactly as given, and
      - a **proxied CNAME** `www` → `worldmachines-2rd.pages.dev`.
   3. **You** redirect the apex to www — a **Redirect Rule**
      (`worldmachines.org/*` → `https://www.worldmachines.org/$1`, 301) so bare
      `worldmachines.org` lands on the Pages-served `www`.
   4. Aneesh confirms the cert issues and the site serves; done.

   *Clean end state (whenever you're ready for the registrar change):* move the
   `worldmachines.org` zone to Aneesh's account (repoint the registrar
   nameservers to his assigned CF NS — **export the current DNS records first**
   so MX/email and any other records carry over), then add the **apex** custom
   domain directly on his Pages project. That's the "complete control" target;
   the interim above is the no-registrar-change stopgap.

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
— ✅ **DONE 2026-07-15.** `CLOUDFLARE_API_TOKEN` + `CF_R2_TOKEN` ← Aneesh's CF API
token (Workers/Pages/R2/KV/AI); `CLOUDFLARE_ACCOUNT_ID` + `CF_AI_TOKEN` ← Aneesh's.
GitHub-Actions deploys now target Aneesh's account. (Steps 1/3 above — site deploy
+ ASK_TOKEN secret — are also done; A2/step-4 remain here for the record.)

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
