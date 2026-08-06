// app.js — Scribe front-end. Same-origin calls to /api/* on this Worker.
//
// There is no login here: the host is behind Cloudflare Access, so the browser
// carries the Access session automatically and the Worker decides who you are.
// The app's first act is to ask /api/me; if that fails it shows the gate with the
// Worker's own explanation rather than inventing one.
//
// Every write is a two-step: Preview (always a dry-run, always shows the exact file
// and commit) and then Save. "Save to repo" stays disabled until the Worker reports
// commitsEnabled, so the prototype physically cannot commit.

const $ = (s, r = document) => r.querySelector(s);
const $$ = (s, r = document) => [...r.querySelectorAll(s)];

const DRAFT_KEY = "scribe.draft.v1";

const state = {
  type: "observation",
  config: null,
  me: null,
  tags: [],
  sources: [],
  reading: [],   // chips: reading-note ids for a book note
  connects: [],  // chips: note ids for a link note
  editing: null, // { path, sha, original }
  notesScope: "mine",
  bodySel: null, // remembered cursor position in the body textarea
};

const api = async (path, opts = {}) => {
  const headers = { "content-type": "application/json", ...(opts.headers || {}) };
  try {
    const r = await fetch(path, { ...opts, headers });
    const data = await r.json().catch(() => ({}));
    return { status: r.status, data };
  } catch (err) {
    return { status: 0, data: { ok: false, error: `offline or unreachable (${err.message})` } };
  }
};

/* ================================== BOOT ================================== */

boot();

async function boot() {
  const [{ data: config }, { status, data: me }] = await Promise.all([api("/api/config"), api("/api/me")]);
  state.config = config;

  if (status !== 200 || !me.ok) {
    const gate = $("#gate");
    const msg = $("#gate-msg");
    msg.textContent =
      status === 403
        ? me.error || "Your email is not in the contributor registry yet."
        : me.error || "Could not establish who you are.";
    msg.classList.add("is-error");
    gate.hidden = false;
    return;
  }

  state.me = me;
  $("#app").hidden = false;
  $("#who").textContent = `${me.handle} · raw-notes/${me.dir}/`;

  const badge = $("#mode-badge");
  if (config.commitsEnabled) {
    badge.textContent = "live";
    badge.className = "badge badge-ok";
  } else {
    badge.textContent = "dry-run";
    badge.className = "badge badge-warn";
    const n = $("#notice");
    n.textContent = config.notice;
    n.hidden = false;
  }
  for (const b of [$("#c-save"), $("#e-save")]) {
    b.disabled = !config.commitsEnabled;
    b.textContent = config.commitsEnabled ? "Save to repo" : "Save to repo 🔒";
    b.title = config.commitsEnabled ? "Write this note as one [trivial] commit" : "GITHUB_TOKEN is not set — preview only";
  }
  if (me.warning) {
    const n = $("#notice");
    n.textContent = `${n.textContent} · ${me.warning}`.trim();
    n.hidden = false;
  }

  setType("observation");
  restoreDraft();
  renderMe();
  loadCorpus();
  registerServiceWorker();
  window.addEventListener("online", updateOffline);
  window.addEventListener("offline", updateOffline);
  updateOffline();
}

function updateOffline() {
  $("#offline").hidden = navigator.onLine;
}

function registerServiceWorker() {
  if (!("serviceWorker" in navigator)) return;
  navigator.serviceWorker.register("/sw.js").catch(() => {});
}

async function loadCorpus() {
  const { data } = await api("/api/corpus");
  if (!data.ok) return;
  state.tags = data.tags || [];
  state.sources = data.sources || [];
  const sel = $("#c-source");
  for (const s of state.sources) {
    const o = document.createElement("option");
    o.value = s.id;
    o.textContent = `${s.title} (${s.notes})`;
    sel.append(o);
  }
  renderConfigCard(data);
}

/* ================================== NAV =================================== */

$$(".tab").forEach((t) =>
  t.addEventListener("click", () => {
    const go = t.dataset.go;
    $$(".tab").forEach((x) => x.classList.toggle("is-active", x === t));
    show(go);
    if (go === "notes") loadNotes();
  })
);

function show(view) {
  $$(".view").forEach((v) => (v.hidden = v.dataset.view !== view));
}

