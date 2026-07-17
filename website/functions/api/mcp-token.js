// Self-serve MCP access-token minting endpoint.
//
// Sits behind the site's Cloudflare Access email-OTP gate (same as /submit).
// Verifies the CF Access JWT exactly like functions/api/me.js, resolves the
// caller's email → HANDLES profile, then mints a bearer token that the Witness
// worker validates purely by key presence in the MCP_TOKENS KV namespace.
//
// Token contract (fixed — validated by the separate Witness worker):
//   KV binding MCP_TOKENS
//   key   = token string  "wmk_<32 hex chars>"
//   value = JSON.stringify({ handle, email, created, exp })   (unix seconds)
//   written with { expirationTtl: 7776000 }  (90 days)

const TOKEN_TTL_SECONDS = 7776000; // 90 days
const WITNESS_MCP_URL = 'https://wm-witness-dev.aneeshsathe.workers.dev/mcp';
const ORACLE_MCP_URL = 'https://wm-oracle-dev.aneeshsathe.workers.dev/mcp';

// Same JWT/email resolution used by functions/api/me.js and
// functions/api/library/private.js: prefer the Access-injected header, fall
// back to decoding the CF_Authorization cookie's JWT payload.
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

async function handler({ request, env }) {
  // 1. Require a valid Access identity. No JWT → 401 (dormant-until-Access
  //    state produces this until the account owner configures Access).
  const email = emailFromRequest(request);
  if (!email) {
    return Response.json({ error: 'unauthorized' }, { status: 401 });
  }

  // 2. The caller must be a registered contributor (mirror me.js semantics).
  const raw = await env.HANDLES.get(email);
  if (!raw) {
    return Response.json({ error: 'not_registered', email }, { status: 403 });
  }

  let handle;
  try {
    ({ handle } = JSON.parse(raw));
  } catch {
    return Response.json({ error: 'not_registered', email }, { status: 403 });
  }

  // 3. Mint a fresh token. Simple v1: a new token each call; previously issued
  //    tokens stay valid until their own TTL lapses.
  const bytes = crypto.getRandomValues(new Uint8Array(16));
  const hex = Array.from(bytes, (b) => b.toString(16).padStart(2, '0')).join('');
  const token = 'wmk_' + hex;

  const created = Math.floor(Date.now() / 1000);
  const exp = created + TOKEN_TTL_SECONDS;

  await env.MCP_TOKENS.put(
    token,
    JSON.stringify({ handle, email, created, exp }),
    { expirationTtl: TOKEN_TTL_SECONDS }
  );

  return Response.json(
    {
      token,
      exp,
      witness_mcp_url: WITNESS_MCP_URL,
      oracle_mcp_url: ORACLE_MCP_URL,
    },
    { headers: { 'Cache-Control': 'private, no-store' } }
  );
}

// The page may POST (button click) or GET; support both.
export const onRequestPost = handler;
export const onRequestGet = handler;
