// GET /api/stats — same-origin proxy to the World Machines Oracle worker
// (wm-oracle, /api/stats). Public cost/usage meter for the Oracle page: how
// many questions the corpus has answered (web + MCP), what that has cost, and
// whether the hourly/daily spend caps are currently tripped.
//
// Mirrors ask.js: ORACLE_URL/ASK_TOKEN stay server-side, the browser only ever
// talks to this same-origin path. The Oracle's /api/stats is public (no token
// needed), but the bearer is attached when configured so both proxies present
// the same identity upstream.
//
// FAILS SOFT BY DESIGN. Any upstream problem — unreachable, 5xx, non-JSON,
// unconfigured env — returns `{ ok: false }` with a 200, never an error status.
// The stats box is decoration on a page whose real job is answering questions;
// oracle.html hides the box entirely on `ok: false`, so a broken meter costs a
// missing panel rather than a broken Oracle. The one exception is the
// unconfigured-env guard, which returns 503 to match ask.js and make a
// misconfigured preview obvious to whoever is running it.
//
// RUNBOOK — local preview
//   1. cp website/.dev.vars.example website/.dev.vars and fill in ORACLE_URL
//      (see that file for where the real dev values live).
//   2. From the repo root: npx wrangler pages dev website
//   3. curl -s http://localhost:8788/api/stats | jq
//   4. Verify: (a) `ok: true` and the `web`/`mcp`/`caps`/`now` objects are
//      populated; (b) with ORACLE_URL pointed at a dead host, the same call
//      returns `{"ok":false}` with HTTP 200 and http://localhost:8788/oracle
//      renders with no stats box at all — chat still works.
//
// Pages env (set on the Pages project, or website/.dev.vars locally):
//   ORACLE_URL  (var)    — base URL of the deployed Oracle worker
//   ASK_TOKEN   (secret) — optional bearer gate, forwarded when set

// Upstream budget. The stats box renders on page load; a slow meter must not
// hold the page, so we give up early and hide rather than wait.
const UPSTREAM_TIMEOUT_MS = 4000;

export async function onRequestGet({ env }) {
  if (!env.ORACLE_URL) {
    return Response.json({ error: "oracle not configured" }, { status: 503 });
  }

  // `ok: false` + 200: the page treats this as "hide the box", not an error.
  const soft = () =>
    Response.json({ ok: false }, { headers: { "Cache-Control": "no-store" } });

  const headers = {
    ...(env.ASK_TOKEN ? { Authorization: `Bearer ${env.ASK_TOKEN}` } : {}),
  };

  let upstream;
  try {
    upstream = await fetch(`${env.ORACLE_URL.replace(/\/$/, "")}/api/stats`, {
      headers,
      signal: AbortSignal.timeout(UPSTREAM_TIMEOUT_MS),
    });
  } catch {
    return soft(); // unreachable or timed out
  }
  if (!upstream.ok) return soft();

  let body;
  try {
    body = await upstream.json();
  } catch {
    return soft(); // upstream answered, but not with JSON
  }
  if (!body || body.ok !== true) return soft();

  // 15s of edge caching: the numbers move on the order of a question, and the
  // page re-fetches after each ask anyway, so freshness costs nothing here.
  return Response.json(body, {
    headers: { "Cache-Control": "public, max-age=15" },
  });
}
