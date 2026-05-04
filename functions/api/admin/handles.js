// GET  — list all email→handle entries
// POST — add { email, handle }
// DELETE — remove { email }
//
// Protected by Cloudflare Access at /admin/* (admin-only policy).

async function listHandles(env) {
  const listed = await env.HANDLES.list();
  const handles = await Promise.all(
    listed.keys.map(async ({ name }) => ({
      email: name,
      handle: await env.HANDLES.get(name),
    }))
  );
  return handles.sort((a, b) => a.email.localeCompare(b.email));
}

export async function onRequestGet({ env }) {
  const handles = await listHandles(env);
  return Response.json({ handles });
}

export async function onRequestPost({ request, env }) {
  let body;
  try { body = await request.json(); } catch {
    return Response.json({ error: 'Invalid JSON' }, { status: 400 });
  }

  const email  = (body.email  ?? '').trim().toLowerCase();
  const handle = (body.handle ?? '').trim();

  if (!email || !handle) {
    return Response.json({ error: 'email and handle are required' }, { status: 400 });
  }
  if (!/^[^\s@]+@[^\s@]+\.[^\s@]+$/.test(email)) {
    return Response.json({ error: 'Invalid email' }, { status: 400 });
  }

  await env.HANDLES.put(email, handle);
  return Response.json({ ok: true });
}

export async function onRequestDelete({ request, env }) {
  let body;
  try { body = await request.json(); } catch {
    return Response.json({ error: 'Invalid JSON' }, { status: 400 });
  }

  const email = (body.email ?? '').trim().toLowerCase();
  if (!email) {
    return Response.json({ error: 'email is required' }, { status: 400 });
  }

  await env.HANDLES.delete(email);
  return Response.json({ ok: true });
}
