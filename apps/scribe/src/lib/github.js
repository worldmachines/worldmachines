// github.js — the write layer, and the dry-run plan that stands in for it.
//
// Scribe writes ONE markdown file per commit, so this uses the Contents API
// (PUT /repos/{owner}/{repo}/contents/{path}) rather than the six-call Git Data
// dance an atomic multi-file commit needs. One note, one commit, one clean diff —
// and a raw-notes-only commit prefixed `[trivial]` is pre-authorised to land on
// main (CLAUDE.md: raw-notes PRs need no review; `[trivial]` skips the devlog).
//
// DRY-RUN IS THE DEFAULT, in two independent ways:
//   1. No GITHUB_TOKEN configured ⇒ every write is a plan. This is the state the
//      app ships in; the button that would commit for real is disabled until the
//      Worker reports commitsEnabled.
//   2. An explicit dryRun:true from the client ⇒ a plan even WITH a token, so
//      "Preview" can never write. The check happens before any fetch(), so a
//      preview makes no network call at all.
//
// Two invariants are asserted before a request is built, not after:
//   • every path is inside raw-notes/   (assertSafePath, lib/notes.js)
//   • every commit message starts with `[trivial]`
// A violation throws rather than committing — the failure mode of a note-capture
// app writing to website/ is much worse than a 500.

import { assertSafePath } from "./notes.js";

const GH = "https://api.github.com";
const UA = "wm-scribe/0.1";

export const DRYRUN_NO_TOKEN =
  "GITHUB_TOKEN not configured — dry-run only. No network call was made and nothing was written.";
export const DRYRUN_REQUESTED =
  "Preview requested — plan only, nothing committed. No network call was made.";

function headers(token) {
  return {
    Authorization: `Bearer ${token}`,
    Accept: "application/vnd.github+json",
    "User-Agent": UA,
    "X-GitHub-Api-Version": "2022-11-28",
    "content-type": "application/json",
  };
}

async function ghJson(r) {
  if (!r.ok) throw new Error(`GitHub ${r.status}: ${(await r.text()).slice(0, 400)}`);
  return r.json();
}

/** Encode a repo path for a Contents API URL while keeping "/" separators. */
function encodePath(p) {
  return String(p || "")
    .split("/")
    .map(encodeURIComponent)
    .join("/");
}

/** UTF-8 text → base64 (what the Contents API wants for `content`). */
export function toBase64(text) {
  const bytes = new TextEncoder().encode(String(text));
  let bin = "";
  for (let i = 0; i < bytes.length; i += 0x8000) {
    bin += String.fromCharCode.apply(null, bytes.subarray(i, i + 0x8000));
  }
  return btoa(bin);
}

/** base64 (possibly newline-wrapped, as GitHub returns) → UTF-8 text. */
export function fromBase64(b64) {
  const bin = atob(String(b64 || "").replace(/\s+/g, ""));
  const bytes = new Uint8Array(bin.length);
  for (let i = 0; i < bin.length; i++) bytes[i] = bin.charCodeAt(i);
  return new TextDecoder("utf-8").decode(bytes);
}

export function byteLength(text) {
  return new TextEncoder().encode(String(text)).length;
}

/** The two hard guards, applied to every write path. Throws on violation. */
function assertWritable(path, message) {
  assertSafePath(path);
  if (!String(message || "").startsWith("[trivial]")) {
    throw new Error(`commit message must start with [trivial]: ${message}`);
  }
}

/**
 * writeNote — create or update ONE note.
 *
 * opts = { repo, branch, token, path, content, message, sha?, author?, dryRun? }
 *   sha    — the blob sha of the file being REPLACED. Required by GitHub for an
 *            update; omitting it on an existing path is a 422, which is the
 *            behaviour we want (never silently clobber someone else's note).
 *   author — { name, email } so git blame shows the member, not the app.
 *
 * Returns { committed, dryRun, reason?, plan, commit? }.
 */
