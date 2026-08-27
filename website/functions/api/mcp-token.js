// Self-serve MCP access-token endpoint (the Witness server's bearer tokens).
//
//   POST   /api/mcp-token            mint a token, returns it once, in full
//   GET    /api/mcp-token            list the caller's live tokens, masked
//   DELETE /api/mcp-token {id}       revoke one of the caller's tokens
//
// Sits behind the "World Machines members" Cloudflare Access application and
// re-checks the Access identity itself (functions/_lib/access.js), then
// resolves email → HANDLES profile before minting.
//
// Token contract (fixed — validated by the separate Witness worker):
//   KV binding MCP_TOKENS
//   key   = token string  "wmk_<32 hex chars>"
//   value = JSON.stringify({ handle, email, created, exp })   (unix seconds)
//   written with { expirationTtl: 7776000 }  (90 days)
//
// The same {handle,email,created,exp} is also written as KV *metadata*, which
// list() returns without a read per key — that is what makes the "your tokens"
// list cheap. The Witness only reads the value, so metadata is additive.
//
// Tokens are never listed in full after minting. Each is identified by
// id = sha256(token)[0..16], derived on the fly, so a stolen listing cannot be
// replayed as a token.

import { requireMember, blockCrossOrigin, NO_STORE } from '../_lib/access.js';

const TOKEN_TTL_SECONDS = 7776000; // 90 days
const WITNESS_MCP_URL = 'https://witness.worldmachines.org/mcp';
const ORACLE_MCP_URL = 'https://oracle.worldmachines.org/mcp';
const LIST_LIMIT = 1000;
const LEGACY_READ_LIMIT = 50; // tokens minted before metadata existed

const hex = (bytes) => Array.from(bytes, (b) => b.toString(16).padStart(2, '0')).join('');

async function tokenId(token) {
  const digest = await crypto.subtle.digest('SHA-256', new TextEncoder().encode(token));
  return hex(new Uint8Array(digest)).slice(0, 16);
}

function mask(token) {
  return `${token.slice(0, 10)}…${token.slice(-4)}`;
}

// Every live token owned by `email`, newest first.
async function ownedTokens(env, email) {
  const listed = await env.MCP_TOKENS.list({ limit: LIST_LIMIT });
  const mine = [];
  let legacyReads = 0;

  for (const key of listed.keys) {
    let meta = key.metadata;
    if (!meta || !meta.email) {
      // Pre-metadata token: fall back to reading the value, bounded.
      if (legacyReads >= LEGACY_READ_LIMIT) continue;
      legacyReads += 1;
      const raw = await env.MCP_TOKENS.get(key.name);
      if (!raw) continue;
      try {
        meta = JSON.parse(raw);
      } catch {
        continue;
      }
    }
    if (String(meta.email || '').toLowerCase() !== email) continue;
    mine.push({ name: key.name, meta });
  }

  mine.sort((a, b) => (b.meta.created || 0) - (a.meta.created || 0));
  return mine;
}

export async function onRequestPost(ctx) {
  const crossOrigin = blockCrossOrigin(ctx.request);
  if (crossOrigin) return crossOrigin;

  const member = await requireMember(ctx);
  if (member.denied) return member.denied;

  const token = `wmk_${hex(crypto.getRandomValues(new Uint8Array(16)))}`;
  const created = Math.floor(Date.now() / 1000);
  const exp = created + TOKEN_TTL_SECONDS;
  const record = { handle: member.handle, email: member.email, created, exp };

  await ctx.env.MCP_TOKENS.put(token, JSON.stringify(record), {
    expirationTtl: TOKEN_TTL_SECONDS,
    metadata: record,
  });

  return Response.json(
    {
      token,
      id: await tokenId(token),
      created,
      exp,
      witness_mcp_url: WITNESS_MCP_URL,
      oracle_mcp_url: ORACLE_MCP_URL,
    },
    { headers: NO_STORE }
  );
}

export async function onRequestGet(ctx) {
  const member = await requireMember(ctx);
  if (member.denied) return member.denied;

  const mine = await ownedTokens(ctx.env, member.email);
  const tokens = await Promise.all(
    mine.map(async ({ name, meta }) => ({
      id: await tokenId(name),
      masked: mask(name),
      created: meta.created || null,
      exp: meta.exp || null,
    }))
  );

  return Response.json(
    { handle: member.handle, tokens, witness_mcp_url: WITNESS_MCP_URL, oracle_mcp_url: ORACLE_MCP_URL },
    { headers: NO_STORE }
  );
}

export async function onRequestDelete(ctx) {
  const crossOrigin = blockCrossOrigin(ctx.request);
  if (crossOrigin) return crossOrigin;

  const member = await requireMember(ctx);
  if (member.denied) return member.denied;

  let body;
  try {
    body = await ctx.request.json();
  } catch {
    return Response.json({ error: 'invalid_json', message: 'Invalid JSON' }, { status: 400 });
  }

  // Accept the id from the listing, or the full token straight from the box.
  const wanted = String(body.id || body.token || '').trim();
  if (!wanted) {
    return Response.json({ error: 'id_required', message: 'id or token is required' }, { status: 400 });
  }

  for (const { name } of await ownedTokens(ctx.env, member.email)) {
    if (name === wanted || (await tokenId(name)) === wanted) {
      await ctx.env.MCP_TOKENS.delete(name);
      return Response.json({ ok: true, revoked: await tokenId(name) }, { headers: NO_STORE });
    }
  }

  // Not found *or* not yours — same answer either way, so this cannot be used
  // to probe whether a token exists.
  return Response.json(
    { error: 'not_found', message: 'No such token on this account.' },
    { status: 404, headers: NO_STORE }
  );
}
