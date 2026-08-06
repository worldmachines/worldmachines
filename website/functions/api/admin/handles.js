// GET    — list all contributors, with emails (admin view)
// POST   — add/update { email, handle, name, url, bio, github }
// DELETE — remove { email }
//
// The gate is the "World Machines admin" Cloudflare Access application on
// BOTH /admin* and /api/admin* (policy: admin emails only). The earlier bug
// was an Access policy that covered only /admin/* — the HTML page — while this
// API lives at /api/admin/*, so it was reachable unauthenticated. The
// requireAdmin() check below is defence-in-depth: it resolves the caller's
// Access identity (verified JWT once ACCESS_TEAM_DOMAIN is set, otherwise the
// Access-injected header) and demands membership of ADMIN_EMAILS. No identity
// → 403. Fail closed, never open.

import { requireAdmin, blockCrossOrigin, NO_STORE } from '../../_lib/access.js';

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
  const deny = await requireAdmin(ctx);
  if (deny) return deny;
  return Response.json({ handles: await listHandles(ctx.env) }, { headers: NO_STORE });
}

export async function onRequestPost(ctx) {
  const crossOrigin = blockCrossOrigin(ctx.request);
  if (crossOrigin) return crossOrigin;
  const deny = await requireAdmin(ctx);
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
  // Optional GitHub username. Accepts "name", "@name" or a github.com URL.
  const github = normaliseGithub(body.github);

  if (!email || !handle) {
    return Response.json({ error: 'email and handle are required' }, { status: 400 });
  }
  if (!/^[^\s@]+@[^\s@]+\.[^\s@]+$/.test(email)) {
    return Response.json({ error: 'Invalid email' }, { status: 400 });
  }
  if (github === false) {
    return Response.json({ error: 'Invalid GitHub username' }, { status: 400 });
  }

  await env.HANDLES.put(email, JSON.stringify({ handle, name, url, bio, github }));
  return Response.json({ ok: true }, { headers: NO_STORE });
}

export async function onRequestDelete(ctx) {
  const crossOrigin = blockCrossOrigin(ctx.request);
  if (crossOrigin) return crossOrigin;
  const deny = await requireAdmin(ctx);
  if (deny) return deny;
  const { request, env } = ctx;
  let body;
  try { body = await request.json(); } catch {
    return Response.json({ error: 'Invalid JSON' }, { status: 400 });
  }

  const email = (body.email ?? '').trim().toLowerCase();
  if (!email) return Response.json({ error: 'email is required' }, { status: 400 });

  await env.HANDLES.delete(email);
  return Response.json({ ok: true }, { headers: NO_STORE });
}

// → null (unset), a bare username, or false (present but not a valid username)
function normaliseGithub(raw) {
  const value = (raw ?? '').toString().trim();
  if (!value) return null;
  const stripped = value
    .replace(/^https?:\/\/(www\.)?github\.com\//i, '')
    .replace(/^@/, '')
    .replace(/\/+$/, '');
  // GitHub usernames: 1–39 chars, alphanumeric or single hyphens.
  return /^[A-Za-z0-9](?:[A-Za-z0-9]|-(?=[A-Za-z0-9])){0,38}$/.test(stripped) ? stripped : false;
}
