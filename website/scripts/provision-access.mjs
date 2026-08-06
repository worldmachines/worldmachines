#!/usr/bin/env node
/**
 * provision-access.mjs — create/update the two Cloudflare Access applications
 * that make member login work, idempotently, from the command line.
 *
 *   "World Machines members"  → /login, /profile, /submit, /api/submit,
 *                               /api/profile, /api/mcp-token,
 *                               /api/library/private, /api/pdf/private/*
 *                               policy: every email in the HANDLES KV
 *   "World Machines admin"    → /admin*, /api/admin*
 *                               policy: ADMIN_EMAILS (default: Aneesh)
 *
 * Both use One-time PIN (email OTP) and a ~1 week session.
 *
 * Usage
 *   node scripts/provision-access.mjs                # dry run (default)
 *   node scripts/provision-access.mjs --apply        # actually write
 *   node scripts/provision-access.mjs --json         # machine-readable plan
 *
 * Env
 *   CLOUDFLARE_API_TOKEN   required. Needs, on the account:
 *                            Access: Apps and Policies  Edit
 *                            Access: Organizations, Identity Providers, and Groups  Read
 *                            Workers KV Storage  Read      (to read the member list)
 *                            Cloudflare Pages  Read        (to discover hostnames)
 *                            Zone  Read                    (to check zone ownership)
 *   CLOUDFLARE_ACCOUNT_ID  required.
 *   ADMIN_EMAILS           optional, comma-separated. Keep this the same value
 *                          as the Pages ADMIN_EMAILS variable that
 *                          functions/_lib/access.js reads — the effective admin
 *                          set is the intersection of the two.
 *
 * Flags
 *   --apply             perform the writes (default is --dry-run)
 *   --emails a@b,c@d    member allowlist override (default: keys of HANDLES KV)
 *   --admin-emails ...  admin allowlist override
 *   --hostnames a,b     hostname override (default: discovered from the Pages
 *                       project, filtered to zones on this account)
 *   --session 168h      session duration
 *   --legacy-domains    send self_hosted_domains instead of destinations
 *   --json              print the plan as JSON and nothing else
 *   --verbose           echo every API call
 *
 * NOTE — this file is served publicly (website/ is the Pages build output, so
 * scripts/*.py is already readable at worldmachines.org/scripts/...). Member
 * emails therefore must NOT be written into it; they are read at run time from
 * the HANDLES KV namespace, which is also the list that actually matters.
 *
 * The script owns these two applications completely: on update it PUTs the
 * full desired configuration, so any field changed by hand in the dashboard is
 * reset. Rename the app in the dashboard if you want to hand-manage it.
 */

import { readFileSync } from 'node:fs';
import { dirname, resolve } from 'node:path';
import { fileURLToPath } from 'node:url';

// ── Constants ─────────────────────────────────────────────────────────

// CF_API_BASE exists so the script can be exercised against a stub server.
const API = process.env.CF_API_BASE || 'https://api.cloudflare.com/client/v4';
const PAGES_PROJECT = 'worldmachines';
const KV_BINDING = 'HANDLES';

// Fallback hostnames, used only when discovery finds nothing.
const FALLBACK_HOSTNAMES = ['worldmachines.org', 'worldmachines-2rd.pages.dev'];

const MEMBERS_APP = 'World Machines members';
const ADMIN_APP = 'World Machines admin';

// Access rejects more than 5 destinations per application (code 12130; the
// dashboard greys out "add domain" at the same point). A logical app whose
// hostname × path matrix exceeds that is split into "<name>", "<name> (2)", …
// all attached to the same reusable policy, which is invisible to members —
// Access SSO reissues the session token per app on the same hostname.
const MAX_DESTINATIONS = 5;

function chunkApp(name, uris) {
  const chunks = [];
  for (let i = 0; i < uris.length; i += MAX_DESTINATIONS) {
    chunks.push({
      name: chunks.length === 0 ? name : `${name} (${chunks.length + 1})`,
      uris: uris.slice(i, i + MAX_DESTINATIONS),
    });
  }
  return chunks;
}
const MEMBERS_POLICY = 'World Machines members — email allowlist';
const ADMIN_POLICY = 'World Machines admin — email allowlist';

