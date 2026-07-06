// POST /api/ask — same-origin proxy to the World Machines Oracle worker
// (wm-oracle, /api/ask). Keeps the ASK_TOKEN server-side so no token sits in
// the browser and the page has no cross-origin surface. The Oracle does the
// three-tier descent over the shared lake, the Witness hop for private
// evidence, and returns a cited answer — see
// wm-encyclopedia-kb/docs/adr/0002-oracle-witness-architecture.md.
//
// RUNBOOK — local preview
//   1. cp website/.dev.vars.example website/.dev.vars, fill in ORACLE_URL and
//      ASK_TOKEN (see that file for where the real dev values live — never
//      commit .dev.vars, it's gitignored).
//   2. From the repo root: npx wrangler pages dev website
//   3. Open http://localhost:8788/oracle.html and ask a question, or drive
//      the function directly:
//        curl -sX POST http://localhost:8788/api/ask \
//          -H 'Content-Type: application/json' \
//          -H 'X-Oracle-Session: test-session-1' \
//          -d '{"question":"What is the Modernity Machine?","debug":true}'
//   4. Verify: (a) `answer` is non-empty prose; (b) `citations.notes` /
//      `citations.chunks` are populated when the answer references sources;
//      (c) asking a second question with the SAME X-Oracle-Session header
//      (and debug:true) shows `debug.quoted_tokens` accumulate per source
//      rather than resetting — that's the session quote budget (D3) in
//      wm-encyclopedia-kb/docs/adr/0005-quote-budget.md round-tripping.
//
// Pages env (set on the Pages project, or website/.dev.vars locally):
//   ORACLE_URL  (var)    — base URL of the deployed Oracle worker
//   ASK_TOKEN   (secret) — optional bearer gate on the Oracle's /api/ask

export async function onRequestPost({ request, env }) {
  if (!env.ORACLE_URL) {
    return Response.json({ error: "oracle not configured" }, { status: 503 });
  }
  const headers = {
    "Content-Type": "application/json",
    ...(env.ASK_TOKEN ? { Authorization: `Bearer ${env.ASK_TOKEN}` } : {}),
  };
  // ADR 0005 D3: forward the client's per-browser-session id so the Oracle's
  // QuoteBudget Durable Object can key on it. Never generated or read here —
  // ORACLE_URL/ASK_TOKEN stay the only server-side secrets this function holds.
  const session = request.headers.get("X-Oracle-Session");
  if (session) headers["X-Oracle-Session"] = session;

  let upstream;
  try {
    upstream = await fetch(`${env.ORACLE_URL.replace(/\/$/, "")}/api/ask`, {
      method: "POST",
      headers,
      body: await request.text(),
    });
  } catch {
    return Response.json({ error: "oracle unreachable" }, { status: 502 });
  }
  // Pass the Oracle's JSON (answer + citations, or its error) straight through.
  return new Response(upstream.body, {
    status: upstream.status,
    headers: { "Content-Type": "application/json" },
  });
}
