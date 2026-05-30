function emailFromRequest(request) {
  const header = request.headers.get('Cf-Access-Authenticated-User-Email');
  if (header) return header;
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

export async function onRequestGet({ request, env, params }) {
  const key = params.key ? params.key.join('/') : null;
  if (!key) return new Response('Not found', { status: 404 });

  const isPrivate = key.startsWith('private/');
  const isPublic  = key.startsWith('public/');
  if (!isPublic && !isPrivate) return new Response('Not found', { status: 404 });

  if (isPrivate) {
    const email = emailFromRequest(request);
    if (!email) {
      return Response.json({ error: 'Authentication required' }, { status: 401 });
    }
  }

  const object = await env.LIBRARY.get(key);
  if (!object) return new Response('Not found', { status: 404 });

  const filename = key.split('/').pop();
  return new Response(object.body, {
    headers: {
      'Content-Type': 'application/pdf',
      'Content-Disposition': `inline; filename="${filename}"`,
      'Cache-Control': isPrivate ? 'private, max-age=3600' : 'public, max-age=86400',
    },
  });
}
