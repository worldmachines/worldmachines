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

## Update 2026-07-17 (evening) — Aneesh session: HANDLES loaded, registry-exposure fix, DNS plan corrected, Access deferred

State captured at the end of Aneesh's 2026-07-17 session. Nothing here has been
executed beyond what's marked ✅ **DONE** or **PR open** — Aneesh paused at this
point and is not acting further tonight. This section **refines the morning's
DNS plan above** (the registrar mechanics were off) and adds new items.

### ✅ DONE — HANDLES KV backfilled into Aneesh's account

- Loaded all 9 records from `handles-export.json` into
  `fc2ed69d95644b8298777e3318240e1c` via `wrangler kv bulk put`. Verified live
  against `worldmachines-2rd.pages.dev/api/contributors`: **8 unique
  contributors** (Florian and Venkat each have two emails that collapse to one).
- Two same-session edits:
  - `mail@aneeshsathe.com` `url` → `https://aneeshsathe.com` (the scheme is
    required — `contributors.html` puts `url` straight into the `href` and only
    strips the scheme for display; `bio` left empty so it doesn't double the
    domain on its own line).
  - Added **Brandon Pink** `brndnpink@gmail.com` → handle `brandon` (handle
    **inferred** from the first-name convention — confirm with Brandon; he has
    **no `raw-notes/brandon/` dir and no CLAUDE.md collaborator line** yet).
