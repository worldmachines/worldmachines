// GET  — returns current contributor's profile (from KV, keyed by Access email)
// POST — updates name, url, bio (handle and email are immutable)

function emailFromRequest(request) {
  const header = request.headers.get('Cf-Access-Authenticated-User-Email');
  if (header) return header;
  const cookie = request.headers.get('cookie') || '';
  const match = cookie.match(/CF_Authorization=([^;]+)/);
  if (!match) return null;
  try {
    const payload = JSON.parse(atob(match[1].split('.')[1]));
    return payload.email || null;
  } catch { return null; }
}

function parseValue(raw) {
  try { return JSON.parse(raw); } catch { return { handle: raw }; }
}

export async function onRequestGet({ request, env }) {
  const email = emailFromRequest(request);
  if (!email) return Response.json({ error: 'Unauthorized' }, { status: 401 });

  const raw = await env.HANDLES.get(email);
  if (!raw) return Response.json({ error: 'Not registered' }, { status: 403 });

  const { handle, name, url, bio } = parseValue(raw);
  return Response.json({ email, handle, name: name || '', url: url || '', bio: bio || '' });
}

export async function onRequestPost({ request, env }) {
  const email = emailFromRequest(request);
  if (!email) return Response.json({ error: 'Unauthorized' }, { status: 401 });

  const raw = await env.HANDLES.get(email);
  if (!raw) return Response.json({ error: 'Not registered' }, { status: 403 });

  const current = parseValue(raw);

  let body;
  try { body = await request.json(); } catch {
    return Response.json({ error: 'Invalid JSON' }, { status: 400 });
  }

  const name = (body.name ?? '').trim();
  const url  = (body.url  ?? '').trim() || null;
  const bio  = (body.bio  ?? '').trim() || null;

  await env.HANDLES.put(email, JSON.stringify({
    handle: current.handle,   // immutable
    name,
    url,
    bio,
  }));

  return Response.json({ ok: true });
}
