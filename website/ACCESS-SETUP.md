# Member login — Cloudflare Access setup

How the eight World Machines members sign in, how to provision it, how to test
it, and how to take it back out.

The HANDLES KV namespace already holds every member's record. "Creating
accounts" is therefore not a data task — it is turning on the Cloudflare Access
applications that let those people authenticate, and setting two Pages
variables so the site verifies the resulting token.

---

## The flow

```
  /login?return=/mcp
        │
        │  no session → Cloudflare Access intercepts (the "World Machines
        │  members" app covers /login) and asks for an email
        ▼
  One-time PIN emailed → member enters the code
        │
        │  Access sets the CF_Authorization cookie on the hostname and lets the
        │  request through, adding Cf-Access-Jwt-Assertion +
        │  Cf-Access-Authenticated-User-Email
        ▼
  functions/login.js  302s back to ?return= (same-origin paths only)
        ▼
  /mcp  → fetch('/api/me')
        │     functions/_lib/access.js verifies the JWT against the team JWKS,
        │     then maps email → handle via HANDLES KV
        │       200 = member · 403 not_registered · 401 signed out
        ▼
  "Generate my Witness token" → POST /api/mcp-token
        │     mints wmk_<32 hex>, stores it in MCP_TOKENS KV (90-day TTL)
        ▼
  MCP client sends `Authorization: Bearer wmk_…` to the Witness worker
```

`/api/me` is deliberately **not** behind Access: public pages call it to decide
whether to show a sign-in prompt, and an Access-gated endpoint answers an
anonymous `fetch()` with a cross-origin redirect to the OTP screen, which JS
cannot read. It verifies the Access JWT itself and returns a clean 401.

## What is gated by what

| Path | Access app | In-code check |
|---|---|---|
| `/login*` | members | — (it is only a redirector) |
| `/profile*`, `/submit*` | members | — (static pages) |
| `/wiki*` | members | — (static pages; members-only for now by decision 2026-08-06) |
| `/api/profile`, `/api/submit`, `/api/mcp-token`, `/api/library/private` | members | identity + HANDLES record |
| `/api/pdf/private/*` | members | identity + HANDLES record |
| `/api/pdf/public/*` | — | none (public) |
| `/api/me` | **none, on purpose** | identity + HANDLES record |
| `/admin*`, `/api/admin*` | admin | identity + `ADMIN_EMAILS` |
| `/logout` | **none, on purpose** | — (you should not have to sign in to sign out) |
| everything else | — | public |

The effective admin set is the **intersection** of the admin Access policy and
the `ADMIN_EMAILS` variable the Functions read. Both fail closed on their own.

---

## Provisioning

### 1. Mint an API token

dash.cloudflare.com → My Profile → API Tokens → Create Token → Custom token, on
**Aneesh's account**:

| Scope | Permission |
|---|---|
| Account → Access: Apps and Policies | Edit |
| Account → Access: Organizations, Identity Providers, and Groups | Read |
| Account → Workers KV Storage | Read |
| Account → Cloudflare Pages | Read |
| Zone → Zone | Read (all zones) |

The deploy token in `wm-infra/.env` does **not** have the Access scopes; this is
a separate, short-lived token.

### 2. Dry run

```bash
cd website
export CLOUDFLARE_API_TOKEN=...        # the token from step 1
export CLOUDFLARE_ACCOUNT_ID=ebef79305d4b32a611e2946cc08f7bd6
node scripts/provision-access.mjs                 # dry run is the default
node scripts/provision-access.mjs --json | jq .   # same plan, machine-readable
```

It prints the account, the Zero Trust team domain, the One-time PIN identity
provider, the hostnames it will cover, the member list, a create/update/
unchanged verdict per policy and app, and the exact `curl` calls it would make.
Nothing is written.

Read three lines of that output carefully:

- **Hostnames.** An Access application can only cover a hostname whose zone
  lives on the same account. If `worldmachines.org` is still on Venkat's
  account, the script skips it and says so, and login will work **only on
  `worldmachines-2rd.pages.dev`** until the zone moves. That is not a script
  bug; there is no way to protect a hostname whose zone you do not hold.
- **Members.** The count should match the HANDLES registry. The list comes from
  the KV namespace, so adding a contributor there and re-running is all it takes
  to grant login.
