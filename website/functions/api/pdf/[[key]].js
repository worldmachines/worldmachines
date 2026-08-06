// public/  → anyone.
// private/ → registered members only. Before, this only required *an* Access
// identity; it never checked HANDLES, so any address Access happened to admit
// could pull in-copyright PDFs. Now it is the same gate as the rest of the
// members area.
import { requireMember } from '../../_lib/access.js';

export async function onRequestGet(ctx) {
  const { env, params } = ctx;
  const key = params.key ? params.key.join('/') : null;
  if (!key) return new Response('Not found', { status: 404 });

  const isPrivate = key.startsWith('private/');
  const isPublic  = key.startsWith('public/');
  if (!isPublic && !isPrivate) return new Response('Not found', { status: 404 });

  if (isPrivate) {
    const member = await requireMember(ctx);
    if (member.denied) return member.denied;
  }

  const object = await env.LIBRARY.get(key);
  if (!object) return new Response('Not found', { status: 404 });

  const filename = key.split('/').pop();
  const ext = filename.split('.').pop().toLowerCase();
  const contentTypes = {
    pdf:  'application/pdf',
    md:   'text/markdown; charset=utf-8',
    txt:  'text/plain; charset=utf-8',
    html: 'text/html; charset=utf-8',
  };
  const contentType = contentTypes[ext] || 'application/octet-stream';
  return new Response(object.body, {
    headers: {
      'Content-Type': contentType,
      'Content-Disposition': `inline; filename="${filename}"`,
      'Cache-Control': isPrivate ? 'private, max-age=3600' : 'public, max-age=86400',
    },
  });
}
