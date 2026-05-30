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

// Private articles manifest is stored in LIBRARY R2 at _manifests/private-articles.json.
// Upload or update it with:
//   wrangler r2 object put worldmachines-library/_manifests/private-articles.json \
//     --file private-articles.json --content-type application/json --remote
export async function onRequestGet({ request, env }) {
  const email = emailFromRequest(request);
  if (!email) {
    return Response.json({ error: 'Authentication required' }, { status: 401 });
  }

  const manifest = await env.LIBRARY.get('_manifests/private-articles.json');
  if (!manifest) {
    return Response.json([], { headers: { 'Cache-Control': 'private, no-store' } });
  }

  try {
    const articles = JSON.parse(await manifest.text());
    return Response.json(articles, { headers: { 'Cache-Control': 'private, no-store' } });
  } catch {
    return Response.json([], { headers: { 'Cache-Control': 'private, no-store' } });
  }
}
