// identity.js — who is calling, and which raw-notes directory do they own?
//
// Scribe is MULTI-USER: unlike a single-owner console there is no "the owner" to
// pin to. Every request resolves to one member, and that member's handle decides
// the only personal directory they may write to. Identity therefore has to be
// established BEFORE any note is even built, and it must FAIL CLOSED — a request
// with no identity gets a 401 and no note shape is generated for it.
//
// Two halves:
//
//   1. EMAIL — from Cloudflare Access, which fronts the deployed host.
//      • strict  : ACCESS_TEAM_DOMAIN + ACCESS_AUD set ⇒ verify the RS256 Access
//                  JWT (Cf-Access-Jwt-Assertion / CF_Authorization) against the
//                  team's JWKS and read `email` from the VERIFIED claims. This is
//                  the mode a deploy should run in.
//      • header  : no ACCESS_* vars ⇒ trust `Cf-Access-Authenticated-User-Email`,
//                  the same header website/functions/api/*.js already trusts. Only
//                  sound because wrangler.jsonc sets workers_dev:false and routes
//                  the Worker exclusively at an Access-gated custom domain, so no
//                  un-gated hostname can reach it and spoof the header.
//      • dev     : DEV_USER_EMAIL set (and Access NOT configured) ⇒ that email.
//                  Ignored outright in strict mode, so a stray var on a deployed
//                  Worker cannot open a bypass.
//
//   2. HANDLE — email → HANDLES KV (binding `HANDLES`, the same namespace the
//      website's contributor registry uses). Records are
//      {email → {handle, name, url, bio}}. No record ⇒ 403 not_registered, exactly
//      like website/functions/api/me.js. The handle is then mapped to the member's
//      raw-notes directory.

/* ------------------------------ handle → directory ------------------------------ */

// The repo's per-member directories (CLAUDE.md "Per-collaborator directories" +
// raw-notes/README.md). `commons` is shared and is NOT a personal target.
export const MEMBER_DIRS = ["aneesh", "brandon", "florian", "ivo", "kyle", "patrick", "sean", "venkat"];

// Handles that don't equal their directory name. Venkat writes as `vgr` on the
// website (website/content/articles/*.json, devlog bylines) but owns raw-notes/venkat/.
const HANDLE_DIR_OVERRIDES = { vgr: "venkat" };

/** Filesystem-safe slug for a handle, so a KV record can never inject a path. */
function safeSegment(s) {
  return String(s || "")
    .toLowerCase()
    .replace(/[^a-z0-9_-]+/g, "-")
    .replace(/^-+|-+$/g, "")
    .slice(0, 40);
}

/**
 * Map a handle to its raw-notes directory.
 * Returns { dir, known } — `known:false` means the directory does not exist in the
 * repo yet, which is a UI hint ("this will create raw-notes/<dir>/"), not an error.
 */
export function handleToDir(handle) {
  const h = safeSegment(handle);
  const dir = HANDLE_DIR_OVERRIDES[h] || h;
  return { dir, known: MEMBER_DIRS.includes(dir) };
}

/* --------------------------------- Access JWT ---------------------------------- */

function b64urlToBytes(b64url) {
  let s = String(b64url).replace(/-/g, "+").replace(/_/g, "/");
  const rem = s.length % 4;
  if (rem) s += "=".repeat(4 - rem);
  const bin = atob(s);
  const out = new Uint8Array(bin.length);
  for (let i = 0; i < bin.length; i++) out[i] = bin.charCodeAt(i);
  return out;
}

function b64urlToJson(b64url) {
  return JSON.parse(new TextDecoder().decode(b64urlToBytes(b64url)));
}

function parseJwt(token) {
  const parts = String(token || "").split(".");
  if (parts.length !== 3) return null;
  const [headerB64, payloadB64, signatureB64] = parts;
  if (!headerB64 || !payloadB64 || !signatureB64) return null;
  try {
    return {
      header: b64urlToJson(headerB64),
      payload: b64urlToJson(payloadB64),
      headerB64,
      payloadB64,
      signatureB64,
    };
  } catch {
    return null;
  }
}

/** The Access token: injected header first, then the browser session cookie. */
function readAccessToken(request) {
  const hdr = request.headers.get("Cf-Access-Jwt-Assertion");
  if (hdr) return hdr.trim();
  const cookie = request.headers.get("Cookie") || "";
  const m = cookie.match(/(?:^|;\s*)CF_Authorization=([^;]+)/);
  return m ? decodeURIComponent(m[1]).trim() : null;
}

// Access rotates its signing keys, so cache the JWK set module-side with a short TTL
// and re-fetch once on an unknown `kid`.
let _certs = { domain: null, keys: null, at: 0 };
const CERTS_TTL_MS = 60 * 60 * 1000;

async function getJwk(teamDomain, kid) {
  const fresh = _certs.keys && _certs.domain === teamDomain && Date.now() - _certs.at < CERTS_TTL_MS;
  if (fresh) {
    const hit = _certs.keys.find((k) => k.kid === kid);
    if (hit) return hit;
  }
  const r = await fetch(`https://${teamDomain}/cdn-cgi/access/certs`, { headers: { accept: "application/json" } });
  if (!r.ok) throw new Error(`Access certs ${r.status}`);
  const data = await r.json();
  const keys = Array.isArray(data.keys) ? data.keys : [];
  _certs = { domain: teamDomain, keys, at: Date.now() };
  return keys.find((k) => k.kid === kid) || null;
}