/* ================================ CAPTURE ================================= */

const TYPE_UI = {
  observation: {
    hint: "A thought, a question, a fragment. Lands in your directory with today's date in the filename.",
    fields: [],
    title: "Title",
    body: "Note (Markdown)",
  },
  book: {
    hint: "Your own reaction to a shared reading. The book's reading notes stay in commons/; this links to them from your directory.",
    fields: ["f-source", "f-reading"],
    title: "Title",
    body: "What you make of it (Markdown)",
  },
  glossary: {
    hint: "A shared definition. Goes to raw-notes/commons/glossary/ — communal, with you recorded as a contributor.",
    fields: ["f-term", "f-aliases", "f-status"],
    title: null, // the term IS the title
    body: "Definition (Markdown)",
  },
  link: {
    hint: "A note whose job is to connect other notes. Pick the notes it ties together; they become [[wiki-links]].",
    fields: ["f-connects"],
    title: "Title",
    body: "Why these belong together (Markdown)",
  },
};

$$(".seg").forEach((b) => b.addEventListener("click", () => setType(b.dataset.type)));

function setType(type) {
  state.type = type;
  $$(".seg").forEach((b) => b.classList.toggle("is-active", b.dataset.type === type));
  const ui = TYPE_UI[type];
  $("#type-hint").textContent = ui.hint;

  const optional = ["f-source", "f-reading", "f-term", "f-aliases", "f-status", "f-connects"];
  for (const id of optional) $(`#${id}`).hidden = !ui.fields.includes(id);
  $("#f-title").hidden = ui.title === null;
  if (ui.title) $("#l-title").textContent = ui.title;
  $("#l-body").innerHTML = ui.body.replace(/\((.*)\)/, '<em class="muted">($1)</em>');

  $("#capture-out").hidden = true;
  updateSlugPreview();
  saveDraft();
}

/* ---- slug preview -------------------------------------------------------
   A copy of the Worker's slugify so the filename is visible while typing. The
   Worker remains authoritative: the path shown after Preview is the real one. */
