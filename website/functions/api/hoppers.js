// GET  /api/hoppers — approved member hoppers (public; no emails)
// POST /api/hoppers — propose a public blyg hopper for the World Machines blyg
//
// Public on purpose, like /api/join: the members Access app only admits emails
// already in HANDLES, and hopper submissions are meant to bring NEW people in.
// A signed-in caller's verified email wins over the form's. Queue + blocking
// rules live in functions/_lib/hoppers.js.

import { getIdentity, blockCrossOrigin, NO_STORE } from '../_lib/access.js';
import {
  parseHopperUrl,
  probeHopper,
  isBlocked,
  liveSubmissionFor,
  createSubmission,
  listSubmissions,
} from '../_lib/hoppers.js';

const MAX_NOTE = 500;

export async function onRequestGet({ env }) {
  const approved = (await listSubmissions(env))
    .filter((s) => s.status === 'approved')
    .map(({ url, name, handle, title, decided_at }) => ({ url, name, handle, title, approved_at: decided_at }))
    .sort((a, b) => a.name.localeCompare(b.name));
  return Response.json({ hoppers: approved }, { headers: { 'Cache-Control': 'public, max-age=300' } });
}

export async function onRequestPost(ctx) {
  const { request, env } = ctx;

  const crossOrigin = blockCrossOrigin(request);
  if (crossOrigin) return crossOrigin;

  let body;
  try { body = await request.json(); } catch {
    return Response.json({ error: 'Invalid request' }, { status: 400, headers: NO_STORE });
  }

  // Honeypot: a field hidden from people. Pretend success so bots don't learn.
  if ((body.website || '').trim()) return Response.json({ ok: true }, { headers: NO_STORE });

  const identity = await getIdentity(request, env);
  const email = identity ? identity.email : (body.email || '').trim().toLowerCase();
  const name = (body.name || '').trim().slice(0, 100);
  const handle = (body.handle || '').trim().toLowerCase().replace(/^@/, '').slice(0, 40) || null;
  const note = (body.note || '').trim().slice(0, MAX_NOTE) || null;

  if (!email || !name || !body.url) {
    return Response.json({ error: 'Hopper URL, name and email are required.' }, { status: 400, headers: NO_STORE });
  }
  if (!/^[^\s@]+@[^\s@]+\.[^\s@]+$/.test(email)) {
    return Response.json({ error: 'Please enter a valid email address.' }, { status: 400, headers: NO_STORE });
  }

  const parsed = parseHopperUrl(body.url);
  if (parsed.error) return Response.json({ error: parsed.error }, { status: 400, headers: NO_STORE });

  if (await isBlocked(env, { base: parsed.base, email })) {
    return Response.json(
      { error: 'A submission from this blyg or email was declined, so it cannot be submitted again.' },
      { status: 403, headers: NO_STORE }
    );
  }

  const existing = await liveSubmissionFor(env, parsed.canonical);
  if (existing) {
    const what = existing.status === 'approved' ? 'already listed' : 'already waiting for review';
    return Response.json({ error: `That hopper is ${what}.` }, { status: 409, headers: NO_STORE });
  }

  const probe = await probeHopper(parsed.canonical);
  if (probe.error) return Response.json({ error: probe.error }, { status: 422, headers: NO_STORE });

  await createSubmission(env, {
    url: parsed.canonical,
    canonical: parsed.canonical,
    base: parsed.base,
    slug: parsed.slug,
    title: probe.title,
    name,
    email,
    email_verified: Boolean(identity && identity.verified),
    handle,
    note,
  });

  return Response.json({ ok: true }, { status: 201, headers: NO_STORE });
}
