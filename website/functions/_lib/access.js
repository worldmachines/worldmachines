// Cloudflare Access identity — the ONE place this site decides who is calling.
//
// Every /api function used to carry its own copy of `emailFromRequest()`, and
// every copy had the same hole: when the `Cf-Access-Authenticated-User-Email`
// header was absent it base64-decoded the *unverified* payload of the
// `CF_Authorization` cookie and believed whatever `email` it found there. A
// cookie is client-supplied, so `Cookie: CF_Authorization=x.<b64 of
// {"email":"vgr@ribbonfarm.com"}>.y` was a complete identity forgery against
// /api/me, /api/profile, /api/submit, /api/mcp-token, /api/library/private and
// the private half of /api/pdf/*. That decode is gone.
//
// Two modes, chosen by whether ACCESS_TEAM_DOMAIN is configured:
//
//   VERIFIED (env.ACCESS_TEAM_DOMAIN set — the target state)
//     The Access JWT (`Cf-Access-Jwt-Assertion` header, else the
//     `CF_Authorization` cookie) is verified with WebCrypto against the team's
//     JWKS at https://<team>.cloudflareaccess.com/cdn-cgi/access/certs, and
//     iss / exp / nbf (and `aud`, if ACCESS_AUD is set) are checked. Nothing
//     else is trusted. This is what makes it safe to leave /api/me reachable
//     without an Access application in front of it.
//
//   HEADER-ONLY (ACCESS_TEAM_DOMAIN unset — the state before Access exists)
//     Falls back to the `Cf-Access-Authenticated-User-Email` header that Access
//     injects. That header is only meaningful on paths an Access application
//     actually covers, so this mode is strictly a bootstrap. Set
//     ACCESS_TEAM_DOMAIN as a Pages variable as soon as the Access apps exist —
//     see website/ACCESS-SETUP.md.
//
// Nothing here ever falls back to "no identity means allow". Absent or
// unverifiable identity → 401. Fail closed.

export const NO_STORE = { 'Cache-Control': 'private, no-store' };

const CLOCK_SKEW_S = 60;
const JWKS_TTL_MS = 10 * 60 * 1000;

// Module-global JWKS cache. Isolates are short-lived and this is a pure cache
// of public keys — no request-specific state ever lands here.
let jwksCache = { origin: null, fetchedAt: 0, keys: null };

// ── Access team domain / audience config ──────────────────────────────

