// GET  — every hopper submission, newest first, with emails (admin view)
// POST — { id, action: "approve" | "reject" | "revalidate" }
//
// Gated like /api/admin/handles: the "World Machines admin" Access application
// on /api/admin*, plus requireAdmin() as defence in depth.
//
// Submissions that pass the validator are accepted on arrival, so the admin's
// job is mostly after the fact:
//   approve     — a `pending` record (left over from the approve-first flow)
//   reject      — a `pending` or `approved` record; blocks the submitter's
//                 blyg and email from submitting again
//   revalidate  — a `pending` or `approved` record; re-runs the validator,
//                 refreshes its metadata, and approves it if it passes
//
// Accepting records the hopper only; nothing is sent to blyg.worldmachines.org
// yet (see functions/_lib/hoppers.js for why).

import { getIdentity, requireAdmin, blockCrossOrigin, NO_STORE } from '../../_lib/access.js';
import { listSubmissions, getSubmission, decide, revalidate } from '../../_lib/hoppers.js';

// action → statuses it may act on
const ALLOWED_FROM = {
  approve: ['pending'],
  reject: ['pending', 'approved'],
  revalidate: ['pending', 'approved'],
};

export async function onRequestGet(ctx) {
  const deny = await requireAdmin(ctx);
  if (deny) return deny;
  return Response.json({ submissions: await listSubmissions(ctx.env) }, { headers: NO_STORE });
}

export async function onRequestPost(ctx) {
  const crossOrigin = blockCrossOrigin(ctx.request);
  if (crossOrigin) return crossOrigin;
  const deny = await requireAdmin(ctx);
  if (deny) return deny;
  const { request, env } = ctx;

  let body;
  try { body = await request.json(); } catch {
    return Response.json({ error: 'Invalid JSON' }, { status: 400, headers: NO_STORE });
  }

  const allowed = ALLOWED_FROM[body.action];
  if (!body.id || !allowed) {
    return Response.json(
      { error: 'id and action (approve|reject|revalidate) are required' },
      { status: 400, headers: NO_STORE }
    );
  }

  const record = await getSubmission(env, String(body.id));
  if (!record) return Response.json({ error: 'No such submission' }, { status: 404, headers: NO_STORE });
  if (!allowed.includes(record.status)) {
    return Response.json({ error: `Cannot ${body.action}: already ${record.status}` }, { status: 409, headers: NO_STORE });
  }

  if (body.action === 'revalidate') {
    const result = await revalidate(env, record);
    if (result.error) {
      return Response.json(
        { error: `Validation failed: ${result.error}`, submission: result.record || record },
        { status: result.status, headers: NO_STORE }
      );
    }
    return Response.json({ ok: true, submission: result.record }, { headers: NO_STORE });
  }

  const admin = await getIdentity(request, env);
  const status = body.action === 'approve' ? 'approved' : 'rejected';
  const updated = await decide(env, record, status, admin.email);
  return Response.json({ ok: true, submission: updated }, { headers: NO_STORE });
}
