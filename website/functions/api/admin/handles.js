// GET    — list all contributors (without emails)
// POST   — add/update { email, handle, name, url, bio }
// DELETE — remove { email }
//
// Protected by Cloudflare Access at /admin/* (admin-only policy).

function parseValue(raw) {
  try { return JSON.parse(raw); } catch { return { handle: raw }; }
}

async function listHandles(env) {
  const listed = await env.HANDLES.list();
  const rows = await Promise.all(
    listed.keys.map(async ({ name: email }) => {
      const data = parseValue(await env.HANDLES.get(email));
      return { email, ...data };
    })
  );
  return rows.sort((a, b) => (a.handle || '').localeCompare(b.handle || ''));
}

export async function onRequestGet({ env }) {
  return Response.json({ handles: await listHandles(env) });
}

export async function onRequestPost({ request, env }) {
  let body;
  try { body = await request.json(); } catch {
    return Response.json({ error: 'Invalid JSON' }, { status: 400 });
  }

  const email  = (body.email  ?? '').trim().toLowerCase();
  const handle = (body.handle ?? '').trim();
  const name   = (body.name   ?? '').trim();
  const url    = (body.url    ?? '').trim() || null;
  const bio    = (body.bio    ?? '').trim() || null;

  if (!email || !handle) {
    return Response.json({ error: 'email and handle are required' }, { status: 400 });
  }
  if (!/^[^\s@]+@[^\s@]+\.[^\s@]+$/.test(email)) {
    return Response.json({ error: 'Invalid email' }, { status: 400 });
  }

  await env.HANDLES.put(email, JSON.stringify({ handle, name, url, bio }));
  return Response.json({ ok: true });
}

export async function onRequestDelete({ request, env }) {
  let body;
  try { body = await request.json(); } catch {
    return Response.json({ error: 'Invalid JSON' }, { status: 400 });
  }

  const email = (body.email ?? '').trim().toLowerCase();
  if (!email) return Response.json({ error: 'email is required' }, { status: 400 });

  await env.HANDLES.delete(email);
  return Response.json({ ok: true });
}