async function verifySignature(jwk, headerB64, payloadB64, signatureB64) {
  const key = await crypto.subtle.importKey("jwk", jwk, { name: "RSASSA-PKCS1-v1_5", hash: "SHA-256" }, false, ["verify"]);
  return crypto.subtle.verify(
    { name: "RSASSA-PKCS1-v1_5" },
    key,
    b64urlToBytes(signatureB64),
    new TextEncoder().encode(`${headerB64}.${payloadB64}`)
  );
}

function claimsValid(payload, env) {
  const now = Math.floor(Date.now() / 1000);
  const skew = 60;
  const aud = payload.aud;
  const audOk = Array.isArray(aud) ? aud.includes(env.ACCESS_AUD) : aud === env.ACCESS_AUD;
  if (!audOk) return false;
  if (payload.iss !== `https://${env.ACCESS_TEAM_DOMAIN}`) return false;
  if (typeof payload.exp !== "number" || payload.exp <= now - skew) return false;
  if (typeof payload.nbf === "number" && payload.nbf > now + skew) return false;
  if (typeof payload.iat === "number" && payload.iat > now + skew) return false;
  return true;
}

/* ------------------------------- email resolution ------------------------------- */

/** Which identity mode this Worker is running in (also surfaced by /api/config). */
export function authMode(env) {
  if (env && env.ACCESS_TEAM_DOMAIN && env.ACCESS_AUD) return "access-jwt";
  if (env && env.DEV_USER_EMAIL) return "dev";
  return "access-header";
}

/**
 * Resolve the caller's email. Returns { ok, email, via } or { ok:false, error }.
 * Never throws; any crypto/network failure is a hard deny.
 */
export async function resolveEmail(request, env) {
  const mode = authMode(env);

  if (mode === "access-jwt") {
    const token = readAccessToken(request);
    if (!token) return { ok: false, error: "no Access token on this request" };
    const parsed = parseJwt(token);
    if (!parsed) return { ok: false, error: "malformed Access token" };
    const { header, payload, headerB64, payloadB64, signatureB64 } = parsed;
    // Access signs RS256 with a kid; anything else is alg-confusion bait.
    if (!header || header.alg !== "RS256" || !header.kid) return { ok: false, error: "unexpected token algorithm" };
    try {
      const jwk = await getJwk(env.ACCESS_TEAM_DOMAIN, header.kid);
      if (!jwk) return { ok: false, error: "unknown signing key" };
      if (!(await verifySignature(jwk, headerB64, payloadB64, signatureB64))) return { ok: false, error: "bad signature" };
      if (!claimsValid(payload, env)) return { ok: false, error: "claims rejected" };
      const email = String(payload.email || "").trim();
      if (!email) return { ok: false, error: "token carries no email" };
      return { ok: true, email, via: "access-jwt" };
    } catch {
      return { ok: false, error: "Access verification failed" };
    }
  }

  // Edge-trust mode: the header Access injects, then the session cookie's payload
  // (unverified — same fallback website/functions/api/me.js uses).
  const header = request.headers.get("Cf-Access-Authenticated-User-Email");
  if (header && header.trim()) return { ok: true, email: header.trim(), via: "access-header" };
  const token = readAccessToken(request);
  if (token) {
    const parsed = parseJwt(token);
    const email = parsed && parsed.payload && parsed.payload.email;
    if (email) return { ok: true, email: String(email).trim(), via: "access-cookie" };
  }

  // Local development only. Unreachable in strict mode by construction.
  if (mode === "dev") return { ok: true, email: String(env.DEV_USER_EMAIL).trim(), via: "dev" };

  return { ok: false, error: "no identity — this app must be reached through Cloudflare Access" };
}

/* ------------------------------ identity resolution ----------------------------- */

/**
 * resolveIdentity — email → HANDLES KV → the member record Scribe writes as.
 *
 * Returns { ok:true, identity:{ email, handle, name, url, bio, dir, dirKnown, via } }
 * or { ok:false, status, error } where status is 401 (no identity) or 403 (identity
 * but no HANDLES record / unusable handle).
 */
export async function resolveIdentity(request, env) {
  const who = await resolveEmail(request, env);
  if (!who.ok) return { ok: false, status: 401, error: who.error };

  const email = who.email;

  let raw = null;
  if (env.HANDLES) {
    try {
      raw = await env.HANDLES.get(email);
      // KV keys are the exact email string the site stored; retry lower-cased so a
      // capitalised Access identity still resolves.
      if (!raw && email !== email.toLowerCase()) raw = await env.HANDLES.get(email.toLowerCase());
    } catch {
      raw = null;
    }
  }

  let record = null;
  if (raw) {
    try {
      record = JSON.parse(raw);
    } catch {
      record = { handle: raw }; // legacy bare-string values (website contributors.js allows this)
    }
  }

  // DEV ONLY: with no KV record and no Access in front, fall back to DEV_HANDLE (or
  // the email's local part) so `wrangler dev` works against an empty local KV. This
  // branch is dead in strict mode — authMode() returns "dev" only when ACCESS_* are
  // both unset — so a deployed Worker can never mint a handle for a stranger.
  if (!record && authMode(env) === "dev" && who.via === "dev") {
    record = { handle: env.DEV_HANDLE || email.split("@")[0], name: env.DEV_NAME || "", dev: true };
  }

  if (!record || !record.handle) {
    return {
      ok: false,
      status: 403,
      error: `not_registered: ${email} has no HANDLES record. Ask a curator to add one (see website/admin/handles.html).`,
    };
  }

  const { dir, known } = handleToDir(record.handle);
  if (!dir) return { ok: false, status: 403, error: "handle does not map to a usable directory name" };

  return {
    ok: true,
    identity: {
      email,
      handle: record.handle,
      name: record.name || record.handle,
      url: record.url || "",
      bio: record.bio || "",
      dir,
      dirKnown: known,
      via: who.via,
    },
  };
}
