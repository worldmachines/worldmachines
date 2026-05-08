// Returns deduplicated contributor list from KV (no emails exposed).
// Deduplicates by handle so multiple emails for the same person collapse.

function parseValue(raw) {
  try { return JSON.parse(raw); } catch { return { handle: raw }; }
}

export async function onRequestGet({ env }) {
  const listed = await env.HANDLES.list();
  const seen = new Set();
  const contributors = [];

  for (const { name: email } of listed.keys) {
    const data = parseValue(await env.HANDLES.get(email));
    if (!data.handle || seen.has(data.handle)) continue;
    seen.add(data.handle);
    contributors.push({
      handle: data.handle,
      name:   data.name || data.handle,
      url:    data.url  || null,
      bio:    data.bio  || null,
    });
  }

  contributors.sort((a, b) => a.handle.localeCompare(b.handle));
  return Response.json({ contributors });
}