export async function writeNote(opts) {
  const { repo, branch = "main", token, path, content, message, sha, author } = opts;
  assertWritable(path, message);

  const b64 = toBase64(content);
  const plan = {
    method: "PUT",
    api: `${GH}/repos/${repo || "<owner>/<repo>"}/contents/${encodePath(path)}`,
    repo: repo || "(GITHUB_REPO not set)",
    branch,
    path,
    message,
    mode: sha ? "update" : "create",
    sha: sha || null,
    bytes: byteLength(content),
    base64Bytes: b64.length,
    author: author || null,
    body: { message, branch, content: `<base64, ${b64.length} chars>`, ...(sha ? { sha } : {}) },
  };

  // Explicit preview short-circuits BEFORE any network call, even with a token.
  if (opts.dryRun === true || !token || !repo) {
    return {
      committed: false,
      dryRun: true,
      reason: opts.dryRun === true && token && repo ? DRYRUN_REQUESTED : DRYRUN_NO_TOKEN,
      plan,
    };
  }

  const body = { message, branch, content: b64 };
  if (sha) body.sha = sha;
  if (author && author.name && author.email) body.author = { name: author.name, email: author.email };

  const data = await ghJson(
    await fetch(`${GH}/repos/${repo}/contents/${encodePath(path)}`, {
      method: "PUT",
      headers: headers(token),
      body: JSON.stringify(body),
    })
  );

  return {
    committed: true,
    dryRun: false,
    plan,
    commit: {
      sha: data.commit && data.commit.sha,
      url: data.commit && data.commit.html_url,
      contentUrl: data.content && data.content.html_url,
      blobSha: data.content && data.content.sha,
    },
  };
}

/**
 * readNote — GET one file's text plus the blob `sha` the editor must send back.
 * Works unauthenticated on a public repo; with no token AND no repo it reports a
 * dry-run miss rather than throwing, so the UI degrades instead of erroring.
 */
export async function readNote({ repo, branch = "main", token, path }) {
  assertSafePath(path);
  if (!repo) return { ok: false, dryRun: true, reason: DRYRUN_NO_TOKEN, path, sha: null, content: "" };

  const h = token ? headers(token) : { Accept: "application/vnd.github+json", "User-Agent": UA };
  const data = await ghJson(
    await fetch(`${GH}/repos/${repo}/contents/${encodePath(path)}?ref=${encodeURIComponent(branch)}`, { headers: h })
  );
  const content = data.encoding === "base64" ? fromBase64(data.content) : String(data.content || "");
  return { ok: true, path: data.path || path, sha: data.sha, size: data.size, content };
}

/**
 * listNotes — every markdown file under raw-notes/, from ONE call to the Git Trees
 * API (recursive), rather than a walk of the Contents API per directory.
 *
 * Cached module-side for CACHE_MS: the tree of ~1000 notes changes on the order of
 * times per day, and the link picker asks for it on every capture.
 */
const CACHE_MS = 5 * 60 * 1000;
let _tree = { key: null, at: 0, files: null };

export async function listNotes({ repo, branch = "main", token, force = false }) {
  if (!repo) return { ok: false, dryRun: true, reason: DRYRUN_NO_TOKEN, files: [] };
  const key = `${repo}@${branch}`;
  if (!force && _tree.files && _tree.key === key && Date.now() - _tree.at < CACHE_MS) {
    return { ok: true, cached: true, files: _tree.files };
  }

  const h = token ? headers(token) : { Accept: "application/vnd.github+json", "User-Agent": UA };
  const data = await ghJson(
    await fetch(`${GH}/repos/${repo}/git/trees/${encodeURIComponent(branch)}?recursive=1`, { headers: h })
  );
  const files = (data.tree || [])
    .filter((n) => n.type === "blob" && n.path.startsWith("raw-notes/") && n.path.endsWith(".md"))
    .map((n) => ({ path: n.path, sha: n.sha, size: n.size }));

  _tree = { key, at: Date.now(), files };
  return { ok: true, cached: false, truncated: Boolean(data.truncated), files };
}