- **Identity provider.** If no One-time PIN provider is found, Access will offer
  every configured IdP. Enable One-time PIN in Zero Trust → Settings →
  Authentication first.

### 3. Apply

```bash
node scripts/provision-access.mjs --apply
```

It creates two reusable policies and the applications, then prints their
**AUD tags**. Access caps an application at 5 destinations, so a logical app
whose hostname × path matrix exceeds that is split into "World Machines
members", "World Machines members (2)", … — all attached to the same policy.
Members never notice: Access SSO carries one session across the chunk apps.
Re-running writes nothing once state matches, so it is safe in a loop or a
workflow.

### 4. Set the Pages variables — do not skip this

Until `ACCESS_TEAM_DOMAIN` is set, the Functions fall back to trusting the
`Cf-Access-Authenticated-User-Email` header, which is only meaningful on paths
Access actually covers. Setting it switches them to verifying the JWT
cryptographically, which is what makes the un-gated `/api/me` safe.

Cloudflare dashboard → Workers & Pages → **worldmachines** → Settings →
Variables and Secrets → add to **Production and Preview**:

| Variable | Value |
|---|---|
| `ACCESS_TEAM_DOMAIN` | `<team>.cloudflareaccess.com` (printed by the script) |
| `ACCESS_AUD` | every AUD tag the script prints (each member chunk app + admin), comma-separated |
| `ADMIN_EMAILS` | `mail@aneeshsathe.com` — keep it equal to the admin Access policy |

Or:

```bash
npx wrangler pages secret put ACCESS_TEAM_DOMAIN --project-name worldmachines
npx wrangler pages secret put ACCESS_AUD --project-name worldmachines
```

Then redeploy — Pages variables only reach the Functions on the next
deployment:

```bash
npx wrangler pages deploy . --project-name worldmachines --branch main
```

`ACCESS_AUD` is optional. Set, it pins tokens to these two applications; unset,
any valid token from this Zero Trust team is accepted. Set it.

### 5. Brandon's GitHub username

The handles record now takes an optional `github` field. To add Brandon's:

```bash
# via the admin API (needs an admin Access session in the browser — easiest is
# the /admin/handles page: click Edit on his row, fill GitHub, Save)

# or directly, from website/ — read the current record first, because a KV put
# replaces the whole value and would drop his name/url/bio:
npx wrangler kv key get "brndnpink@gmail.com" --binding HANDLES --remote

npx wrangler kv key put "brndnpink@gmail.com" \
  '{"handle":"brandon","name":"Brandon Pink","url":null,"bio":null,"github":"brndnpink"}' \
  --binding HANDLES --remote
```

Splice `github` into whatever `kv key get` returned rather than pasting the line
above verbatim if any of the other fields are non-null.

---

## Test plan

Run through this once as Aneesh, then ask one other member (Brandon is the
obvious first, since his record is the one being edited) to repeat steps 1–5.

Substitute `worldmachines-2rd.pages.dev` for `worldmachines.org` throughout if
the apex was skipped in step 2.

**Before anything is provisioned** — confirm the hole this closes:

```bash
curl -s -o /dev/null -w '%{http_code}\n' https://worldmachines.org/api/admin/handles
# 403 once the current branch is deployed (it was 200 with every member's email)

curl -s -H 'Cookie: CF_Authorization=eyJhbGciOiJSUzI1NiJ9.eyJlbWFpbCI6InZnckByaWJib25mYXJtLmNvbSJ9.x' \
     https://worldmachines.org/api/me
# 401. Before this branch, that hand-written cookie returned vgr's profile.
```

**Per member:**

1. Open `https://worldmachines.org/mcp` in a clean/private window. The Witness
   section shows **Sign in →**, the Oracle section is fully visible without
   signing in.
2. Click it. Access asks for an email; the code arrives within a minute or so
   (check spam). Wrong email → Access denies and lands on `/join`.
3. After the code, you land back on `/mcp`, now showing "Signed in as
   *name*" with Edit profile / Sign out.
4. Click **Generate my Witness token**. A `wmk_…` token appears, with an
   expiry ~90 days out, and the Claude Code / Claude Desktop snippets fill in
   with the real token. Copy it — it is not shown again.
