import { requireMember } from '../../_lib/access.js';

// Private articles manifest is stored in LIBRARY R2 at _manifests/private-articles.json.
// Upload or update it with:
//   wrangler r2 object put worldmachines-library/_manifests/private-articles.json \
//     --file private-articles.json --content-type application/json --remote
export async function onRequestGet(ctx) {
  const { env } = ctx;

  const member = await requireMember(ctx);
  if (member.denied) return member.denied;

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