- Closes Venkat's action item 1 (export) and Aneesh's step B (backfill). The
  export file is now gitignored (via PR #29).

### ✅ VERIFIED — GitHub Actions deploy secrets already point at Aneesh's account

The starting worry was that CI still held Venkat's credentials. It does not: the
four repo secrets (`CLOUDFLARE_API_TOKEN`, `CF_R2_TOKEN`, `CLOUDFLARE_ACCOUNT_ID`,
`CF_AI_TOKEN`) were rotated 2026-07-15 21:35 and are confirmed working — today's
`rebuild.yml` run deployed bot-commit `911e39c` into account `ebef7930…`
(Aneesh's) Pages project. No secrets action needed (matches "A2 · DONE" below).

### 🔴 SECURITY — contributor-registry API was publicly exposed → fix in PR #30

- `/api/admin/handles` had **no authentication**, verified live on **both**
  `worldmachines-2rd.pages.dev` **and** `worldmachines.org`: `GET` returned every
  record **including emails** (200, unauthenticated); `POST`/`DELETE` (read from
  source, **not** tested against prod) let anyone add themselves to the submit
  allowlist or delete contributors.
- Root cause: the Access policy protected `/admin/*` (the HTML admin page) but
  the API lives at `/api/admin/*`, which that prefix never matches.
- **PR #30** (`security/access-login-and-admin-gate`) closes it with an
  in-function admin-email allowlist keyed on `Cf-Access-Authenticated-User-Email`
  (**fail-closed** — no header ⇒ 403), independent of any Access app. Same PR
  adds the member login button + `/login` redirector (see Access below). Touches
  `website/` → needs Venkat's approval; merge auto-deploys via `rebuild.yml`.
- ⚠️ **CI split-brain — merging PR #30 does NOT fix the live public domain.**
  `worldmachines.org` is currently served by **Venkat's** Pages project
  (`worldmachines.pages.dev`, per the morning update). GitHub CI deploys to
  **Aneesh's** account, so the merge only fixes `worldmachines-2rd.pages.dev`. To
  close the hole on `worldmachines.org` before cutover, **Venkat must redeploy
  his Pages project from updated `main`** — or accept the residual exposure until
  the domain transfer lands (after which `worldmachines.org` serves Aneesh's
  fixed deployment).

### DNS — corrected: this is a Cloudflare **Registrar** inter-account transfer

The morning plan's entry point (Account Home → "Transfer domain to another
account") is right, but two mechanics were off:

- `worldmachines.org` is registered at **Cloudflare Registrar, inside Venkat's
  account** (whois: `Registrar: Cloudflare, Inc.`). There is **no external
  registrar** to point elsewhere, and a Cloudflare Registrar domain **must stay
  on the Cloudflare nameservers assigned to its zone in the same account** — you
  cannot hand-set NS to Aneesh's `bailey`/`sterling`. So the morning plan's
  **step 4 ("update the registrar's NS if they changed") has no valid target and
  is not a separate step** — the inter-account registration transfer re-homes the
  NS automatically within Cloudflare.
- Treat it as one operation: **the Registrar inter-account transfer** (moves the
  registration; the pending zone on Aneesh's account becomes the live one).
  Docs: <https://developers.cloudflare.com/registrar/account-options/inter-account-transfer/>

Prereqs, checked 2026-07-17:

- ✅ Registered >10 days ago (2026-05-04)
- ✅ Destination zone already added & **pending** on Aneesh's account
  (`440e991c…`, created 2026-07-18 UTC; assigned NS `bailey`/`sterling`)
- ✅ DNSSEC off (no DS/DNSKEY at the registry)
- ✅ No `pendingDelete` / `redemptionPeriod` / `pendingTransfer`
- ⚠️ **Transfer lock `clientTransferProhibited` is SET — Venkat must release it**
- ⚠️ Registrant email must be verified (Venkat's side)

Steps: **Venkat** releases the lock + confirms the registrant email, then Manage
Domain → Configuration → Start → transfer to account
`ebef79305d4b32a611e2946cc08f7bd6`. **Aneesh** accepts within **5 days** (Manage
Domains → View Actions) or it auto-cancels; post-move the registration is
transfer-locked 30 days.

⚠️ The move carries **WHOIS contacts only — "no other configuration will be
moved"** — so DNS records do **not** come with it (the morning plan's step-1
export already covers this). Low risk here: the live zone is near-empty — **apex
only, no MX, no TXT, no `www`, no subdomains** (probed 2026-07-17), so there's no
email to break. Aneesh will pre-create the apex record in the pending zone so
there's no gap at the NS flip. After the move, NS update automatically and Aneesh
adds `worldmachines.org` as an **apex** custom domain on the Pages project
(validates directly, same account — this is what error 1014 was blocking).

This corrected plan was posted for Venkat as a comment on **PR #29** (2026-07-17).

### Cloudflare Access — DEFERRED until after the domain transfer (decision 2026-07-17)

No Access app exists on Aneesh's account yet: the `.pages.dev` host has none, and
`worldmachines.org` login works only because it's still Venkat's deployment with
Venkat's Access. **Decision: do the Access setup after the transfer, directly on
`worldmachines.org`.** Rationale: real users are on `worldmachines.org` (Venkat's
Access still works there), so login isn't actually broken in the interim, and this
avoids a `.pages.dev`-now + apex-later double setup. The registry hole is already
handled by PR #30's fail-closed in-function check, independent of Access.

Interim state to expect on `worldmachines-2rd.pages.dev` until Access exists:
PR #30's "Sign in" button and MCP-token minting are **inert** (no Access ⇒ no
`CF_Authorization` cookie), and `/admin/handles` returns 403 for everyone — use
`wrangler kv` for registry edits (that's how the backfill was done).

**When ready (after transfer)**, create two Access apps on Aneesh's account
(Zero Trust → Access → Applications → Self-hosted). One-time PIN is the login
method (on by default; first-time Zero Trust use asks you to pick a team name →
`<team>.cloudflareaccess.com`). Add `worldmachines.org/<path>` rows; add the
matching `.pages.dev/<path>` rows too only if you want the staging host working.

- **App 1 — members** (permissive, any email). Paths `/login`, `/submit`,
  `/profile`. Policy: Allow, Include → **Everyone** (still forces OTP = any
  verified email; HANDLES KV is the real allowlist per `CLAUDE.md`).
- **App 2 — admin** (restricted). Paths `/admin`, `/api/admin`. Policy: Allow,
  Include → Emails: `mail@aneeshsathe.com`, `vgururao@gmail.com`,
  `vgr@ribbonfarm.com` (matches the `ADMIN_EMAILS` default in
  `functions/api/admin/handles.js`; override via that env var).

Acceptance tests (after apps exist + PR #30 deployed):

```bash
# registry API must be locked (was 200 leaking emails):
curl -s -o /dev/null -w "%{http_code}\n" <host>/api/admin/handles       # want 403 / login redirect
# login button must bounce to OTP:
curl -sI <host>/login | grep -i location                                 # want cloudflareaccess.com
```

Then in a browser: `/mcp` → "Sign in →" → OTP → land back on `/mcp` signed in →
"Generate my Witness token" works. **The one thing to verify live:** the members
OTP must set a *hostname-level* `CF_Authorization` cookie that the public `/mcp`
page's `fetch('/api/me')` can read (the code assumes this; it's how it worked on
Venkat's account). If `/api/me` still 401s after sign-in, that cookie scoping is
what to check.

### Still open after this session

- **Brandon Pink**: no `raw-notes/brandon/` dir, not in `CLAUDE.md` collaborator
  list, handle `brandon` unconfirmed.
- **Venkat**: release the transfer lock + verify registrant email + initiate the
  registrar transfer; and redeploy `worldmachines.org` after PR #30 merges (or
  accept residual exposure until cutover).
- **Aneesh**: accept the transfer within 5 days of Venkat starting it; pre-create
  the apex record; after cutover add the apex custom domain + set up the two
  Access apps.
- **PRs open**: #29 (this DNS doc), #30 (security + login button). This doc's
  morning "Update 2026-07-17" steps are refined by the DNS section above.

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
