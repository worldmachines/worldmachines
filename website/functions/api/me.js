function emailFromRequest(request) {
  const header = request.headers.get('Cf-Access-Authenticated-User-Email');
  if (header) return header;
  const cookie = request.headers.get('cookie') || '';
  const match = cookie.match(/CF_Authorization=([^;]+)/);
  if (!match) return null;
  try {
    const payload = JSON.parse(atob(match[1].split('.')[1]));
    return payload.email || null;
  } catch { return null; }
}

export async function onRequestGet({ request, env }) {
  const email = emailFromRequest(request);
  if (!email) return Response.json({ error: 'unauthorized' }, { status: 401 });

  const raw = await env.HANDLES.get(email);
  if (!raw) return Response.json({ error: 'not_registered', email }, { status: 403 });

  try {
    const { handle, name, url, bio } = JSON.parse(raw);
    return Response.json({ email, handle, name: name || '', url: url || '', bio: bio || '' });
  } catch {
    return Response.json({ error: 'not_registered', email }, { status: 403 });
  }
}
