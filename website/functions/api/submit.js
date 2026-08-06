import { requireMember, blockCrossOrigin } from '../_lib/access.js';

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

  const payload = {
    url,
    handle,
    type,
    format,
    description,
    submitted_at: new Date().toISOString(),
  };

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