5. The token appears in **Your tokens**, masked. Click **Revoke** on it and it
   disappears from the list.
6. Generate a fresh one and check it against the MCP endpoint:

```bash
TOKEN=wmk_...
curl -s https://wm-witness-dev.aneeshsathe.workers.dev/mcp \
  -H "Authorization: Bearer $TOKEN" \
  -H 'Content-Type: application/json' \
  -H 'Accept: application/json, text/event-stream' \
  --data '{"jsonrpc":"2.0","id":1,"method":"tools/list"}'
# expect a tools list, not 401

curl -s -o /dev/null -w '%{http_code}\n' https://wm-witness-dev.aneeshsathe.workers.dev/mcp \
  -H 'Authorization: Bearer wmk_0000000000000000000000000000dead' \
  -H 'Content-Type: application/json' --data '{"jsonrpc":"2.0","id":1,"method":"tools/list"}'
# expect 401
```

7. `https://worldmachines.org/profile` — the form is populated; change the bio,
   Save, reload, the change persists, and `handle` / `github` are unchanged.
8. `https://worldmachines.org/logout`, then reload `/mcp` — back to the
   **Sign in →** state.

**Admin, as Aneesh only:**

9. `https://worldmachines.org/admin/handles` — the registry loads, shows the
   GitHub column, and Edit prefills the form.
10. Ask a non-admin member to open the same URL: Access must deny them. If they
    somehow reach the page, `/api/admin/handles` still answers 403 (the in-code
    allowlist), which is the belt to Access's braces.

**Regression, from a terminal (no Access session):**

```bash
for p in /api/me /api/mcp-token /api/profile /api/library/private /api/admin/handles /api/pdf/private/x.pdf; do
  printf '%-28s %s\n' "$p" "$(curl -s -o /dev/null -w '%{http_code}' "https://worldmachines.org$p")"
done
# /api/me 401 · /api/mcp-token 302→Access · /api/profile 302 · /api/library/private 302
# /api/admin/handles 302 · /api/pdf/private/x.pdf 302
# (302 = Access intercepting, which is the correct answer for a gated path;
#  401 = /api/me answering honestly, which is its job)
```

---

## Rollback

Nothing here is one-way.

**Undo the Access applications** — Zero Trust → Access → Applications → delete
*World Machines members* and *World Machines admin* (and the two reusable
policies under Access → Policies). Or by API:

```bash
curl -s "https://api.cloudflare.com/client/v4/accounts/$CLOUDFLARE_ACCOUNT_ID/access/apps" \
  -H "Authorization: Bearer $CLOUDFLARE_API_TOKEN" | jq -r '.result[] | "\(.id)\t\(.name)"'

curl -X DELETE "https://api.cloudflare.com/client/v4/accounts/$CLOUDFLARE_ACCOUNT_ID/access/apps/<id>" \
  -H "Authorization: Bearer $CLOUDFLARE_API_TOKEN"
```

Deleting the apps makes `/login` a redirector nobody is challenged by, and every
member endpoint starts answering 401 — the site keeps serving, the members area
just becomes unreachable. It does **not** re-open `/api/admin/handles`; that is
held shut by the in-code allowlist independently.

**Undo the JWT verification** — remove the `ACCESS_TEAM_DOMAIN` variable and
redeploy. The Functions fall back to the Access header. Do this only if
verification is misconfigured and members are locked out; it is strictly weaker.

**Revoke every issued MCP token** — they live in the `MCP_TOKENS` KV namespace,
one key per token:

```bash
npx wrangler kv key list --binding MCP_TOKENS --remote | jq -r '.[].name' \
  | xargs -I{} npx wrangler kv key delete --binding MCP_TOKENS --remote {}
```

---

## Adding a member later

1. Add their email to HANDLES (the `/admin/handles` page, or `wrangler kv key put`).
2. Re-run `node scripts/provision-access.mjs --apply` — it reads the allowlist
   back out of HANDLES, so the Access policy picks them up.

Removing a member is the same two steps in reverse. Revoke their MCP tokens too
if they had any; deleting the HANDLES record stops new ones being minted but
does not invalidate tokens already issued (the Witness validates by key presence
in `MCP_TOKENS`, not by re-checking the registry).
