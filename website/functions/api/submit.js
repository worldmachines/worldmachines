import { requireMember, blockCrossOrigin } from '../_lib/access.js';
import { PASTED_PREFIX } from './ingest-relay.js';

// Pasted article text can exceed repository_dispatch's ~64 KB client_payload
// limit, so it goes to R2 and the ingest job reads it back via /api/ingest-relay.
const MAX_PASTED_CHARS = 2_000_000;

export async function onRequestPost(ctx) {
  const { request, env } = ctx;

  const crossOrigin = blockCrossOrigin(request);
  if (crossOrigin) return crossOrigin;

  const member = await requireMember(ctx);
  if (member.denied) return member.denied;
  const handle = member.handle;

  let formData;
  try {
    formData = await request.formData();
  } catch {
    return Response.json({ error: 'Invalid form data' }, { status: 400 });
  }

  const url = formData.get('url')?.trim() ?? '';
  const type = formData.get('type') ?? '';
  const format = formData.get('format')?.trim() || 'essay';
  const description = formData.get('description')?.trim() || null;

  if (!url || !['contribution', 'resource'].includes(type)) {
    return Response.json({ error: 'Missing or invalid required fields' }, { status: 400 });
  }

  try { new URL(url); } catch {
    return Response.json({ error: 'Invalid URL' }, { status: 400 });
  }

  const pastedText = formData.get('text')?.trim() || '';
  if (pastedText.length > MAX_PASTED_CHARS) {
    return Response.json({ error: 'Pasted text is too long (2 million characters max).' }, { status: 413 });
  }

  const payload = {
    url,
    handle,
    type,
    format,
    description,
    submitted_at: new Date().toISOString(),
  };

  if (pastedText) {
    const key = `${crypto.randomUUID()}.txt`;
    await env.LIBRARY.put(PASTED_PREFIX + key, pastedText, {
      httpMetadata: { contentType: 'text/plain; charset=utf-8' },
      customMetadata: { url, handle },
    });
    payload.pasted_key = key;
  }

  if (!env.GITHUB_TOKEN || !env.GITHUB_REPO) {
    console.error('submit: GITHUB_TOKEN / GITHUB_REPO not configured on the Pages project');
    return Response.json({ error: 'Submissions are temporarily unavailable — please tell the project admin.' }, { status: 503 });
  }

  const ghRes = await fetch(
    `https://api.github.com/repos/${env.GITHUB_REPO}/dispatches`,
    {
      method: 'POST',
      headers: {
        Authorization: `Bearer ${env.GITHUB_TOKEN}`,
        Accept: 'application/vnd.github+json',
        'Content-Type': 'application/json',
        'X-GitHub-Api-Version': '2022-11-28',
        'User-Agent': 'worldmachines-worker',
      },
      body: JSON.stringify({
        event_type: 'article-submission',
        client_payload: payload,
      }),
    }
  );

  if (!ghRes.ok) {
    const text = await ghRes.text();
    console.error('GitHub dispatch failed:', ghRes.status, text);
    return Response.json({ error: 'Failed to queue submission' }, { status: 502 });
  }

  return Response.json({ success: true });
}
