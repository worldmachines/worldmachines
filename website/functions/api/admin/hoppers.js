// GET  — every hopper submission, newest first, with emails (admin view)
// POST — { id, action: "approve" | "reject" }
//
// Gated like /api/admin/handles: the "World Machines admin" Access application
// on /api/admin*, plus requireAdmin() as defence in depth.
//
// Approving records the hopper only; nothing is sent to blyg.worldmachines.org
// yet (see functions/_lib/hoppers.js for why). Rejecting blocks the
// submitter's blyg and email from submitting again.

import { getIdentity, requireAdmin, blockCrossOrigin, NO_STORE } from '../../_lib/access.js';
import { listSubmissions, getSubmission, decide } from '../../_lib/hoppers.js';

const ACTIONS = { approve: 'approved', reject: 'rejected' };

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

  const status = ACTIONS[body.action];
  if (!body.id || !status) {
    return Response.json({ error: 'id and action (approve|reject) are required' }, { status: 400, headers: NO_STORE });
  }

  const record = await getSubmission(env, String(body.id));
  if (!record) return Response.json({ error: 'No such submission' }, { status: 404, headers: NO_STORE });
  if (record.status !== 'pending') {
    return Response.json({ error: `Already ${record.status}` }, { status: 409, headers: NO_STORE });
  }

  const admin = await getIdentity(request, env);
  const updated = await decide(env, record, status, admin.email);
  return Response.json({ ok: true, submission: updated }, { headers: NO_STORE });
}
