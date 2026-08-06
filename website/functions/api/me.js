// GET /api/me — "who am I?", the auth-state probe every member page calls.
//
// Deliberately NOT behind a Cloudflare Access application: public pages
// (/mcp, /join, /submit, /profile) fetch it to decide which panel to show, and
// a page behind Access would answer an anonymous fetch() with a cross-origin
// redirect to the OTP screen, which JS cannot read. Instead it verifies the
// Access JWT itself (see functions/_lib/access.js) and answers in plain JSON:
//
//   200 { email, handle, ... }        signed in and registered
//   403 { error: 'not_registered' }   signed in, no HANDLES record
//   401 { error: 'unauthorized' }     not signed in

import { getIdentity, lookupProfile, unauthorized, notRegistered, NO_STORE } from '../_lib/access.js';

export async function onRequestGet({ request, env }) {
  const identity = await getIdentity(request, env);
  if (!identity) return unauthorized();

  const profile = await lookupProfile(env, identity);
  if (!profile || !profile.handle) return notRegistered(identity.email);

  const { handle, name, url, bio, github } = profile;
  return Response.json(
    {
      email: identity.email,
      handle,
      name: name || '',
      url: url || '',
      bio: bio || '',
      github: github || '',
    },
    { headers: NO_STORE }
  );
}
