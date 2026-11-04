// GET  /api/hoppers — approved member hoppers (public; no emails)
// POST /api/hoppers — submit a public blyg hopper for the World Machines blyg
//
// A submission that validates as a real public blyg hopper is accepted at once
// (status `approved`) and returned as `hopper`; anything else gets a 4xx with a
// readable `error`. The GET shape (publicHopper) is consumed elsewhere — keep
// `canonical`, `base`, `slug`, `title`, `submitted_at`, `name` stable.
//
// Public on purpose, like /api/join: the members Access app only admits emails
// already in HANDLES, and hopper submissions are meant to bring NEW people in.
// A signed-in caller's verified email wins over the form's. Queue + blocking
// rules and the validator live in functions/_lib/hoppers.js.
//
// An accepted submission also fires a GitHub repository_dispatch
// (`hopper-accepted`), which runs .github/workflows/blyg-sync.yml in its
// blogroll-only mode: the new hopper's blyg is subscribed and added to the WM
// blyg's blogroll within minutes instead of at the next twice-daily sync. It
// runs in ctx.waitUntil, so it never delays or fails the submission.

import { getIdentity, blockCrossOrigin, NO_STORE } from '../_lib/access.js';
import {
  normalizeHopperUrl,
  validateHopper,
  isBlocked,
  liveSubmissionFor,
  createSubmission,
  listSubmissions,
  publicHopper,
  revalidate,
} from '../_lib/hoppers.js';

const MAX_NOTE = 500;

export async function onRequestGet({ env }) {
  const approved = (await listSubmissions(env))
    .filter((s) => s.status === 'approved')
    .map(publicHopper)
    .sort((a, b) => (a.name || '').localeCompare(b.name || '') || a.canonical.localeCompare(b.canonical));
  // Short cache: accepted hoppers should show up within a minute.
  return Response.json({ hoppers: approved }, { headers: { 'Cache-Control': 'public, max-age=60' } });
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

  const parsed = normalizeHopperUrl(body.url);
  if (parsed.error) return Response.json({ error: parsed.error }, { status: 400, headers: NO_STORE });

  const blocked = () => Response.json(
    { error: 'A submission from this blyg or email was declined, so it cannot be submitted again.' },
    { status: 403, headers: NO_STORE }
  );
  // Cheap pre-check on the submitted mount; the identity origin is checked after validation.
  if (await isBlocked(env, { base: parsed.mount, email })) return blocked();

  const existing = await liveSubmissionFor(env, parsed.canonical);
  if (existing && existing.status === 'approved') {
    return Response.json({ error: 'That hopper is already listed.' }, { status: 409, headers: NO_STORE });
  }
  if (existing) {
    // Left pending by the old approve-first flow: nothing would ever list it,
    // and a 409 here kept its owner locked out. Re-validate the stored record
    // (approves it if it passes; keeps its id and submitted_at) and treat the
    // result exactly like a fresh acceptance.
    const r = await revalidate(env, existing);
    if (r.error) return Response.json({ error: r.error }, { status: r.status, headers: NO_STORE });
    return accepted(ctx, env, r.record);
  }

  const v = await validateHopper(parsed.canonical);
  if (v.error) return Response.json({ error: v.error }, { status: 422, headers: NO_STORE });
  if (await isBlocked(env, { base: v.base })) return blocked();

  const record = await createSubmission(env, v, {
    name,
    email,
    email_verified: Boolean(identity && identity.verified),
    handle,
    note,
  });
  return accepted(ctx, env, record);
}

/** 201 with the public record, plus the hopper-accepted dispatch in waitUntil. */
function accepted(ctx, env, record) {
  const hopper = publicHopper(record);
  const dispatch = dispatchHopperAccepted(env, hopper);
  if (typeof ctx.waitUntil === 'function') ctx.waitUntil(dispatch);
  return Response.json({ ok: true, hopper }, { status: 201, headers: NO_STORE });
}

/**
 * Ask GitHub to run the blyg sync's blogroll step for a just-accepted hopper.
 * Same call as /api/submit's article dispatch. Never throws: a failure is
 * logged, and the twice-daily sync picks the hopper up anyway.
 */
export async function dispatchHopperAccepted(env, hopper) {
  if (!env.GITHUB_TOKEN || !env.GITHUB_REPO) {
    console.error('hoppers: GITHUB_TOKEN / GITHUB_REPO not configured; no hopper-accepted dispatch');
    return false;
  }
  try {
    const res = await fetch(`https://api.github.com/repos/${env.GITHUB_REPO}/dispatches`, {
      method: 'POST',
      headers: {
        Authorization: `Bearer ${env.GITHUB_TOKEN}`,
        Accept: 'application/vnd.github+json',
        'Content-Type': 'application/json',
        'X-GitHub-Api-Version': '2022-11-28',
        'User-Agent': 'worldmachines-worker',
      },
      body: JSON.stringify({
        event_type: 'hopper-accepted',
        client_payload: { canonical: hopper.canonical, base: hopper.base },
      }),
    });
    if (!res.ok) {
      console.error('hoppers: hopper-accepted dispatch failed:', res.status, await res.text().catch(() => ''));
      return false;
    }
    return true;
  } catch (err) {
    console.error('hoppers: hopper-accepted dispatch failed:', err);
    return false;
  }
}
