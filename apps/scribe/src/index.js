// index.js — the Scribe Worker.
//
// Serves the installable PWA from ./public and a small JSON API under /api/*.
// wrangler.jsonc sets assets.run_worker_first, so this handler sees every request
// and hands non-/api paths back to the assets binding.
//
// Shape of the thing:
//
//   identity → note builder → dry-run plan → (only with a token) one commit
//
// Every route below /api/config requires a resolved member identity: an Access
// email that maps to a HANDLES record. No identity, no note — the app fails closed
// rather than guessing whose directory a note belongs in.
//
// Nothing here can write anywhere except raw-notes/, and nothing can write at all
// until GITHUB_TOKEN is set. Until then every write route answers with the exact
// file, path, and commit it WOULD produce.

import { resolveIdentity, authMode, MEMBER_DIRS } from "./lib/identity.js";
import {
  buildNote,
  updateNote,
  parseNote,
  editCommitMessage,
  extractWikiLinks,
  assertSafePath,
  isCanonPath,
  NOTE_TYPES,
  GLOSSARY_DIR,
  GLOSSARY_STATUSES,
  CANON_DIRS,
} from "./lib/notes.js";
import { writeNote, readNote } from "./lib/github.js";
import { corpus, searchNotes, danglingLinks } from "./lib/corpus.js";

const json = (data, status = 200) =>
  new Response(JSON.stringify(data, null, 2), {
    status,
    headers: {
      "content-type": "application/json; charset=utf-8",
      // Private, per-member, and mode-dependent: never cache any of it.
      "cache-control": "no-store, no-cache, must-revalidate",
    },
  });

