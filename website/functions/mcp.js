// /mcp — same-origin proxy to the World Machines Oracle worker's MCP server
// (wm-oracle, POST /mcp: search_corpus / get_note / get_chunks). Gives agents
// a stable public address on the site's own domain — worldmachines.org/mcp —
// instead of the workers.dev hostname, which is an account-specific detail.
//
// The MCP surface is public by design (read-only corpus search, no
// generation; see the wm-oracle README), so unlike /api/ask no token is
// attached here. All methods forward as-is: the worker answers POST, 405s
// GET (no server-initiated stream), and handles OPTIONS preflight itself.
//
// Pages env: ORACLE_URL (var) — base URL of the deployed Oracle worker,
// same value the /api/ask proxy uses.

export async function onRequest({ request, env }) {
  if (!env.ORACLE_URL) {
    return Response.json({ error: "oracle not configured" }, { status: 503 });
  }
  let upstream;
  try {
    upstream = await fetch(`${env.ORACLE_URL.replace(/\/$/, "")}/mcp`, {
      method: request.method,
      headers: { "Content-Type": "application/json" },
      body: ["GET", "HEAD"].includes(request.method) ? undefined : request.body,
    });
  } catch {
    return Response.json({ error: "oracle unreachable" }, { status: 502 });
  }
  // Rebuild the response (as api/ask.js does): re-serving the fetch Response
  // directly leaks the upstream's Content-Encoding header over an
  // already-decoded body, which garbles the payload for clients.
  const headers = {};
  for (const h of ["Content-Type", "Allow", "Access-Control-Allow-Origin"]) {
    const v = upstream.headers.get(h);
    if (v) headers[h] = v;
  }
  return new Response(upstream.status === 202 ? null : upstream.body, {
    status: upstream.status,
    headers,
  });
}
