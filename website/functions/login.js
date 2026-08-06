// Members login redirector.
//
// This path is protected by the "World Machines members" Cloudflare Access
// application (any email in the HANDLES registry, One-time PIN) — see
// website/ACCESS-SETUP.md. Hitting it with no Access
// session triggers the OTP screen; after sign-in the request reaches this
// function WITH a CF_Authorization cookie for the hostname — which every other
// page's /api/me and /api/mcp-token calls then read.
//
// Its only job post-auth is to bounce the browser back to wherever the login
// button was clicked (?return=/mcp), so the member lands where they started,
// already signed in.

import { safeReturnPath } from './_lib/access.js';

export function onRequestGet({ request }) {
  const url = new URL(request.url);
  const dest = safeReturnPath(url.searchParams.get('return'));
  return new Response(null, {
    status: 302,
    headers: { Location: dest, 'Cache-Control': 'private, no-store' },
  });
}
