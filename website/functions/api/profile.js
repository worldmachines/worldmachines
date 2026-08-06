// GET  /api/profile — the caller's own profile (from HANDLES, keyed by Access email)
// POST /api/profile — updates name, url, bio. handle, email and github are admin-owned.

import { requireMember, blockCrossOrigin, NO_STORE } from '../_lib/access.js';

export async function onRequestGet(ctx) {
  const member = await requireMember(ctx);
  if (member.denied) return member.denied;

  const { handle, name, url, bio, github } = member.profile;
  return Response.json(
    {
      email: member.email,
      handle,
      name: name || '',
      url: url || '',
      bio: bio || '',
      github: github || '',
    },
    { headers: NO_STORE }
  );
}

export async function onRequestPost(ctx) {
  const crossOrigin = blockCrossOrigin(ctx.request);
  if (crossOrigin) return crossOrigin;

  const member = await requireMember(ctx);
  if (member.denied) return member.denied;

  let body;
  try {
    body = await ctx.request.json();
  } catch {
    return Response.json({ error: 'invalid_json', message: 'Invalid JSON' }, { status: 400 });
  }

  const name = (body.name ?? '').trim();
  const url = (body.url ?? '').trim() || null;
  const bio = (body.bio ?? '').trim() || null;

  // Spread the existing record first so admin-owned fields (handle, github, and
  // anything added later) survive a member's profile save instead of being
  // silently dropped by this write.
  await ctx.env.HANDLES.put(
    member.key,
    JSON.stringify({ ...member.profile, handle: member.handle, name, url, bio })
  );

  return Response.json({ ok: true }, { headers: NO_STORE });
}