// "worldmachines" | "worldmachines.cloudflareaccess.com" | full URL → origin.
export function teamOrigin(env) {
  const raw = ((env && env.ACCESS_TEAM_DOMAIN) || '').trim();
  if (!raw) return null;
  const host = raw.replace(/^https?:\/\//, '').replace(/\/+$/, '').trim();
  if (!host) return null;
  return 'https://' + (host.includes('.') ? host : `${host}.cloudflareaccess.com`);
}

function audSet(env) {
  const raw = ((env && env.ACCESS_AUD) || '').trim();
  return new Set(raw.split(',').map((a) => a.trim()).filter(Boolean));
}

// ── JWT plumbing ──────────────────────────────────────────────────────

function b64urlBytes(part) {
  const pad = (4 - (part.length % 4)) % 4;
  const b64 = part.replace(/-/g, '+').replace(/_/g, '/') + '='.repeat(pad);
  const bin = atob(b64);
  const out = new Uint8Array(bin.length);
  for (let i = 0; i < bin.length; i++) out[i] = bin.charCodeAt(i);
  return out;
}

function b64urlJson(part) {
  return JSON.parse(new TextDecoder().decode(b64urlBytes(part)));
}

async function jwks(origin) {
  const now = Date.now();
  if (jwksCache.origin === origin && jwksCache.keys && now - jwksCache.fetchedAt < JWKS_TTL_MS) {
    return jwksCache.keys;
  }
  try {
    const res = await fetch(`${origin}/cdn-cgi/access/certs`, { cf: { cacheTtl: 600 } });
    if (!res.ok) throw new Error(`jwks ${res.status}`);
    const body = await res.json();
    const keys = Array.isArray(body.keys) ? body.keys : [];
    if (!keys.length) throw new Error('jwks empty');
    jwksCache = { origin, fetchedAt: now, keys };
    return keys;
  } catch (err) {
    // Serve stale keys through a JWKS blip rather than logging everyone out;
    // with no cache at all there is nothing to verify against → fail closed.
    if (jwksCache.origin === origin && jwksCache.keys) return jwksCache.keys;
    throw err;
  }
}

async function verifyAccessJwt(token, env) {
  const origin = teamOrigin(env);
  if (!origin || typeof token !== 'string') return null;

  const parts = token.split('.');
  if (parts.length !== 3) return null;

  let header;
  let payload;
  try {
    header = b64urlJson(parts[0]);
    payload = b64urlJson(parts[1]);
  } catch {
    return null;
  }
  if (header.alg !== 'RS256' || !header.kid) return null;

  const jwk = (await jwks(origin)).find((k) => k.kid === header.kid);
  if (!jwk) return null;

  const key = await crypto.subtle.importKey(
    'jwk',
    { kty: jwk.kty, n: jwk.n, e: jwk.e, alg: 'RS256', ext: true },
    { name: 'RSASSA-PKCS1-v1_5', hash: 'SHA-256' },
    false,
    ['verify']
  );
  const signed = new TextEncoder().encode(`${parts[0]}.${parts[1]}`);
  const ok = await crypto.subtle.verify('RSASSA-PKCS1-v1_5', key, b64urlBytes(parts[2]), signed);
  if (!ok) return null;

  const now = Math.floor(Date.now() / 1000);
  if (typeof payload.exp === 'number' && payload.exp + CLOCK_SKEW_S < now) return null;
  if (typeof payload.nbf === 'number' && payload.nbf - CLOCK_SKEW_S > now) return null;
  if (typeof payload.iat === 'number' && payload.iat - CLOCK_SKEW_S > now) return null;
  if (payload.iss && String(payload.iss).replace(/\/+$/, '') !== origin) return null;

  const allowed = audSet(env);
  if (allowed.size) {
    const auds = Array.isArray(payload.aud) ? payload.aud : payload.aud ? [payload.aud] : [];
    if (!auds.some((a) => allowed.has(a))) return null;
  }

  const email = String(payload.email || '').trim();
  return email ? { email, payload } : null;
}

function cookieValue(request, name) {
  const jar = request.headers.get('cookie') || '';
  const match = jar.match(new RegExp(`(?:^|;\\s*)${name}=([^;]+)`));
  return match ? match[1] : null;
}

// ── Public API ────────────────────────────────────────────────────────

/**
 * Resolve the Access identity of a request.
 * @returns {Promise<{email:string, rawEmail:string, verified:boolean}|null>}
 */
export async function getIdentity(request, env) {
  const origin = teamOrigin(env);

  if (origin) {
    const token =
      request.headers.get('Cf-Access-Jwt-Assertion') || cookieValue(request, 'CF_Authorization');
    if (!token) return null;
    let verified;
    try {
      verified = await verifyAccessJwt(token, env);
    } catch {
      return null; // JWKS unreachable and nothing cached → fail closed
    }
    if (!verified) return null;
    return { email: verified.email.toLowerCase(), rawEmail: verified.email, verified: true };
  }

  // Bootstrap mode: only the Access-injected header, never the cookie.
  const header = (request.headers.get('Cf-Access-Authenticated-User-Email') || '').trim();
  if (!header) return null;
  return { email: header.toLowerCase(), rawEmail: header, verified: false };
}

function parseValue(raw) {
  try {
    const parsed = JSON.parse(raw);
    return parsed && typeof parsed === 'object' ? parsed : { handle: raw };
  } catch {
    return { handle: raw };
  }
}

/**
 * HANDLES lookup, tolerant of a non-lowercase key having been written.
 * Returns the parsed record with the KV key it was found under attached as
 * `_key`, so writers update the record in place instead of forking it.
 */
export async function lookupProfile(env, identity) {
  const candidates = [...new Set([identity.email, identity.rawEmail].filter(Boolean))];
  for (const key of candidates) {
    const raw = await env.HANDLES.get(key);
    if (raw) return { ...parseValue(raw), _key: key };
  }
  return null;
}

export function unauthorized() {
  return Response.json(
    { error: 'unauthorized', message: 'Sign in with an approved World Machines email.' },
    { status: 401, headers: NO_STORE }
  );
}

export function notRegistered(email) {
  return Response.json(
    {
      error: 'not_registered',
      email,
      message: 'This account is not a registered World Machines contributor yet.',
    },
    { status: 403, headers: NO_STORE }
  );
}

/**
 * Identity + HANDLES registration in one step.
 * `key` is the KV key the record lives under — write updates back to that key.
 * @returns {Promise<{denied:Response}|{denied:null, email:string, key:string, handle:string, profile:object, verified:boolean}>}
 */
export async function requireMember({ request, env }) {
  const identity = await getIdentity(request, env);
  if (!identity) return { denied: unauthorized() };

  const found = await lookupProfile(env, identity);
  if (!found || !found.handle) return { denied: notRegistered(identity.email) };

  const { _key: key, ...profile } = found;
  return {
    denied: null,
    email: identity.email,
    key,
    verified: identity.verified,
    handle: profile.handle,
    profile,
  };
}

/**
 * Admin gate. Defence in depth behind the "World Machines admin" Access
 * application on /admin* AND /api/admin* — the effective admin set is the
 * intersection of that Access policy and this allowlist. No identity → 403.
 */
export function adminEmails(env) {
  const raw = (env && env.ADMIN_EMAILS) || 'mail@aneeshsathe.com,vgururao@gmail.com,vgr@ribbonfarm.com';
  return new Set(raw.split(',').map((e) => e.trim().toLowerCase()).filter(Boolean));
}

export async function requireAdmin({ request, env }) {
  const identity = await getIdentity(request, env);
  if (!identity || !adminEmails(env).has(identity.email)) {
    return Response.json({ error: 'forbidden' }, { status: 403, headers: NO_STORE });
  }
  return null;
}

/**
 * Reject cross-site state-changing requests. Browsers always send `Origin` on
 * POST/DELETE (including cross-site form posts); non-browser clients (curl, an
 * MCP server) send none and are left alone.
 */
export function blockCrossOrigin(request) {
  const origin = request.headers.get('Origin');
  if (!origin) return null;
  try {
    if (new URL(origin).host === new URL(request.url).host) return null;
  } catch {
    /* malformed Origin → treat as cross-origin */
  }
  return Response.json({ error: 'cross_origin' }, { status: 403, headers: NO_STORE });
}

/**
 * Same-origin absolute paths only. Rejects protocol-relative ("//host") and
 * backslash tricks ("/\\host") so ?return= can never bounce off-site.
 */
export function safeReturnPath(raw) {
  if (typeof raw !== 'string' || raw[0] !== '/' || raw[1] === '/' || raw[1] === '\\') return '/';
  return raw;
}