// Derived from the code: every path that must not answer without a session.
// /api/me is deliberately NOT here — public pages fetch it to decide whether to
// show a sign-in prompt, and an Access-gated endpoint answers an anonymous
// fetch() with a cross-origin redirect JS cannot read. It verifies the Access
// JWT itself (functions/_lib/access.js) and returns a clean 401 instead.
const MEMBER_PATHS = [
  '/login*', // the redirector: hitting it with no session is what triggers OTP
  '/profile*',
  '/submit*',
  '/api/submit*',
  '/api/profile*',
  '/api/mcp-token*',
  '/api/library/private*',
  '/api/pdf/private/*',
];

// The original bug: a policy on /admin/* only, while the API lives at
// /api/admin/*. Both, always.
const ADMIN_PATHS = ['/admin*', '/api/admin*'];

const DEFAULT_ADMIN_EMAILS = ['mail@aneeshsathe.com'];
const DEFAULT_SESSION = '168h'; // ~1 week

// ── CLI ───────────────────────────────────────────────────────────────

function parseArgs(argv) {
  const opts = {
    apply: false,
    json: false,
    verbose: false,
    legacyDomains: false,
    emails: null,
    adminEmails: null,
    hostnames: null,
    session: DEFAULT_SESSION,
  };
  for (let i = 0; i < argv.length; i++) {
    const arg = argv[i];
    const value = () => (arg.includes('=') ? arg.slice(arg.indexOf('=') + 1) : argv[++i]);
    if (arg === '--apply') opts.apply = true;
    else if (arg === '--dry-run') opts.apply = false;
    else if (arg === '--json') opts.json = true;
    else if (arg === '--verbose' || arg === '-v') opts.verbose = true;
    else if (arg === '--legacy-domains') opts.legacyDomains = true;
    else if (arg.startsWith('--emails')) opts.emails = splitList(value());
    else if (arg.startsWith('--admin-emails')) opts.adminEmails = splitList(value());
    else if (arg.startsWith('--hostnames')) opts.hostnames = splitList(value());
    else if (arg.startsWith('--session')) opts.session = value();
    else if (arg === '--help' || arg === '-h') opts.help = true;
    else throw new Error(`unknown argument: ${arg}`);
  }
  return opts;
}

const splitList = (raw) => String(raw || '').split(',').map((s) => s.trim()).filter(Boolean);

// ── Cloudflare API ────────────────────────────────────────────────────

class CfError extends Error {
  constructor(method, path, status, errors) {
    super(`${method} ${path} → HTTP ${status}: ${JSON.stringify(errors)}`);
    this.status = status;
    this.errors = errors || [];
  }
}

function makeClient(token, { verbose }) {
  return async function cf(method, path, body) {
    if (verbose) process.stderr.write(`→ ${method} ${path}\n`);
    const res = await fetch(`${API}${path}`, {
      method,
      headers: {
        Authorization: `Bearer ${token}`,
        'Content-Type': 'application/json',
      },
      body: body === undefined ? undefined : JSON.stringify(body),
    });
    let payload = {};
    try {
      payload = await res.json();
    } catch {
      /* non-JSON error page */
    }
    if (!res.ok || payload.success === false) {
      throw new CfError(method, path, res.status, payload.errors || payload);
    }
    return payload.result;
  };
}

function curlFor(method, path, body) {
  const head = `curl -X ${method} '${API}${path}' \\\n  -H 'Authorization: Bearer $CLOUDFLARE_API_TOKEN' \\\n  -H 'Content-Type: application/json'`;
  return body === undefined ? head : `${head} \\\n  --data '${JSON.stringify(body)}'`;
}

// ── Discovery ─────────────────────────────────────────────────────────

