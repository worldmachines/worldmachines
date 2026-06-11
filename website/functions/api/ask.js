// POST /api/ask — same-origin proxy to the World Machines Oracle worker
// (wm-oracle, /api/ask). Keeps the ASK_TOKEN server-side so no token sits in
// the browser and the page has no cross-origin surface. The Oracle does the
// three-tier descent over the shared lake, the Witness hop for private
// evidence, and returns a cited answer — see
// wm-encyclopedia-kb/docs/adr/0002-oracle-witness-architecture.md.
//
// Pages env (set on the Pages project):
//   ORACLE_URL  (var)    — base URL of the deployed Oracle worker
//   ASK_TOKEN   (secret) — optional bearer gate on the Oracle's /api/ask

export async function onRequestPost({ request, env }) {
  if (!env.ORACLE_URL) {
    return Response.json({ error: "oracle not configured" }, { status: 503 });
  }
  let upstream;
  try {
    upstream = await fetch(`${env.ORACLE_URL.replace(/\/$/, "")}/api/ask`, {
      method: "POST",
      headers: {
        "Content-Type": "application/json",
        ...(env.ASK_TOKEN ? { Authorization: `Bearer ${env.ASK_TOKEN}` } : {}),
      },
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
