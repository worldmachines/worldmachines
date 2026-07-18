// GET    — list all contributors, with emails (admin view)
// POST   — add/update { email, handle, name, url, bio }
// DELETE — remove { email }
//
// The gate is the "worldmachines admin" Cloudflare Access application on
// BOTH /admin/* and /api/admin/* (policy: admin emails only). The earlier bug
// was an Access policy that covered only /admin/* — the HTML page — while this
// API lives at /api/admin/*, so it was reachable unauthenticated. The
// requireAdmin() check below is defense-in-depth: it reads the
// Cf-Access-Authenticated-User-Email header, which Access injects only AFTER
// verifying the JWT and only when the request actually traversed an Access
// app. No header (path not behind Access, or a direct client request) → 403.
// Fail closed, never open.

// Comma-separated override via env; defaults to Aneesh + Venkat's two emails.
function adminEmails(env) {
  const raw = env.ADMIN_EMAILS || 'mail@aneeshsathe.com,vgururao@gmail.com,vgr@ribbonfarm.com';
  return new Set(raw.split(',').map((e) => e.trim().toLowerCase()).filter(Boolean));
}

function requireAdmin({ request, env }) {
  const email = (request.headers.get('Cf-Access-Authenticated-User-Email') || '').trim().toLowerCase();
  if (!email || !adminEmails(env).has(email)) {
    return Response.json({ error: 'forbidden' }, { status: 403 });
  }
  return null; // authorized
}

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

export async function onRequestGet(ctx) {
  const deny = requireAdmin(ctx);
  if (deny) return deny;
  return Response.json({ handles: await listHandles(ctx.env) });
}

export async function onRequestPost(ctx) {
  const deny = requireAdmin(ctx);
  if (deny) return deny;
  const { request, env } = ctx;
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

export async function onRequestDelete(ctx) {
  const deny = requireAdmin(ctx);
  if (deny) return deny;
  const { request, env } = ctx;
  let body;
  try { body = await request.json(); } catch {
    return Response.json({ error: 'Invalid JSON' }, { status: 400 });
  }

  const email = (body.email ?? '').trim().toLowerCase();
  if (!email) return Response.json({ error: 'email is required' }, { status: 400 });

  await env.HANDLES.delete(email);
  return Response.json({ ok: true });
}