export default {
  async fetch(request, env) {
    const url = new URL(request.url);
    const { pathname } = url;

    if (!pathname.startsWith("/api/")) {
      return env.ASSETS ? env.ASSETS.fetch(request) : new Response("Not found", { status: 404 });
    }

    const repo = env.GITHUB_REPO || "";
    const branch = env.GITHUB_BRANCH || "main";
    const commitsEnabled = Boolean(env.GITHUB_TOKEN && repo);

    try {
      /* ------------------------------- /api/config -------------------------------
         The only unauthenticated route. It reveals booleans about configuration —
         never data — because the PWA needs to know what UI to render (dry-run badge,
         disabled commit button) before it knows whether the caller has a handle. */
      if (pathname === "/api/config") {
        return json({
          ok: true,
          app: "scribe",
          commitsEnabled,
          repo: repo || "(GITHUB_REPO not set)",
          branch,
          auth: authMode(env),
          noteTypes: NOTE_TYPES,
          glossaryStatuses: GLOSSARY_STATUSES,
          glossaryDir: GLOSSARY_DIR,
          memberDirs: MEMBER_DIRS,
          canonDirs: CANON_DIRS,
          notice: commitsEnabled
            ? "Commits ENABLED — 'Save to repo' writes one [trivial] commit to raw-notes/."
            : "Dry-run mode: every save shows the exact file, path and commit it would make. Set GITHUB_TOKEN to enable real commits.",
        });
      }

      /* ------------------------------- identity gate ------------------------------
         Everything below needs a member. 401 = no Access identity at all;
         403 = an identity with no HANDLES record (a curator has to add one). */
      const who = await resolveIdentity(request, env);
      if (!who.ok) return json({ ok: false, error: who.error }, who.status);
      const me = who.identity;

      // ---- /api/me : who the Worker thinks you are, and where it would write ----
      if (pathname === "/api/me" && request.method === "GET") {
        return json({
          ok: true,
          ...me,
          notesDir: `raw-notes/${me.dir}/`,
          glossaryDir: `${GLOSSARY_DIR}/`,
          warning: me.dirKnown ? undefined : `raw-notes/${me.dir}/ does not exist yet — the first note will create it.`,
        });
      }

      // ---- /api/corpus : books, tags, and the freshness of the note index ----
      if (pathname === "/api/corpus" && request.method === "GET") {
        const c = await corpus(env);
        return json({
          ok: true,
          live: c.live,
          generated: c.generated,
          counts: { notes: c.notes.length, sources: c.sources.length, tags: c.tags.length },
          sources: c.sources,
          tags: c.tags.slice(0, 400), // the type-ahead only ever shows a handful
        });
      }

      // ---- /api/notes : the picker/browse index ----
      // scope=mine  → the caller's own directory (edit flow)
      // scope=commons → the shared tree
      // scope=all (default) → everything, for the wiki-link picker
      // prefix=… → a path prefix, e.g. raw-notes/commons/reading/<source-id>/ so a
      //            book note can link the section it is reacting to
      if (pathname === "/api/notes" && request.method === "GET") {
        const c = await corpus(env);
        const scope = url.searchParams.get("scope") || "all";
        const dir = scope === "mine" ? me.dir : scope === "commons" ? "commons" : null;
        const limit = Math.min(Number(url.searchParams.get("limit")) || 40, 200);
        const prefix = url.searchParams.get("prefix") || "";
        const pool = prefix ? c.notes.filter((n) => n.path.startsWith(prefix)) : c.notes;
        const notes = searchNotes(pool, url.searchParams.get("q") || "", { dir, limit }).map((n) =>
          isCanonPath(n.path) ? { ...n, canon: true } : n
        );
        return json({ ok: true, scope, prefix, live: c.live, total: pool.length, count: notes.length, notes });
      }

      // ---- /api/note : read one note for editing (content + sha) ----
      if (pathname === "/api/note" && request.method === "GET") {
        const path = url.searchParams.get("path") || "";
        try {
          assertSafePath(path);
        } catch (err) {
          return json({ ok: false, error: err.message }, 400);
        }
        if (!repo) {
          return json(
            { ok: false, error: "GITHUB_REPO is not set, so notes cannot be read back. Editing needs it; capture does not." },
            503
          );
        }
        const file = await readNote({ repo, branch, token: env.GITHUB_TOKEN, path });
        if (!file.ok) return json({ ok: false, error: file.reason || "not found" }, 404);
        const parsed = parseNote(file.content);
        return json({
          ok: true,
          path: file.path,
          sha: file.sha,
          mine: file.path.startsWith(`raw-notes/${me.dir}/`),
          canon: isCanonPath(file.path),
          content: file.content,
          ...parsed,
        });
      }

      /* --------------------------------- /api/compose ---------------------------
         Build a new note of any type. dryRun:true (the Preview button) always
         returns a plan; dryRun:false commits only when a token is configured. */
      if (pathname === "/api/compose" && request.method === "POST") {
        const payload = await request.json().catch(() => ({}));
        const dryRun = payload.dryRun !== false;

        let note;
        try {
          note = buildNote(payload, me);
        } catch (err) {
          return json({ ok: false, error: err.message }, 400);
        }

        // Dangling wiki-links are invisible to both repo validators, so they are
        // caught here: reported always, and BLOCKING for a real commit unless the
        // caller deliberately overrides (a link to a note being written next).
        const dangling = await danglingLinks(env, note.meta.wikiLinks || []);
        if (dangling.length && !dryRun && payload.allowDangling !== true) {
          return json(
            {
              ok: false,
              error: `these [[links]] point at notes that do not exist: ${dangling.join(", ")}`,
              dangling,
              path: note.path,
              markdown: note.markdown,
            },
            409
          );
        }

        const result = await writeNote({
          repo,
          branch,
          token: env.GITHUB_TOKEN,
          path: note.path,
          content: note.markdown,
          message: note.commitMessage,
          author: { name: me.name, email: me.email },
          dryRun,
        });

        return json({
          ok: true,
          action: "create",
          type: note.meta.type,
          path: note.path,
          markdown: note.markdown,
          commitMessage: note.commitMessage,
          meta: note.meta,
          dangling,
          commit: result,
        });
      }

      /* ---------------------------------- /api/save -----------------------------
         Edit an existing note. The client sends the path + the sha it read, so a
         concurrent edit by someone else fails loudly (422 from GitHub) instead of
         being overwritten. Only body/summary/tags change; every other frontmatter
         key the ingestion pipeline wrote is preserved byte-for-byte. */
      if (pathname === "/api/save" && request.method === "POST") {
        const payload = await request.json().catch(() => ({}));
        const dryRun = payload.dryRun !== false;
        const path = String(payload.path || "");
        try {
          assertSafePath(path);
        } catch (err) {
          return json({ ok: false, error: err.message }, 400);
        }

        // Members own their own directory; commons is shared by everyone. Anything
        // else is someone else's dir and is refused (raw-notes/README.md: "each
        // person writes and pushes inside their own directory").
        const mine = path.startsWith(`raw-notes/${me.dir}/`);
        const shared = path.startsWith("raw-notes/commons/");
        if (!mine && !shared) {
          return json({ ok: false, error: `${path} is not yours to edit — you own raw-notes/${me.dir}/ and share raw-notes/commons/.` }, 403);
        }

        // The canon layer is review-gated even inside your own directory. Previewing
        // is fine and useful — it produces the exact file to take to a PR — but a
        // direct commit would walk past the gate, so it is refused.
        const canon = isCanonPath(path);
        if (canon && !dryRun) {
          return json(
            {
              ok: false,
              canon: true,
              error: `${path} is a canon page (${CANON_DIRS.join("/")}), which lands by PR review, not by direct commit. Preview it here, then open a PR with the result.`,
            },
            409
          );
        }

        const original = typeof payload.original === "string" ? payload.original : null;
        let sha = payload.sha || null;
        let base = original;
        if (base === null) {
          if (!repo) return json({ ok: false, error: "GITHUB_REPO is not set, so the current note cannot be read back." }, 503);
          const file = await readNote({ repo, branch, token: env.GITHUB_TOKEN, path });
          if (!file.ok) return json({ ok: false, error: file.reason || "not found" }, 404);
          base = file.content;
          sha = sha || file.sha;
        }

        const updated = updateNote(base, {
          body: typeof payload.body === "string" ? payload.body : undefined,
          summary: typeof payload.summary === "string" ? payload.summary : undefined,
          tags: payload.tags,
          touchDate: payload.touchDate !== false,
        });

        const dangling = await danglingLinks(env, updated.wikiLinks);
        if (dangling.length && !dryRun && payload.allowDangling !== true) {
          return json(
            { ok: false, error: `these [[links]] point at notes that do not exist: ${dangling.join(", ")}`, dangling, path, markdown: updated.markdown },
            409
          );
        }

        const message = String(payload.message || editCommitMessage(path, me));
        const result = await writeNote({
          repo,
          branch,
          token: env.GITHUB_TOKEN,
          path,
          content: updated.markdown,
          message,
          sha,
          author: { name: me.name, email: me.email },
          dryRun,
        });

        return json({
          ok: true,
          action: "edit",
          path,
          markdown: updated.markdown,
          changed: updated.changed,
          commitMessage: message,
          wikiLinks: updated.wikiLinks,
          dangling,
          commit: result,
        });
      }

      // ---- /api/links/check : validate [[links]] in a draft, without saving ----
      if (pathname === "/api/links/check" && request.method === "POST") {
        const { text } = await request.json().catch(() => ({}));
        const links = extractWikiLinks(text);
        return json({ ok: true, links, dangling: await danglingLinks(env, links) });
      }

      return json({ ok: false, error: `no route for ${request.method} ${pathname}` }, 404);
    } catch (err) {
      // Guard violations (path outside raw-notes/, missing [trivial] prefix) land
      // here too — they are 400s, not 500s: the caller asked for something refused.
      const msg = String((err && err.message) || err);
      const refused = /refusing to write|unsafe path|must start with \[trivial\]|\.md files/.test(msg);
      return json({ ok: false, error: msg }, refused ? 400 : 500);
    }
  },
};
