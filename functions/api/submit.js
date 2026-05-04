function emailFromRequest(request) {
  // Access injects this header when the path is policy-protected
  const header = request.headers.get('Cf-Access-Authenticated-User-Email');
  if (header) return header;

  // Fallback: decode email from the CF_Authorization JWT in the session cookie
  const cookie = request.headers.get('cookie') || '';
  const match = cookie.match(/CF_Authorization=([^;]+)/);
  if (!match) return null;
  try {
    const payload = JSON.parse(atob(match[1].split('.')[1]));
    return payload.email || null;
  } catch {
    return null;
  }
}

export async function onRequestPost({ request, env }) {
  const submitterEmail = emailFromRequest(request);
  if (!submitterEmail) {
    return Response.json({ error: 'Unauthorized' }, { status: 401 });
  }

  const handle = await env.HANDLES.get(submitterEmail);
  if (!handle) {
    return Response.json({ error: 'Your account is not registered. Contact the site admin.' }, { status: 403 });
  }

  let formData;
  try {
    formData = await request.formData();
  } catch {
    return Response.json({ error: 'Invalid form data' }, { status: 400 });
  }

  const url = formData.get('url')?.trim() ?? '';
  const type = formData.get('type') ?? '';
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