// Tolerant JSONC read of website/wrangler.jsonc — for the HANDLES namespace id,
// so this script and the deployed Worker can never disagree about it.
function kvNamespaceId() {
  const here = dirname(fileURLToPath(import.meta.url));
  const raw = readFileSync(resolve(here, '..', 'wrangler.jsonc'), 'utf8');
  const stripped = raw
    .replace(/\/\*[\s\S]*?\*\//g, '')
    .split('\n')
    .map((line) => line.replace(/(^|\s)\/\/.*$/, ''))
    .join('\n');
  const config = JSON.parse(stripped);
  const ns = (config.kv_namespaces || []).find((n) => n.binding === KV_BINDING);
  if (!ns) throw new Error(`no ${KV_BINDING} binding in website/wrangler.jsonc`);
  return ns.id;
}

async function kvEmails(cf, accountId, namespaceId) {
  const emails = [];
  let cursor = '';
  do {
    const query = `?limit=1000${cursor ? `&cursor=${encodeURIComponent(cursor)}` : ''}`;
    const res = await fetch(
      `${API}/accounts/${accountId}/storage/kv/namespaces/${namespaceId}/keys${query}`,
      { headers: { Authorization: `Bearer ${cf.token}` } }
    );
    const payload = await res.json();
    if (!res.ok || payload.success === false) {
      throw new CfError('GET', `/accounts/…/storage/kv/namespaces/${namespaceId}/keys`, res.status, payload.errors);
    }
    for (const key of payload.result || []) {
      const name = String(key.name || '').trim().toLowerCase();
      if (name.includes('@')) emails.push(name);
    }
    cursor = (payload.result_info && payload.result_info.cursor) || '';
  } while (cursor);
  return [...new Set(emails)].sort();
}

/** Which of the wanted hostnames this account can actually put Access in front of. */
function usableHostnames(candidates, zones, pagesSubdomain) {
  const usable = [];
  const skipped = [];
  for (const host of candidates) {
    if (pagesSubdomain && host === pagesSubdomain) {
      usable.push(host);
      continue;
    }
    const zone = zones.find((z) => host === z || host.endsWith(`.${z}`));
    if (zone) usable.push(host);
    else {
      skipped.push({
        hostname: host,
        reason: host.endsWith('.pages.dev')
          ? `not this account's Pages subdomain (${pagesSubdomain || 'unknown'})`
          : 'no matching zone on this account — Access applications can only cover hostnames whose zone lives here',
      });
    }
  }
  return { usable, skipped };
}

// ── Desired state ─────────────────────────────────────────────────────

function destinationsFor(hostnames, paths) {
  const out = [];
  for (const host of hostnames) for (const path of paths) out.push(`${host}${path}`);
  return out;
}

function appBody({ name, uris, session, idps, denyUrl, policies, legacyDomains }) {
  const body = {
    name,
    type: 'self_hosted',
    domain: uris[0],
    session_duration: session,
    app_launcher_visible: false,
    skip_interstitial: true,
    allowed_idps: idps,
    // A single IdP means we can skip the "choose a login method" screen and go
    // straight to the email box.
    auto_redirect_to_identity: idps.length === 1,
    ...(denyUrl ? { custom_deny_url: denyUrl } : {}),
  };
  if (legacyDomains) body.self_hosted_domains = uris;
  else body.destinations = uris.map((uri) => ({ type: 'public', uri }));
  if (policies) body.policies = policies.map((id, index) => ({ id, precedence: index + 1 }));
  return body;
}

const policyBody = (name, emails) => ({
  name,
  decision: 'allow',
  include: emails.map((email) => ({ email: { email } })),
});

// ── Diffing ───────────────────────────────────────────────────────────

const sameSet = (a, b) =>
  a.length === b.length && [...a].sort().join('\u0000') === [...b].sort().join('\u0000');

function existingUris(app) {
  if (Array.isArray(app.destinations)) return app.destinations.filter((d) => d.type === 'public').map((d) => d.uri);
  if (Array.isArray(app.self_hosted_domains)) return app.self_hosted_domains;
  return app.domain ? [app.domain] : [];
}

function diffApp(existing, desired) {
  if (!existing) return { action: 'create', changes: null };
  const changes = {};
  const compare = (field, from, to, set = false) => {
    const equal = set ? sameSet(from || [], to || []) : JSON.stringify(from) === JSON.stringify(to);
    if (!equal) changes[field] = { from, to };
  };
  compare('destinations', existingUris(existing), desired.destinations
    ? desired.destinations.map((d) => d.uri)
    : desired.self_hosted_domains, true);
  compare('session_duration', existing.session_duration, desired.session_duration);
  compare('allowed_idps', existing.allowed_idps || [], desired.allowed_idps, true);
  compare('auto_redirect_to_identity', !!existing.auto_redirect_to_identity, desired.auto_redirect_to_identity);
  compare('app_launcher_visible', !!existing.app_launcher_visible, desired.app_launcher_visible);
  compare('skip_interstitial', !!existing.skip_interstitial, desired.skip_interstitial);
  compare(
    'policies',
    (existing.policies || []).map((p) => p.id),
    (desired.policies || []).map((p) => p.id),
    true
  );
  return { action: Object.keys(changes).length ? 'update' : 'unchanged', changes };
}

function diffPolicy(existing, desired) {
  if (!existing) return { action: 'create', changes: null };
  const changes = {};
  const from = (existing.include || []).map((r) => r.email && r.email.email).filter(Boolean).sort();
  const to = desired.include.map((r) => r.email.email).sort();
  if (!sameSet(from, to)) changes.include = { from, to };
  if (existing.decision !== desired.decision) changes.decision = { from: existing.decision, to: desired.decision };
  return { action: Object.keys(changes).length ? 'update' : 'unchanged', changes };
}

// ── Main ──────────────────────────────────────────────────────────────

async function main() {
  const opts = parseArgs(process.argv.slice(2));
  if (opts.help) {
    process.stdout.write(readFileSync(fileURLToPath(import.meta.url), 'utf8').split('*/')[0] + '*/\n');
    return 0;
  }

  const token = process.env.CLOUDFLARE_API_TOKEN;
  const accountId = process.env.CLOUDFLARE_ACCOUNT_ID;
  if (!token || !accountId) {
    throw new Error('CLOUDFLARE_API_TOKEN and CLOUDFLARE_ACCOUNT_ID must both be set');
  }

  const cf = makeClient(token, opts);
  cf.token = token;
  // --json keeps stdout pure: the plan goes to stdout, everything else to stderr.
  const log = (line = '') => (opts.json ? process.stderr : process.stdout).write(`${line}\n`);

  // ── read current state ──
  const account = await cf('GET', `/accounts/${accountId}`);
  const org = await cf('GET', `/accounts/${accountId}/access/organizations`).catch(() => null);
  const teamDomain = org && org.auth_domain ? org.auth_domain : null;

  const zones = (await cf('GET', `/zones?account.id=${accountId}&per_page=50`).catch(() => []) || []).map(
    (z) => z.name
  );

  let pagesSubdomain = null;
  let pagesDomains = [];
  try {
    const project = await cf('GET', `/accounts/${accountId}/pages/projects/${PAGES_PROJECT}`);
    pagesSubdomain = project.subdomain || null;
    pagesDomains = project.domains || [];
  } catch {
    /* Pages read not permitted, or project renamed — fall back to constants */
  }

  const idps = (await cf('GET', `/accounts/${accountId}/access/identity_providers`).catch(() => [])) || [];
  const otp = idps.find((i) => i.type === 'onetimepin');
  const allowedIdps = otp ? [otp.id] : [];

  const apps = (await cf('GET', `/accounts/${accountId}/access/apps?per_page=50`)) || [];
  const policies = (await cf('GET', `/accounts/${accountId}/access/policies?per_page=50`).catch(() => [])) || [];

  // ── work out who and where ──
  const candidateHosts = opts.hostnames
    ? opts.hostnames
    : [...new Set([...pagesDomains, ...(pagesSubdomain ? [pagesSubdomain] : []), ...FALLBACK_HOSTNAMES])];
  const { usable: hostnames, skipped } = opts.hostnames
    ? { usable: opts.hostnames, skipped: [] }
    : usableHostnames(candidateHosts, zones, pagesSubdomain);

  if (!hostnames.length) {
    throw new Error(
      `no usable hostnames. Zones on this account: ${zones.join(', ') || '(none)'}; ` +
        `Pages subdomain: ${pagesSubdomain || '(unknown)'}. Pass --hostnames to override.`
    );
  }

  const memberEmails = opts.emails || (await kvEmails(cf, accountId, kvNamespaceId()));
  if (!memberEmails.length) throw new Error('member email list is empty — refusing to create a policy nobody matches');

  const adminEmails = opts.adminEmails || splitList(process.env.ADMIN_EMAILS) || [];
  const admins = adminEmails.length ? adminEmails : DEFAULT_ADMIN_EMAILS;

  // ── desired state ──
  const desiredPolicies = [
    { name: MEMBERS_POLICY, body: policyBody(MEMBERS_POLICY, memberEmails) },
    { name: ADMIN_POLICY, body: policyBody(ADMIN_POLICY, admins) },
  ];
  const policyPlan = desiredPolicies.map((p) => {
    const existing = policies.find((x) => x.name === p.name) || null;
    return { ...p, existing, ...diffPolicy(existing, p.body) };
  });

  const desiredApps = [];
  for (const spec of [
    {
      name: MEMBERS_APP,
      policyName: MEMBERS_POLICY,
      uris: destinationsFor(hostnames, MEMBER_PATHS),
      denyUrl: `https://${hostnames[0]}/join`,
    },
    {
      name: ADMIN_APP,
      policyName: ADMIN_POLICY,
      uris: destinationsFor(hostnames, ADMIN_PATHS),
      denyUrl: null,
    },
  ]) {
    for (const chunk of chunkApp(spec.name, spec.uris)) {
      desiredApps.push({ ...spec, name: chunk.name, uris: chunk.uris });
    }
  }

  // A previous run with more hostnames may have left higher-numbered chunk
  // apps behind. Never delete — surface them for a human.
  const staleChunks = apps.filter(
    (x) =>
      [MEMBERS_APP, ADMIN_APP].some((base) => new RegExp(`^${base} \\(\\d+\\)$`).test(x.name)) &&
      !desiredApps.some((d) => d.name === x.name)
  );

  const appPlan = desiredApps.map((a) => {
    const existing = apps.find((x) => x.name === a.name) || null;
    const policy = policyPlan.find((p) => p.name === a.policyName);
    const policyIds = policy.existing ? [policy.existing.id] : ['<policy id from this run>'];
    const body = appBody({
      name: a.name,
      uris: a.uris,
      session: opts.session,
      idps: allowedIdps,
      denyUrl: a.denyUrl,
      policies: policyIds,
      legacyDomains: opts.legacyDomains,
    });
    return { ...a, existing, body, ...diffApp(existing, body) };
  });

  // ── report ──
  const plan = {
    mode: opts.apply ? 'apply' : 'dry-run',
    account: { id: accountId, name: account.name },
    team_domain: teamDomain,
    identity_provider: otp ? { id: otp.id, name: otp.name, type: otp.type } : null,
    hostnames,
    skipped_hostnames: skipped,
    session_duration: opts.session,
    member_emails: memberEmails,
    admin_emails: admins,
    policies: policyPlan.map((p) => ({ name: p.name, action: p.action, changes: p.changes })),
    applications: appPlan.map((a) => ({
      name: a.name,
      action: a.action,
      changes: a.changes,
      aud: a.existing ? a.existing.aud : null,
      destinations: a.uris,
    })),
  };

  if (opts.json) process.stdout.write(`${JSON.stringify(plan, null, 2)}\n`);

  log(`Cloudflare account : ${account.name} (${accountId})`);
  log(`Access team domain : ${teamDomain || '(none — Zero Trust has never been set up on this account)'}`);
  log(`Identity provider  : ${otp ? `${otp.name} [onetimepin] ${otp.id}` : '(no One-time PIN provider found — Access will offer every configured IdP)'}`);
  log(`Hostnames          : ${hostnames.join(', ')}`);
  for (const s of skipped) log(`  ! skipping ${s.hostname} — ${s.reason}`);
  log(`Members            : ${memberEmails.length} emails from ${opts.emails ? '--emails' : `${KV_BINDING} KV`}`);
  log(`Admins             : ${admins.join(', ')}`);
  log(`Session duration   : ${opts.session}`);
  for (const s of staleChunks) {
    log(`  ! stale chunk app "${s.name}" (${existingUris(s).length} destinations) — no longer needed; delete it in Zero Trust → Access → Applications`);
  }
  log();

  for (const p of policyPlan) {
    log(`policy  ${p.action.toUpperCase().padEnd(9)} ${p.name}`);
    if (p.changes && Object.keys(p.changes).length) log(`        ${JSON.stringify(p.changes)}`);
  }
  for (const a of appPlan) {
    log(`app     ${a.action.toUpperCase().padEnd(9)} ${a.name}   (${a.uris.length} destinations)`);
    if (a.changes && Object.keys(a.changes).length) log(`        ${JSON.stringify(a.changes, null, 2).replace(/\n/g, '\n        ')}`);
    else if (a.action === 'create') for (const uri of a.uris) log(`        + ${uri}`);
  }
  log();

  if (!opts.apply) {
    log('DRY RUN — nothing was written. The equivalent calls would be:');
    log();
    for (const p of policyPlan) {
      if (p.action === 'unchanged') continue;
      const path = p.existing
        ? `/accounts/${accountId}/access/policies/${p.existing.id}`
        : `/accounts/${accountId}/access/policies`;
      log(curlFor(p.existing ? 'PUT' : 'POST', path, p.body));
      log();
    }
    for (const a of appPlan) {
      if (a.action === 'unchanged') continue;
      const path = a.existing
        ? `/accounts/${accountId}/access/apps/${a.existing.id}`
        : `/accounts/${accountId}/access/apps`;
      log(curlFor(a.existing ? 'PUT' : 'POST', path, a.body));
      log();
    }
    log('Re-run with --apply to perform them.');
    return 0;
  }

  // ── apply ──
  const policyIds = {};
  for (const p of policyPlan) {
    if (p.action === 'unchanged') {
      policyIds[p.name] = p.existing.id;
      log(`policy  unchanged  ${p.name}  ${p.existing.id}`);
      continue;
    }
    const result = p.existing
      ? await cf('PUT', `/accounts/${accountId}/access/policies/${p.existing.id}`, p.body)
      : await cf('POST', `/accounts/${accountId}/access/policies`, p.body);
    policyIds[p.name] = result.id;
    log(`policy  ${p.action}d  ${p.name}  ${result.id}`);
  }

  const results = [];
  for (const a of appPlan) {
    if (a.action === 'unchanged') {
      results.push({ name: a.name, id: a.existing.id, aud: a.existing.aud });
      log(`app     unchanged  ${a.name}  id=${a.existing.id}  aud=${a.existing.aud}`);
      continue;
    }
    const body = appBody({
      name: a.name,
      uris: a.uris,
      session: opts.session,
      idps: allowedIdps,
      denyUrl: a.denyUrl,
      policies: [policyIds[a.policyName]],
      legacyDomains: opts.legacyDomains,
    });
    const path = a.existing
      ? `/accounts/${accountId}/access/apps/${a.existing.id}`
      : `/accounts/${accountId}/access/apps`;
    const method = a.existing ? 'PUT' : 'POST';

    let result;
    try {
      result = await cf(method, path, body);
    } catch (err) {
      // Older Access API versions reject `destinations`; retry the deprecated
      // self_hosted_domains shape once before giving up.
      const rejectsDestinations =
        err instanceof CfError &&
        JSON.stringify(err.errors).includes('destination') &&
        !opts.legacyDomains;
      if (!rejectsDestinations) throw err;
      log(`        (destinations rejected — retrying with self_hosted_domains)`);
      result = await cf(
        method,
        path,
        appBody({ ...a, uris: a.uris, session: opts.session, idps: allowedIdps, denyUrl: a.denyUrl, policies: [policyIds[a.policyName]], legacyDomains: true })
      );
    }
    results.push({ name: a.name, id: result.id, aud: result.aud });
    log(`app     ${a.existing ? 'updated' : 'created'}  ${a.name}  id=${result.id}  aud=${result.aud}`);
  }

  log();
  log('Done. Now set these on the Pages project so the Functions verify the JWT');
  log('rather than trusting the Access-injected header:');
  log();
  log(`  npx wrangler pages project ... ACCESS_TEAM_DOMAIN = ${teamDomain || '<team>.cloudflareaccess.com'}`);
  log(`  ACCESS_AUD = ${[...new Set(results.map((r) => r.aud).filter(Boolean))].join(',')}`);
  log();
  log('(Pages → Settings → Variables and Secrets → Production + Preview, then redeploy.)');
  return 0;
}

main()
  .then((code) => process.exit(code))
  .catch((err) => {
    process.stderr.write(`\nprovision-access: ${err.message}\n`);
    if (err instanceof CfError && err.status === 403) {
      process.stderr.write(
        'The API token is missing a scope. It needs Access: Apps and Policies (Edit),\n' +
          'Access: Organizations, IdPs and Groups (Read), Workers KV Storage (Read),\n' +
          'Cloudflare Pages (Read) and Zone (Read), all on the account.\n'
      );
    }
    process.exit(1);
  });