function slugify(input) {
  return String(input || "")
    .toLowerCase()
    .normalize("NFKD")
    .replace(/[̀-ͯ]/g, "")
    .replace(/['’"]/g, "")
    .replace(/[^a-z0-9]+/g, "-")
    .replace(/^-+|-+$/g, "")
    .slice(0, 80)
    .replace(/-+$/, "");
}

function updateSlugPreview() {
  const el = $("#slug-preview");
  const me = state.me;
  if (!me) return (el.hidden = true);
  const name = state.type === "glossary" ? $("#c-term").value : $("#c-title").value;
  const stem = slugify(name);
  if (!stem) return (el.hidden = true);
  const today = new Date().toISOString().slice(0, 10);
  const path =
    state.type === "glossary"
      ? `raw-notes/commons/glossary/${stem}.md`
      : state.type === "observation"
        ? `raw-notes/${me.dir}/${today}-${stem}.md`
        : `raw-notes/${me.dir}/${stem}.md`;
  el.textContent = `→ ${path}`;
  el.hidden = false;
}

for (const id of ["#c-title", "#c-term"]) $(id).addEventListener("input", updateSlugPreview);

/* ---- draft persistence (the whole point of a capture app is not losing it) ---- */
const DRAFT_FIELDS = ["c-title", "c-term", "c-aliases", "c-status", "c-source", "c-body", "c-summary", "c-tags"];

function saveDraft() {
  const d = { type: state.type, reading: state.reading, connects: state.connects };
  for (const id of DRAFT_FIELDS) d[id] = $(`#${id}`).value;
  try {
    localStorage.setItem(DRAFT_KEY, JSON.stringify(d));
  } catch {}
}

function restoreDraft() {
  let d;
  try {
    d = JSON.parse(localStorage.getItem(DRAFT_KEY) || "null");
  } catch {
    d = null;
  }
  if (!d) return;
  for (const id of DRAFT_FIELDS) if (typeof d[id] === "string") $(`#${id}`).value = d[id];
  state.reading = Array.isArray(d.reading) ? d.reading : [];
  state.connects = Array.isArray(d.connects) ? d.connects : [];
  renderChips();
  if (d.type) setType(d.type);
  updateSlugPreview();
}

function clearDraft() {
  try {
    localStorage.removeItem(DRAFT_KEY);
  } catch {}
}

$("#capture-form").addEventListener("input", saveDraft);

$("#c-clear").addEventListener("click", () => {
  for (const id of DRAFT_FIELDS) $(`#${id}`).value = "";
  state.reading = [];
  state.connects = [];
  renderChips();
  clearDraft();
  $("#capture-out").hidden = true;
  setStatus("#capture-status", "");
  updateSlugPreview();
});

/* ---- chips (reading notes, connected notes) ---- */
function renderChips() {
  renderChipList("#c-reading-chips", state.reading, (id) => {
    state.reading = state.reading.filter((x) => x !== id);
    renderChips();
    saveDraft();
  });
  renderChipList("#c-connect-chips", state.connects, (id) => {
    state.connects = state.connects.filter((x) => x !== id);
    renderChips();
    saveDraft();
  });
}

function renderChipList(sel, ids, onRemove) {
  const ul = $(sel);
  ul.textContent = "";
  for (const id of ids) {
    const li = document.createElement("li");
    li.textContent = id;
    const b = document.createElement("button");
    b.type = "button";
    b.textContent = "×";
    b.setAttribute("aria-label", `Remove ${id}`);
    b.addEventListener("click", () => onRemove(id));
    li.append(b);
    ul.append(li);
  }
}

/* ================================ PICKERS ================================= */
/**
 * A type-ahead over a remote or local list. `fetcher(q)` returns
 * [{ value, label, sub }]; picking one calls `onPick(value)`.
 */
function makePicker(inputSel, listSel, fetcher, onPick, { clearOnPick = true } = {}) {
  const input = $(inputSel);
  const list = $(listSel);
  let items = [];
  let hl = -1;
  let seq = 0;

  const close = () => {
    list.hidden = true;
    list.textContent = "";
    input.setAttribute("aria-expanded", "false");
    hl = -1;
  };

  const render = () => {
    list.textContent = "";
    if (!items.length) {
      const li = document.createElement("li");
      li.className = "empty";
      li.textContent = "no matches";
      list.append(li);
    }
    items.forEach((it, i) => {
      const li = document.createElement("li");
      li.setAttribute("role", "option");
      li.textContent = it.label;
      if (it.sub) {
        const s = document.createElement("small");
        s.textContent = it.sub;
        li.append(s);
      }
      if (i === hl) li.classList.add("is-hl");
      li.addEventListener("mousedown", (e) => {
        e.preventDefault();
        pick(it);
      });
      list.append(li);
    });
    list.hidden = false;
    input.setAttribute("aria-expanded", "true");
  };

  const pick = (it) => {
    onPick(it.value, it);
    if (clearOnPick) input.value = "";
    close();
  };

  const run = async () => {
    const mine = ++seq;
    const results = await fetcher(input.value.trim());
    if (mine !== seq) return; // a newer keystroke already won
    items = results.slice(0, 12);
    hl = -1;
    render();
  };

  let timer = null;
  input.addEventListener("input", () => {
    clearTimeout(timer);
    timer = setTimeout(run, 160);
  });
  input.addEventListener("focus", run);
  input.addEventListener("blur", () => setTimeout(close, 120));
  input.addEventListener("keydown", (e) => {
    if (list.hidden) return;
    if (e.key === "ArrowDown" || e.key === "ArrowUp") {
      e.preventDefault();
      hl = Math.max(0, Math.min(items.length - 1, hl + (e.key === "ArrowDown" ? 1 : -1)));
      render();
    } else if (e.key === "Enter" && hl >= 0) {
      e.preventDefault();
      pick(items[hl]);
    } else if (e.key === "Escape") {
      close();
    }
  });

  return { close };
}

const noteFetcher = (paramsFn) => async (q) => {
  const params = new URLSearchParams({ q, limit: "12", ...paramsFn() });
  const { data } = await api(`/api/notes?${params}`);
  return (data.notes || []).map((n) => ({ value: n.id, label: n.title || n.id, sub: n.path }));
};

// Book note → the reading notes of the CHOSEN book only.
makePicker(
  "#c-reading-q",
  "#c-reading-list",
  async (q) => {
    const src = $("#c-source").value;
    if (!src) return [{ value: "", label: "pick a book first", sub: "" }];
    return noteFetcher(() => ({ prefix: `raw-notes/commons/reading/${src}/` }))(q);
  },
  (id) => {
    if (id && !state.reading.includes(id)) state.reading.push(id);
    renderChips();
    saveDraft();
  }
);

// Link note → any note in the corpus.
makePicker("#c-connect-q", "#c-connect-list", noteFetcher(() => ({})), (id) => {
  if (!state.connects.includes(id)) state.connects.push(id);
  renderChips();
  saveDraft();
});

// Inline [[link]] insertion into the body at the cursor.
const bodyEl = $("#c-body");
bodyEl.addEventListener("blur", () => {
  state.bodySel = [bodyEl.selectionStart, bodyEl.selectionEnd];
});
$("#c-insert-link").addEventListener("click", () => {
  const box = $("#f-inline-link");
  box.hidden = !box.hidden;
  if (!box.hidden) $("#c-inline-q").focus();
});
makePicker("#c-inline-q", "#c-inline-list", noteFetcher(() => ({})), (id) => {
  const [s, e] = state.bodySel || [bodyEl.value.length, bodyEl.value.length];
  bodyEl.value = `${bodyEl.value.slice(0, s)}[[${id}]]${bodyEl.value.slice(e)}`;
  state.bodySel = [s + id.length + 4, s + id.length + 4];
  $("#f-inline-link").hidden = true;
  $("#link-status").textContent = `inserted [[${id}]]`;
  setTimeout(() => ($("#link-status").textContent = ""), 2500);
  saveDraft();
});

// Tags: type-ahead over the vocabulary already in use, on the LAST comma-separated
// fragment. Still a plain text field, so a genuinely new tag is just typed.
makePicker(
  "#c-tags",
  "#c-tag-list",
  async () => {
    const frag = lastTagFragment($("#c-tags").value).toLowerCase();
    if (!frag) return [];
    return state.tags
      .filter((t) => t.toLowerCase().includes(frag))
      .slice(0, 12)
      .map((t) => ({ value: t, label: t }));
  },
  (tag) => {
    const input = $("#c-tags");
    const parts = input.value.split(",");
    parts[parts.length - 1] = ` ${tag}`;
    input.value = parts.join(",").replace(/^\s+/, "") + ", ";
    input.focus();
    saveDraft();
  },
  { clearOnPick: false }
);

function lastTagFragment(v) {
  return String(v).split(",").pop().trim();
}

/* --------------------------- capture: preview / save --------------------------- */

function capturePayload(dryRun) {
  const p = {
    type: state.type,
    dryRun,
    title: $("#c-title").value,
    body: $("#c-body").value,
    summary: $("#c-summary").value,
    tags: $("#c-tags").value,
  };
  if (state.type === "book") {
    p.sourceId = $("#c-source").value;
    p.readingNotes = state.reading;
  }
  if (state.type === "glossary") {
    p.term = $("#c-term").value;
    p.aliases = $("#c-aliases").value;
    p.status = $("#c-status").value;
  }
  if (state.type === "link") p.connects = state.connects;
  return p;
}

$("#capture-form").addEventListener("submit", (e) => {
  e.preventDefault();
  submitCapture(true);
});
$("#c-save").addEventListener("click", () => submitCapture(false));

async function submitCapture(dryRun) {
  setStatus("#capture-status", dryRun ? "Building the file…" : "Committing…");
  const { status, data } = await api("/api/compose", { method: "POST", body: JSON.stringify(capturePayload(dryRun)) });

  if (!data.ok) {
    setStatus("#capture-status", data.error || `failed (${status})`, "error");
    if (data.markdown) renderOut(data, "#capture-out", "#out-badge", "#out-path", "#out-md", "#out-msg", "#out-plan", "#out-dangling");
    return;
  }

  renderOut(data, "#capture-out", "#out-badge", "#out-path", "#out-md", "#out-msg", "#out-plan", "#out-dangling");

  if (data.commit && data.commit.committed) {
    setStatus("#capture-status", `Committed ${data.commit.commit.sha.slice(0, 7)} — ${data.path}`, "ok");
    clearDraft();
    $("#c-clear").click();
  } else {
    setStatus("#capture-status", "Dry run — nothing was written. Read the file above, then save.", "ok");
    $("#c-save").classList.add("btn-emphasis");
  }
}

function renderOut(data, outSel, badgeSel, pathSel, mdSel, msgSel, planSel, dangSel) {
  const committed = Boolean(data.commit && data.commit.committed);
  const badge = $(badgeSel);
  badge.textContent = committed ? "written" : "would write";
  badge.className = committed ? "badge badge-ok" : "badge badge-warn";
  $(pathSel).textContent = data.path || "";
  $(mdSel).textContent = data.markdown || "";
  if (msgSel) $(msgSel).textContent = data.commitMessage || "";
  if (planSel) {
    const plan = data.commit && data.commit.plan;
    $(planSel).textContent = plan
      ? `${plan.method} ${plan.mode} · ${plan.bytes} bytes · ${plan.repo}@${plan.branch}`
      : "";
  }
  const dang = $(dangSel);
  if (data.dangling && data.dangling.length) {
    dang.textContent = `These [[links]] point at notes that do not exist: ${data.dangling.join(", ")}. Saving is blocked until they resolve — wiki-links are case-sensitive.`;
    dang.hidden = false;
  } else {
    dang.hidden = true;
  }
  $(outSel).hidden = false;
  $(outSel).scrollIntoView({ behavior: "smooth", block: "nearest" });
}

function setStatus(sel, msg, kind) {
  const el = $(sel);
  el.textContent = msg;
  el.className = `status${kind ? ` is-${kind}` : ""}`;
  el.hidden = !msg;
}

/* ================================= NOTES ================================== */

$$(".nseg").forEach((b) =>
  b.addEventListener("click", () => {
    state.notesScope = b.dataset.scope;
    $$(".nseg").forEach((x) => x.classList.toggle("is-active", x === b));
    loadNotes();
  })
);

let notesTimer = null;
$("#n-search").addEventListener("input", () => {
  clearTimeout(notesTimer);
  notesTimer = setTimeout(loadNotes, 200);
});

async function loadNotes() {
  const params = new URLSearchParams({ scope: state.notesScope, q: $("#n-search").value.trim(), limit: "60" });
  setStatus("#notes-status", "Loading…");
  const { data } = await api(`/api/notes?${params}`);
  const list = $("#notes-list");
  list.textContent = "";
  if (!data.ok) return setStatus("#notes-status", data.error || "could not load notes", "error");

  setStatus("#notes-status", `${data.count} of ${data.total}${data.live ? "" : " (from the baked index)"}`);
  for (const n of data.notes) {
    const li = document.createElement("li");
    const mine = n.path.startsWith(`raw-notes/${state.me.dir}/`) || n.path.startsWith("raw-notes/commons/");
    li.innerHTML = `<span class="n-title"></span><span class="n-path"></span>`;
    li.querySelector(".n-title").textContent = n.title || n.id;
    li.querySelector(".n-path").textContent = n.path;
    if (!mine || n.canon) {
      const lock = document.createElement("span");
      lock.className = "n-lock";
      // A canon page is editable here but lands by PR, not by direct commit.
      lock.textContent = n.canon ? "review-gated" : "read-only";
      li.prepend(lock);
    }
    li.addEventListener("click", () => openNote(n.path));
    list.append(li);
  }
}

/* ================================= EDITOR ================================= */

$("#e-back").addEventListener("click", () => {
  show("notes");
  $$(".tab").forEach((x) => x.classList.toggle("is-active", x.dataset.go === "notes"));
});

async function openNote(path) {
  show("editor");
  setStatus("#editor-status", "Loading…");
  $("#editor-out").hidden = true;
  const { data } = await api(`/api/note?path=${encodeURIComponent(path)}`);
  if (!data.ok) return setStatus("#editor-status", data.error || "could not open that note", "error");

  state.editing = { path: data.path, sha: data.sha, original: data.content };
  $("#e-path").textContent = data.path;
  $("#e-summary").value = data.summary || "";
  $("#e-tags").value = (data.tags || []).join(", ");
  $("#e-body").value = data.body || "";

  const mine = data.path.startsWith(`raw-notes/${state.me.dir}/`);
  const shared = data.path.startsWith("raw-notes/commons/");
  const editable = mine || shared;
  const ro = $("#e-readonly");
  ro.hidden = true;
  if (!editable) {
    ro.hidden = false;
    ro.textContent = `This is someone else's note. You can read it, but you own raw-notes/${state.me.dir}/ and share raw-notes/commons/.`;
  } else if (data.canon) {
    ro.hidden = false;
    ro.textContent =
      "Canon page — these land by PR review, not by direct commit. Preview produces the exact file to put in that PR.";
  } else if (shared && !mine) {
    ro.hidden = false;
    ro.textContent = "Shared note — everyone in the club can edit this one.";
  }
  $("#e-preview").disabled = !editable;
  $("#e-save").disabled = !editable || data.canon || !state.config.commitsEnabled;
  setStatus("#editor-status", "");
}

$("#e-preview").addEventListener("click", () => submitEdit(true));
$("#e-save").addEventListener("click", () => submitEdit(false));

async function submitEdit(dryRun) {
  if (!state.editing) return;
  setStatus("#editor-status", dryRun ? "Building the file…" : "Committing…");
  const payload = {
    dryRun,
    path: state.editing.path,
    sha: state.editing.sha,
    original: state.editing.original,
    body: $("#e-body").value,
    summary: $("#e-summary").value,
    tags: $("#e-tags").value,
  };
  const { status, data } = await api("/api/save", { method: "POST", body: JSON.stringify(payload) });
  if (!data.ok) {
    setStatus("#editor-status", data.error || `failed (${status})`, "error");
    if (data.markdown) renderOut(data, "#editor-out", "#eout-badge", "#eout-path", "#eout-md", "#eout-msg", null, "#eout-dangling");
    return;
  }
  renderOut(data, "#editor-out", "#eout-badge", "#eout-path", "#eout-md", "#eout-msg", null, "#eout-dangling");
  if (data.commit && data.commit.committed) {
    setStatus("#editor-status", `Committed ${data.commit.commit.sha.slice(0, 7)}`, "ok");
    state.editing.sha = data.commit.commit.blobSha;
    state.editing.original = data.markdown;
  } else if (!data.changed) {
    setStatus("#editor-status", "Nothing changed.", "ok");
  } else {
    setStatus("#editor-status", "Dry run — nothing was written.", "ok");
    $("#e-save").classList.add("btn-emphasis");
  }
}

/* =================================== ME =================================== */

function renderMe() {
  const me = state.me;
  $("#me-card").innerHTML = `
    <h2>You</h2>
    <dl>
      <dt>handle</dt><dd><code>${esc(me.handle)}</code></dd>
      <dt>name</dt><dd>${esc(me.name || "—")}</dd>
      <dt>email</dt><dd>${esc(me.email)}</dd>
      <dt>identified</dt><dd>${esc(me.via)}</dd>
      <dt>your notes</dt><dd><code>${esc(me.notesDir)}</code>${me.dirKnown ? "" : " <em class='muted'>(will be created)</em>"}</dd>
      <dt>glossary</dt><dd><code>${esc(me.glossaryDir)}</code></dd>
    </dl>`;
}

function renderConfigCard(corpus) {
  const c = state.config;
  const baked = corpus.generated ? new Date(corpus.generated).toISOString().slice(0, 10) : "—";
  $("#config-card").innerHTML = `
    <h2>This app</h2>
    <dl>
      <dt>mode</dt><dd>${c.commitsEnabled ? "live — commits enabled" : "dry-run — no token configured"}</dd>
      <dt>repo</dt><dd><code>${esc(c.repo)}</code> @ <code>${esc(c.branch)}</code></dd>
      <dt>identity</dt><dd>${esc(c.auth)}</dd>
      <dt>note index</dt><dd>${corpus.counts.notes} notes · ${corpus.counts.sources} books · ${corpus.counts.tags} tags<br />
        <span class="muted small">${corpus.live ? "live from the repo" : `baked ${baked} — no live read available`}</span></dd>
    </dl>`;
}

function esc(s) {
  return String(s ?? "").replace(/[&<>"']/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" })[c]);
}
