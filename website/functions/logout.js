// Members logout.
//
// /cdn-cgi/access/logout is served by Cloudflare's edge on any hostname that
// has an Access application; hitting it clears the CF_Authorization cookie for
// that hostname. This route exists so pages can link to a plain "/logout" and
// so the flow keeps working if the logout path ever needs to change.
//
// Deliberately NOT behind an Access application — you should be able to sign
// out without first being made to sign in.

export function onRequestGet({ request }) {
  const url = new URL(request.url);
  return new Response(null, {
    status: 302,
    headers: {
      Location: `${url.origin}/cdn-cgi/access/logout`,
      'Cache-Control': 'private, no-store',
    },
  });
}
