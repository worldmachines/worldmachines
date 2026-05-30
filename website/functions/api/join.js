export async function onRequestPost({ request, env }) {
  let body;
  try { body = await request.json(); } catch {
    return Response.json({ error: 'Invalid request' }, { status: 400 });
  }

  const email  = (body.email  || '').trim();
  const name   = (body.name   || '').trim();
  const handle = (body.handle || '').trim().toLowerCase();
  const siteUrl = (body.url   || '').trim() || null;
  const bio    = (body.bio    || '').trim() || null;

  if (!email || !name || !handle) {
    return Response.json({ error: 'Email, name, and handle are required.' }, { status: 400 });
  }
  if (!/^[^\s@]+@[^\s@]+\.[^\s@]+$/.test(email)) {
    return Response.json({ error: 'Please enter a valid email address.' }, { status: 400 });
  }
  if (!/^[a-z0-9_-]{2,20}$/.test(handle)) {
    return Response.json({ error: 'Handle must be 2–20 lowercase letters, numbers, hyphens, or underscores.' }, { status: 400 });
  }

  const wranglerCmd = `wrangler kv key put --binding HANDLES --remote "${email}" '{"handle":"${handle}","name":"${name}","url":${siteUrl ? `"${siteUrl}"` : 'null'},"bio":${bio ? `"${bio}"` : 'null'}}'`;

  const lines = [
    `**Join request from ${name}**`,
    '',
    `| Field | Value |`,
    `|-------|-------|`,
    `| Email | ${email} |`,
    `| Handle | \`${handle}\` |`,
    siteUrl ? `| Website | ${siteUrl} |` : null,
    bio     ? `| Bio | ${bio} |` : null,
    '',
    '**To approve**, add to HANDLES KV:',
    '```',
    wranglerCmd,
    '```',
    'Or use the [admin panel](https://worldmachines.org/admin/handles).',
    '',
    'Also ensure their email is allowed through Cloudflare Access (Zero Trust → Access → Applications → worldmachines).',
  ].filter(l => l !== null).join('\n');

  const res = await fetch(
    `https://api.github.com/repos/${env.GITHUB_REPO}/issues`,
    {
      method: 'POST',
      headers: {
        Authorization: `Bearer ${env.GITHUB_TOKEN}`,
        Accept: 'application/vnd.github+json',
        'Content-Type': 'application/json',
        'X-GitHub-Api-Version': '2022-11-28',
        'User-Agent': 'worldmachines-worker',
      },
      body: JSON.stringify({
        title: `Join request: ${name} (@${handle}) — ${email}`,
        body: lines,
      }),
    }
  );

  if (!res.ok) {
    const text = await res.text();
    console.error('GitHub issue creation failed:', res.status, text);
    return Response.json({ error: 'Failed to submit request. Please try again.' }, { status: 502 });
  }

  const issue = await res.json();
  return Response.json({ ok: true, issue_url: issue.html_url });
}
