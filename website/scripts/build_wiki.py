#!/usr/bin/env python3
"""
Renders `raw-notes/` into a static, browsable wiki under `website/wiki/`.

    python3 website/scripts/build_wiki.py --full            # rebuild everything
    python3 website/scripts/build_wiki.py --changed A.md B.md   # rebuild only what those touch
    npm run build:wiki                                      # == --full

Like `scripts/build.py`, this is a plain-stdlib generator whose output is
committed to the repo — Cloudflare Pages serves `website/` directly
(`pages_build_output_dir: "."`), so there is no build step at deploy time.

Output is **deterministic**: no page carries a wall-clock timestamp, so two
builds over the same tree produce byte-identical files and `wrangler pages
deploy` re-uploads only what actually changed. `--changed` must therefore agree
with `--full` byte for byte; the incremental path exists to save time, never to
produce different output.

What it produces
----------------
    website/wiki/index.html                     wiki home (contributors, books, recent changes)
    website/wiki/all.html                       every note, filterable
    website/wiki/wiki.css                       wiki-only styles (site style.css is loaded first)
    website/wiki/wiki-manifest.json             link graph + note index (input to --changed)
    website/wiki/<member>/index.html            per-contributor index
    website/wiki/<member>/<...>/<slug>.html     one page per note
    website/wiki/commons/reading/<book>/index.html   per-book index
    website/wiki/glossary/index.html            glossary index
    website/wiki/glossary/<term>.html           one page per glossary term

Conventions it follows
----------------------
* A note's wiki-link id is its filename stem, and link resolution is
  **case-sensitive exact match** — the same rule the knowledge lake uses
  (`tools/notes-pipeline/notes_to_parquet.py`). Links that do not resolve are
  rendered as muted, non-clickable text rather than dead hrefs.
* Glossary entries may declare `aliases:`; an alias resolves like a note id,
  but never shadows a real note with that exact stem.
* The top-level `wiki/` directory of this repo is the club's INTERNAL wiki and
  is deliberately NOT published. Only `raw-notes/` is.

Excluded from publishing
------------------------
* zero-byte notes (placeholders), `README.md`, `raw-notes/<member>/index.md`
  (hand-maintained tables of contents; the lake excludes them too),
  dotfiles/dot-directories, and every non-`.md` file (`_chunks.yaml`, `.gitkeep`).
"""

from __future__ import annotations

import argparse
import hashlib
import html
import json
import re
import subprocess
import sys
import time
import unicodedata
from collections import defaultdict
from datetime import datetime
from pathlib import Path
from urllib.parse import quote

# ─── Locations ───────────────────────────────────────────────────────────────

REPO_ROOT = Path(__file__).resolve().parents[2]
NOTES_ROOT = REPO_ROOT / "raw-notes"
OUT_ROOT = REPO_ROOT / "website" / "wiki"
MANIFEST_PATH = OUT_ROOT / "wiki-manifest.json"
MANIFEST_VERSION = 1

GITHUB_BLOB = "https://github.com/worldmachines/worldmachines/blob/main/"
GITHUB_COMMIT = "https://github.com/worldmachines/worldmachines/commit/"

# ─── Site chrome (kept in step with website/scripts/build.py NAV) ────────────

SITENAV = '''\
  <nav class="sitenav">
    <a href="/theory">Theory</a>
    <a href="/contributions">Contributions</a>
    <a href="/resources">Resources</a>
    <a href="/evolution/">Evolution</a>
    <a href="/wiki/">Wiki</a>
    <a href="/wiki/glossary/">Glossary</a>
    <a href="/contributors">Contributors</a>
    <a href="/devlog">Devlog</a>
    <a href="/oracle">Oracle</a>
    <a href="/mcp">MCP</a>
    <a href="https://discord.gg/tqUFztN3r">Project Chat</a>
  </nav>'''

# ─── Display metadata ────────────────────────────────────────────────────────

MEMBER_NAMES = {
    "aneesh": "Aneesh",
    "brandon": "Brandon",
    "commons": "Commons",
    "florian": "Florian",
    "ivo": "Ivo",
    "kyle": "Kyle",
    "patrick": "Patrick",
    "sean": "Sean",
    "venkat": "Venkat",
}

MEMBER_BLURBS = {
    "commons": "Shared, communal notes — AI-ingested reading notes for the books "
               "the whole club works through, plus the canon pages derived from them. "
               "Attributed to the pseudo-author <em>commons</em>, not to any one member.",
}

FOLDER_LABELS = {
    "_root": "Loose notes",
    "concepts": "Concepts",
    "entities": "Entities",
    "summaries": "Summaries",
    "synthesis": "Synthesis",
    "reading": "Reading notes",
    "Essays": "Essays",
    "Literature Notes": "Literature notes",
    "glossary": "Glossary",
}

FOLDER_ORDER = ["_root", "concepts", "entities", "summaries", "synthesis", "reading"]

# Optional polish for the books in commons/reading/. Unknown source ids still
# work — the title falls back to the parenthetical in `_chunks.yaml`, then to a
# prettified form of the directory name.
BOOK_META = {
    "adams-education": ("The Education of Henry Adams", "Henry Adams", "1918"),
    "appleby-relentless-revolution": ("The Relentless Revolution", "Joyce Appleby", "2010"),
    "chaucer-canterbury-tales": ("The Canterbury Tales, and Other Poems", "Geoffrey Chaucer", "c.1400"),
    "dante-divine-comedy": ("The Divine Comedy", "Dante Alighieri (Cary tr.)", "c.1320"),
    "decameron": ("The Decameron", "Giovanni Boccaccio", "c.1353"),
    "ingold-2023-possible-world": ("On Not Knowing and Paying Attention", "Tim Ingold", "2023"),
    "landes-revolution-in-time": ("Revolution in Time", "David S. Landes", "1983"),
    "more-utopia": ("Utopia", "Thomas More", "1516"),
}

GLOSSARY_STATUSES = ("seed", "developing", "settled")


# ─── Small helpers ───────────────────────────────────────────────────────────


def esc(s: str) -> str:
    """HTML-escape text for element content and attribute values."""
    return html.escape(s or "", quote=True)


def slugify(text: str) -> str:
    """Path-safe slug. Handles spaces, apostrophes, em dashes, accents, colons.

    'On the Monstrous -Why Tweaks Won't Cut It' -> on-the-monstrous-why-tweaks-wont-cut-it
    accents are folded; 'babel-was-a-clue (1)' -> babel-was-a-clue-1
    """
    text = unicodedata.normalize("NFKD", text)
    text = "".join(c for c in text if not unicodedata.combining(c))
    text = text.replace("&", " and ")
    text = re.sub(r"[‘’'`]", "", text)  # apostrophes vanish, they don't become dashes
    text = text.lower()
    text = re.sub(r"[^a-z0-9]+", "-", text)
    text = re.sub(r"-{2,}", "-", text).strip("-")
    return text or "untitled"


def prettify(name: str) -> str:
    return re.sub(r"[-_]+", " ", name).strip().title()


def fmt_date(value) -> str:
    if not value:
        return ""
    text = str(value)[:10]
    try:
        return datetime.strptime(text, "%Y-%m-%d").strftime("%-d %B %Y")
    except ValueError:
        return text


# ─── Frontmatter (a deliberately small YAML subset) ──────────────────────────

FRONTMATTER_RE = re.compile(r"\A---\s*\n(.*?)\n---\s*\n?(.*)\Z", re.DOTALL)


def _unquote(value: str) -> str:
    value = value.strip()
    if len(value) >= 2 and value[0] == value[-1] and value[0] in "\"'":
        inner = value[1:-1]
        return inner.replace("''", "'") if value[0] == "'" else inner
    return value


def parse_frontmatter(raw: str) -> tuple[dict, str]:
    """Return (frontmatter dict, body). Supports scalars, inline lists and
    block lists — everything the notes corpus actually uses."""
    m = FRONTMATTER_RE.match(raw)
    if not m:
        return {}, raw
    block, body = m.group(1), m.group(2)
    data: dict = {}
    lines = block.split("\n")
    i = 0
    while i < len(lines):
        line = lines[i]
        i += 1
        if not line.strip() or line.lstrip().startswith("#"):
            continue
        km = re.match(r"^([A-Za-z_][A-Za-z0-9_-]*):\s*(.*)$", line)
        if not km:
            continue
        key, rest = km.group(1), km.group(2).strip()
        if rest.startswith("[") and rest.endswith("]"):
            items = [_unquote(p) for p in rest[1:-1].split(",")]
            data[key] = [p for p in items if p]
        elif rest:
            # A quoted scalar may wrap over several lines.
            if rest[0] in "\"'" and not (len(rest) > 1 and rest.rstrip().endswith(rest[0])):
                quote_char, buf = rest[0], [rest]
                while i < len(lines):
                    buf.append(lines[i])
                    i += 1
                    if buf[-1].rstrip().endswith(quote_char):
                        break
                rest = " ".join(part.strip() for part in buf)
            data[key] = _unquote(rest)
        else:
            items = []
            while i < len(lines):
                nxt = lines[i]
                if re.match(r"^\s*-\s+", nxt):
                    items.append(_unquote(re.sub(r"^\s*-\s+", "", nxt)))
                    i += 1
                elif not nxt.strip():
                    i += 1
                else:
                    break
            data[key] = items
    return data, body


def as_list(value) -> list[str]:
    if value is None:
        return []
    if isinstance(value, list):
        return [str(v).strip() for v in value if str(v).strip()]
    text = str(value).strip()
    return [text] if text else []


# ─── Markdown → HTML ─────────────────────────────────────────────────────────

WIKI_LINK_RE = re.compile(r"\[\[([^\]\|#]+?)(?:#([^\]\|]*))?(?:\|([^\]]*))?\]\]")
CODE_SPAN_RE = re.compile(r"(`+)(.+?)\1", re.DOTALL)
MD_LINK_RE = re.compile(r"\[([^\]]+)\]\(\s*(<[^>]*>|[^)\s]+)(?:\s+\"[^\"]*\")?\s*\)")
MD_IMAGE_RE = re.compile(r"!\[([^\]]*)\]\(\s*(<[^>]*>|[^)\s]+)(?:\s+\"[^\"]*\")?\s*\)")
AUTOLINK_RE = re.compile(r"&lt;(https?://[^\s&]+)&gt;")
LIST_ITEM_RE = re.compile(r"^(\s*)([-*+]|\d{1,9}[.)])\s+(.*)$")
HEADING_RE = re.compile(r"^(#{1,6})\s+(.*?)\s*#*\s*$")
FENCE_RE = re.compile(r"^\s*(`{3,}|~{3,})\s*([A-Za-z0-9_+-]*)\s*$")
HR_RE = re.compile(r"^\s*(?:-{3,}|\*{3,}|_{3,})\s*$")
TABLE_SEP_RE = re.compile(r"^\s*\|?[\s:|-]*-[\s:|-]*\|[\s:|-]*$")
SETEXT_RE = re.compile(r"^\s*(=+|-{2,})\s*$")

SAFE_URL_RE = re.compile(r"^(https?:|mailto:|/|#|\.{1,2}/)", re.IGNORECASE)


def anchor_id(text: str) -> str:
    return slugify(re.sub(r"\[\[([^\]\|#]+?)(?:[#\|][^\]]*)?\]\]", r"\1", text))


def extract_wiki_links(body: str) -> dict[str, int]:
    """Occurrence count per link target, ignoring targets inside code spans.
    Same target grammar as the lake's parser: text before `#` or `|`."""
    stripped = CODE_SPAN_RE.sub(" ", body)
    counts: dict[str, int] = defaultdict(int)
    for m in WIKI_LINK_RE.finditer(stripped):
        target = (m.group(1) or "").strip()
        if target:
            counts[target] += 1
    return dict(counts)


class MarkdownRenderer:
    """A small, dependency-free renderer for the markdown subset the notes use:
    headings, paragraphs, lists, tables, blockquotes, fenced code, rules,
    emphasis, links, images and [[wiki-links]]."""

    def __init__(self, resolve_link=None):
        # resolve_link(target, anchor, label) -> html string
        self.resolve_link = resolve_link or (lambda t, a, l: esc(l))

    # -- inline ------------------------------------------------------------

    def inline(self, text: str) -> str:
        """Render one line's worth of inline markdown.

        Order matters. Code spans and wiki-links are lifted out of the *raw*
        text before HTML-escaping: escaping first would turn an apostrophe in a
        link id into `&#x27;`, whose `#` then reads as an anchor separator and
        silently breaks resolution for every id containing one.
        """
        text = text.replace("\x00", "")
        slots: list[str] = []

        def stash(fragment: str) -> str:
            slots.append(fragment)
            return f"\x00{len(slots) - 1}\x00"

        text = CODE_SPAN_RE.sub(lambda m: stash(f"<code>{esc(m.group(2).strip())}</code>"), text)

        def wikilink(m):
            target = (m.group(1) or "").strip()
            anchor = (m.group(2) or "").strip()
            label = (m.group(3) or "").strip() or target
            return stash(self.resolve_link(target, anchor, label))

        text = WIKI_LINK_RE.sub(wikilink, text)
        text = esc(text)

        def image(m):
            url = html.unescape(m.group(2).strip("<>"))
            if not SAFE_URL_RE.match(url):
                return m.group(0)
            return f'<img src="{esc(url)}" alt="{m.group(1)}" loading="lazy">'

        text = MD_IMAGE_RE.sub(image, text)

        def link(m):
            url = html.unescape(m.group(2).strip("<>"))
            if not SAFE_URL_RE.match(url):
                return m.group(0)
            return f'<a href="{esc(url)}">{m.group(1)}</a>'

        text = MD_LINK_RE.sub(link, text)
        text = AUTOLINK_RE.sub(lambda m: f'<a href="{esc(m.group(1))}">{esc(m.group(1))}</a>', text)

        text = re.sub(r"\*\*(?=\S)(.+?)(?<=\S)\*\*", r"<strong>\1</strong>", text, flags=re.DOTALL)
        text = re.sub(r"(?<![A-Za-z0-9_])__(?=\S)(.+?)(?<=\S)__(?![A-Za-z0-9_])",
                      r"<strong>\1</strong>", text, flags=re.DOTALL)
        text = re.sub(r"~~(?=\S)(.+?)(?<=\S)~~", r"<del>\1</del>", text, flags=re.DOTALL)
        text = re.sub(r"(?<![\*\w])\*(?=[^\s*])([^*\n]+?)(?<=\S)\*(?![\*\w])", r"<em>\1</em>", text)
        text = re.sub(r"(?<![A-Za-z0-9_])_(?=\S)([^_\n]+?)(?<=\S)_(?![A-Za-z0-9_])", r"<em>\1</em>", text)

        for idx, fragment in enumerate(slots):
            text = text.replace(f"\x00{idx}\x00", fragment)
        return text

    # -- blocks ------------------------------------------------------------

    def blocks(self, lines: list[str]) -> str:
        out: list[str] = []
        i = 0
        n = len(lines)
        while i < n:
            line = lines[i]

            if not line.strip():
                i += 1
                continue

            fence = FENCE_RE.match(line)
            if fence:
                marker = fence.group(1)[0] * 3
                lang = fence.group(2)
                i += 1
                buf = []
                while i < n and not (lines[i].lstrip().startswith(marker)
                                     and not lines[i].strip().strip(marker[0])):
                    buf.append(lines[i])
                    i += 1
                i += 1  # closing fence
                cls = f' class="language-{esc(lang)}"' if lang else ""
                out.append(f"<pre><code{cls}>{esc(chr(10).join(buf))}</code></pre>")
                continue

            heading = HEADING_RE.match(line)
            if heading:
                level = len(heading.group(1))
                raw_text = heading.group(2)
                aid = anchor_id(raw_text)
                out.append(f'<h{level} id="{esc(aid)}">{self.inline(raw_text)}</h{level}>')
                i += 1
                continue

            if HR_RE.match(line):
                out.append("<hr>")
                i += 1
                continue

            if line.lstrip().startswith(">"):
                buf = []
                while i < n and (lines[i].lstrip().startswith(">") or
                                 (lines[i].strip() and buf and not LIST_ITEM_RE.match(lines[i])
                                  and not HEADING_RE.match(lines[i]))):
                    buf.append(re.sub(r"^\s*>\s?", "", lines[i]))
                    i += 1
                out.append(f"<blockquote>{self.blocks(buf)}</blockquote>")
                continue

            if "|" in line and i + 1 < n and TABLE_SEP_RE.match(lines[i + 1]) and "|" in lines[i + 1]:
                i, table = self.table(lines, i)
                out.append(table)
                continue

            if LIST_ITEM_RE.match(line):
                i, lst = self.list_block(lines, i)
                out.append(lst)
                continue

            # paragraph (with single-line setext heading support)
            buf = [line]
            i += 1
            while i < n and lines[i].strip():
                nxt = lines[i]
                if len(buf) == 1 and SETEXT_RE.match(nxt) and not HR_RE.match(buf[0]):
                    level = 1 if nxt.strip().startswith("=") else 2
                    aid = anchor_id(buf[0])
                    out.append(f'<h{level} id="{esc(aid)}">{self.inline(buf[0].strip())}</h{level}>')
                    buf = []
                    i += 1
                    break
                if (HEADING_RE.match(nxt) or FENCE_RE.match(nxt) or HR_RE.match(nxt)
                        or LIST_ITEM_RE.match(nxt) or nxt.lstrip().startswith(">")):
                    break
                buf.append(nxt)
                i += 1
            if buf:
                text = "<br>\n".join(
                    self.inline(part.rstrip()) for part in self._merge_hard_breaks(buf)
                )
                out.append(f"<p>{text}</p>")
        return "\n".join(out)

    @staticmethod
    def _merge_hard_breaks(buf: list[str]) -> list[str]:
        """Markdown joins soft-wrapped lines; two trailing spaces force a break.

        One corpus-specific addition: a block whose lines all open with a bold
        label (`**Source**: …` / `**See also**: …`) is a metadata stack, not
        prose — 124 notes use that shape — so each label starts a new line.
        """
        label_block = bool(buf) and buf[0].lstrip().startswith("**")
        chunks: list[str] = []
        current: list[str] = []
        for idx, raw in enumerate(buf):
            current.append(raw.strip())
            nxt = buf[idx + 1] if idx + 1 < len(buf) else None
            hard = raw.rstrip("\n").endswith("  ")
            labelled = label_block and nxt is not None and nxt.lstrip().startswith("**")
            if hard or labelled:
                chunks.append(" ".join(current))
                current = []
        if current:
            chunks.append(" ".join(current))
        return chunks

    def table(self, lines: list[str], i: int) -> tuple[int, str]:
        def cells(row: str) -> list[str]:
            row = re.sub(r"\|$", "", re.sub(r"^\|", "", row.strip()))
            return [c.strip() for c in re.split(r"(?<!\\)\|", row)]

        header = cells(lines[i])
        aligns = []
        for spec in cells(lines[i + 1]):
            left, right = spec.startswith(":"), spec.endswith(":")
            aligns.append("center" if left and right else "right" if right else "left" if left else "")
        i += 2
        body_rows = []
        while i < len(lines) and lines[i].strip() and "|" in lines[i]:
            body_rows.append(cells(lines[i]))
            i += 1

        def cell_html(tag: str, value: str, idx: int) -> str:
            align = aligns[idx] if idx < len(aligns) else ""
            style = f' style="text-align:{align}"' if align else ""
            return f"<{tag}{style}>{self.inline(value.replace(chr(92) + '|', '|'))}</{tag}>"

        head = "".join(cell_html("th", c, k) for k, c in enumerate(header))
        body = "\n".join(
            "<tr>" + "".join(cell_html("td", c, k) for k, c in enumerate(row)) + "</tr>"
            for row in body_rows
        )
        return i, ('<div class="table-wrap"><table>\n<thead><tr>' + head + "</tr></thead>\n"
                   + (f"<tbody>\n{body}\n</tbody>\n" if body else "") + "</table></div>")

    def list_block(self, lines: list[str], i: int) -> tuple[int, str]:
        base_match = LIST_ITEM_RE.match(lines[i])
        base_indent = len(base_match.group(1).expandtabs(4))
        ordered = bool(re.match(r"\d", base_match.group(2)))
        items: list[list[str]] = []
        loose = False
        n = len(lines)
        pending_blank = False

        while i < n:
            line = lines[i]
            if not line.strip():
                pending_blank = True
                i += 1
                continue
            m = LIST_ITEM_RE.match(line)
            indent = len(re.match(r"^\s*", line).group(0).expandtabs(4))
            if m and indent <= base_indent + 1:
                if indent < base_indent:
                    break
                if items and pending_blank:
                    loose = True
                items.append([m.group(3)])
                pending_blank = False
                i += 1
                continue
            if not items:
                break
            if indent > base_indent:
                if pending_blank:
                    items[-1].append("")
                    loose = True
                items[-1].append(line[min(indent, base_indent + 2):])
                pending_blank = False
                i += 1
                continue
            if pending_blank:
                break  # blank line then unindented text ends the list
            items[-1].append(line.strip())  # lazy continuation
            i += 1

        rendered = []
        for item in items:
            inner = self.blocks(item).strip()
            if not loose:
                only_p = re.fullmatch(r"<p>(.*)</p>", inner, re.DOTALL)
                if only_p:
                    inner = only_p.group(1)
            rendered.append(f"<li>{inner}</li>")
        tag = "ol" if ordered else "ul"
        return i, f"<{tag}>\n" + "\n".join(rendered) + f"\n</{tag}>"

    def render(self, body: str) -> str:
        return self.blocks(body.replace("\r\n", "\n").replace("\r", "\n").split("\n"))


# ─── Notes ───────────────────────────────────────────────────────────────────


class Note:
    """One published page. `body`/`front` are lazy: an incremental build
    rehydrates unchanged notes from the manifest and only reads the files it
    actually re-renders."""

    __slots__ = ("rel", "member", "folder", "book", "note_id", "title", "url", "kind",
                 "term", "aliases", "status", "contributors", "summary", "outlinks",
                 "digest", "front", "body", "git")

    def __init__(self, **kw):
        for key in self.__slots__:
            setattr(self, key, kw.get(key))

    @property
    def path(self) -> Path:
        return NOTES_ROOT / self.rel

    @property
    def out_path(self) -> Path:
        return OUT_ROOT / (self.url[len("/wiki/"):] + ".html")

    def hydrate(self) -> None:
        if self.body is not None:
            return
        front, body = parse_frontmatter(self.path.read_text(encoding="utf-8", errors="replace"))
        _, body = split_title(body, prettify(self.path.stem))
        self.front, self.body = front, body

    def to_manifest(self) -> dict:
        return {
            "member": self.member, "folder": self.folder, "book": self.book,
            "note_id": self.note_id, "title": self.title, "url": self.url,
            "kind": self.kind, "term": self.term, "aliases": self.aliases,
            "status": self.status, "contributors": self.contributors,
            "summary": self.summary, "outlinks": self.outlinks, "digest": self.digest,
        }

    @classmethod
    def from_manifest(cls, rel: str, data: dict) -> "Note":
        return cls(rel=rel, front=None, body=None, git=None, **data)


def split_title(body: str, fallback: str) -> tuple[str, str]:
    """Pull a leading H1 off the body and use it as the page title."""
    lines = body.split("\n")
    for idx, line in enumerate(lines):
        if not line.strip():
            continue
        m = re.match(r"^#\s+(.*?)\s*#*\s*$", line)
        if m:
            return m.group(1).strip(), "\n".join(lines[idx + 1:])
        break
    m = re.search(r"^#\s+(.+?)\s*$", body, re.MULTILINE)
    return (m.group(1).strip() if m else fallback), body


def is_publishable(path: Path) -> tuple[bool, str]:
    try:
        rel = path.relative_to(NOTES_ROOT)
    except ValueError:
        return False, "outside"
    if any(part.startswith(".") for part in rel.parts):
        return False, "dotpath"
    if path.suffix.lower() != ".md":
        return False, "not-markdown"
    if path.name.lower() == "readme.md":
        return False, "readme"
    if len(rel.parts) < 2:
        return False, "top-level"
    if len(rel.parts) == 2 and rel.parts[1] == "index.md":
        return False, "member-index"
    if not path.is_file() or path.stat().st_size == 0:
        return False, "empty"
    return True, ""


def parse_note(path: Path) -> Note:
    rel = path.relative_to(NOTES_ROOT)
    raw_bytes = path.read_bytes()
    raw = raw_bytes.decode("utf-8", errors="replace")
    front, body = parse_frontmatter(raw)
    title, body = split_title(body, prettify(path.stem))

    is_glossary = len(rel.parts) >= 3 and rel.parts[0] == "commons" and rel.parts[1] == "glossary"
    book = rel.parts[2] if (len(rel.parts) >= 4 and rel.parts[0] == "commons"
                            and rel.parts[1] == "reading") else None
    summary = front.get("summary")

    # `connects:` entries are rendered as links on the page, so they belong in
    # the graph too — otherwise the target's backlink list would disagree with
    # what a reader can see pointing at it.
    outlinks = extract_wiki_links(body)
    for target in as_list(front.get("connects")):
        outlinks[target] = outlinks.get(target, 0) + 1

    return Note(
        rel=str(rel),
        member=rel.parts[0],
        folder="glossary" if is_glossary else (rel.parts[1] if len(rel.parts) > 2 else "_root"),
        book=book,
        note_id=path.stem,
        title=title,
        url=None,  # assigned by the URL allocator
        kind="glossary" if is_glossary else "note",
        term=(front.get("term") or title) if is_glossary else title,
        aliases=as_list(front.get("aliases")) if is_glossary else [],
        status=str(front.get("status") or "seed").strip().lower() if is_glossary else "",
        contributors=as_list(front.get("contributors")) if is_glossary else [],
        summary=summary if isinstance(summary, str) else "",
        outlinks=outlinks,
        digest=hashlib.sha256(raw_bytes).hexdigest()[:16],
        front=front,
        body=body,
        git=None,
    )


def reserved_urls() -> set[str]:
    """URLs the generator owns, so a note can never shadow an index page."""
    urls = {"/wiki/index", "/wiki/all", "/wiki/glossary/index"}
    if NOTES_ROOT.is_dir():
        for p in sorted(NOTES_ROOT.iterdir()):
            if p.is_dir() and not p.name.startswith("."):
                urls.add(f"/wiki/{slugify(p.name)}/index")
        for book_dir in sorted((NOTES_ROOT / "commons" / "reading").glob("*")):
            if book_dir.is_dir():
                urls.add(f"/wiki/commons/reading/{slugify(book_dir.name)}/index")
    return urls


def assign_url(note: Note, taken: set[str]) -> str:
    rel = Path(note.rel)
    if note.kind == "glossary":
        url_dir = "/wiki/glossary"
    else:
        url_dir = "/wiki/" + "/".join(slugify(p) for p in rel.parts[:-1])
    base = f"{url_dir}/{slugify(rel.stem)}"
    url, bump = base, 2
    while url in taken:
        url = f"{base}-{bump}"
        bump += 1
    taken.add(url)
    return url


def scan_corpus() -> tuple[list[Path], dict[str, int]]:
    paths, skipped = [], defaultdict(int)
    for path in sorted(NOTES_ROOT.rglob("*")):
        if not path.is_file():
            continue
        ok, why = is_publishable(path)
        if ok:
            paths.append(path)
        elif why not in ("not-markdown", "dotpath"):
            skipped[why] += 1
    return paths, dict(skipped)


# ─── Git history ─────────────────────────────────────────────────────────────


def git_history() -> tuple[dict[str, dict], list[dict]]:
    """(last commit per raw-notes path, newest-first commit list). Degrades to
    empty data outside a git checkout."""
    try:
        raw = subprocess.run(
            ["git", "log", "--no-color", "--pretty=format:\x01%H\x02%aI\x02%an\x02%s",
             "--name-only", "--", "raw-notes"],
            cwd=REPO_ROOT, capture_output=True, text=True, check=True, timeout=120,
        ).stdout
    except (subprocess.SubprocessError, FileNotFoundError, OSError):
        return {}, []

    last: dict[str, dict] = {}
    commits: list[dict] = []
    for chunk in raw.split("\x01"):
        if not chunk.strip():
            continue
        head, _, files_block = chunk.partition("\n")
        parts = head.split("\x02")
        if len(parts) < 4:
            continue
        commit = {"sha": parts[0], "date": parts[1][:10], "author": parts[2], "subject": parts[3],
                  "files": [f.strip() for f in files_block.split("\n")
                            if f.strip().startswith("raw-notes/")]}
        commits.append(commit)
        for f in commit["files"]:
            last.setdefault(f, commit)
    return last, commits


# ─── Link graph ──────────────────────────────────────────────────────────────


class LinkIndex:
    """Resolution and backlinks for the whole corpus, built from the manifest's
    outlink table — never from the rendering pass, so a partial rebuild sees the
    same graph a full one does."""

    def __init__(self, notes: list[Note]):
        self.by_id: dict[str, list[Note]] = defaultdict(list)
        for note in notes:
            self.by_id[note.note_id].append(note)
        self.ambiguous = {k: v for k, v in self.by_id.items() if len(v) > 1}

        self.aliases: dict[str, Note] = {}
        self.alias_conflicts: list[tuple[str, str]] = []
        for note in sorted((n for n in notes if n.kind == "glossary"), key=lambda n: n.rel):
            for alias in note.aliases:
                if alias in self.by_id:
                    self.alias_conflicts.append((alias, note.note_id))
                elif alias not in self.aliases:
                    self.aliases[alias] = note

        self.backlinks: dict[str, list[Note]] = defaultdict(list)
        self.dangling: dict[str, int] = defaultdict(int)
        self.resolved_hits = 0
        for note in sorted(notes, key=lambda n: n.rel):
            for target, count in sorted(note.outlinks.items()):
                dest = self.lookup(target)
                if dest is None:
                    self.dangling[target] += count
                    continue
                self.resolved_hits += count
                if dest is not note and note not in self.backlinks[dest.url]:
                    self.backlinks[dest.url].append(note)

    def lookup(self, target: str) -> Note | None:
        """Case-sensitive exact match on note id, then on glossary aliases."""
        hit = self.by_id.get(target)
        if hit:
            return sorted(hit, key=lambda n: n.rel)[0]
        return self.aliases.get(target)


def make_resolver(index: LinkIndex):
    def resolve(target: str, anchor: str, label: str) -> str:
        dest = index.lookup(target)
        if dest is None:
            return (f'<span class="wikilink-missing" '
                    f'title="No note in raw-notes/ is named &quot;{esc(target)}&quot;">'
                    f"{esc(label)}</span>")
        frag = f"#{esc(slugify(anchor))}" if anchor else ""
        cls = "wikilink wikilink-glossary" if dest.kind == "glossary" else "wikilink"
        return f'<a class="{cls}" href="{esc(dest.url)}{frag}">{esc(label)}</a>'
    return resolve


# ─── Page shell ──────────────────────────────────────────────────────────────


def wikinav(active: str = "") -> str:
    items = [("/wiki/", "Wiki home"), ("/wiki/all", "All notes"), ("/wiki/glossary/", "Glossary")]
    links = "".join(
        f'<a href="{href}"{" aria-current=\"page\"" if href == active else ""}>{label}</a>'
        for href, label in items
    )
    return f'  <nav class="wikinav" aria-label="Wiki">{links}</nav>'


def shell(title: str, body: str, active: str = "", description: str = "",
          script: str = "", stamp: str = "") -> str:
    """No wall-clock timestamp anywhere: identical input must give identical
    bytes, or every deploy re-uploads all ~1000 pages."""
    desc = f'\n  <meta name="description" content="{esc(description)}">' if description else ""
    tail = f"{script}  <!-- {stamp} -->\n" if stamp else script
    return f'''<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>{esc(title)} — World Machines</title>{desc}
  <link rel="stylesheet" href="/style.css">
  <link rel="stylesheet" href="/wiki/wiki.css">
</head>
<body>
  <header>
    <h1><a href="/" style="color:inherit">World Machines</a></h1>
    <a href="/submit" class="submit-link">Submit</a>
  </header>
{SITENAV}
{wikinav(active)}
  <main class="wiki">
{body}
  </main>
{tail}</body>
</html>
'''


def write(path: Path, content: str) -> bool:
    """Write only when the bytes change, so unchanged pages keep their mtime and
    `wrangler pages deploy` has nothing to re-upload."""
    data = content.encode("utf-8")
    if path.exists() and path.read_bytes() == data:
        return False
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(data)
    return True


def breadcrumb(parts: list[tuple[str, str]]) -> str:
    bits = [f'<a href="{esc(href)}">{esc(label)}</a>' if href else f"<span>{esc(label)}</span>"
            for href, label in parts]
    return '  <nav class="breadcrumb">' + " <b>/</b> ".join(bits) + "</nav>"


def member_label(member: str) -> str:
    return MEMBER_NAMES.get(member, prettify(member))


def folder_label(folder: str) -> str:
    return FOLDER_LABELS.get(folder, prettify(folder))


_BOOK_TITLE_CACHE: dict[str, tuple[str, str, str]] = {}


def book_title(source_id: str) -> tuple[str, str, str]:
    if source_id in _BOOK_TITLE_CACHE:
        return _BOOK_TITLE_CACHE[source_id]
    if source_id in BOOK_META:
        result = BOOK_META[source_id]
    else:
        result = (prettify(source_id), "", "")
        sidecar = NOTES_ROOT / "commons" / "reading" / source_id / "_chunks.yaml"
        if sidecar.exists():
            header = " ".join(
                line.lstrip("#").strip()
                for line in sidecar.read_text(encoding="utf-8", errors="replace").split("\n")[:8]
                if line.startswith("#")
            )
            m = re.search(r"\((.+?)[;)]", header)
            if m:
                first = m.group(1).split(",")
                result = (first[0].strip(), first[1].strip() if len(first) > 1 else "", "")
    _BOOK_TITLE_CACHE[source_id] = result
    return result


# ─── Note pages ──────────────────────────────────────────────────────────────


def note_meta_line(note: Note) -> str:
    bits = [f'<a href="/wiki/{slugify(note.member)}/">{esc(member_label(note.member))}</a>']
    if note.book:
        bits.append(f'<a href="/wiki/commons/reading/{slugify(note.book)}/">'
                    f"{esc(book_title(note.book)[0])}</a>")
    elif note.folder and note.folder != "_root":
        bits.append(esc(folder_label(note.folder)))
    updated = note.front.get("last_updated") or (note.git or {}).get("date")
    if updated:
        bits.append(f"updated {esc(fmt_date(updated))}")
    github = GITHUB_BLOB + quote(f"raw-notes/{note.rel}", safe="/")
    bits.append(f'<a href="{esc(github)}">source on GitHub</a>')
    return '  <div class="note-byline">' + " · ".join(bits) + "</div>"


def backlinks_section(index: LinkIndex, note: Note) -> str:
    refs = index.backlinks.get(note.url) or []
    if not refs:
        return ('  <section class="backlinks">\n'
                '    <h2>Linked from</h2>\n'
                '    <p class="empty-state">No other note links here yet.</p>\n'
                "  </section>")
    rows = "\n".join(
        f'      <li><a href="{esc(src.url)}">{esc(src.title)}</a>'
        f' <span class="muted">{esc(member_label(src.member))}</span></li>'
        for src in sorted(refs, key=lambda n: (n.member, n.title.lower(), n.rel))
    )
    return (f'  <section class="backlinks">\n    <h2>Linked from <span class="count">{len(refs)}</span></h2>\n'
            f"    <ul>\n{rows}\n    </ul>\n  </section>")


def render_note_page(note: Note, index: LinkIndex) -> str:
    note.hydrate()
    renderer = MarkdownRenderer(resolve_link=make_resolver(index))
    body_html = renderer.render(note.body)

    crumbs = [("/wiki/", "Wiki"), (f"/wiki/{slugify(note.member)}/", member_label(note.member))]
    if note.book:
        crumbs.append((f"/wiki/commons/reading/{slugify(note.book)}/", book_title(note.book)[0]))
    elif note.folder != "_root":
        crumbs.append(("", folder_label(note.folder)))
    crumbs.append(("", note.title))

    summary_html = ""
    if note.summary:
        summary_html = ('  <div class="note-summary">' + renderer.inline(note.summary.strip())
                        + "</div>")

    tags = as_list(note.front.get("tags"))
    tags_html = ('  <div class="tags">' + "".join(f'<span class="tag">{esc(t)}</span>' for t in tags)
                 + "</div>") if tags else ""

    connects = as_list(note.front.get("connects"))
    connects_html = ""
    if connects:
        resolver = make_resolver(index)
        connects_html = ('  <p class="note-connects"><b>Connects:</b> '
                         + ", ".join(resolver(t, "", t) for t in connects) + "</p>")

    git = note.git or {}
    history = ""
    if git:
        history = (f'  <p class="note-history">Last changed {esc(fmt_date(git["date"]))} by '
                   f'{esc(git["author"])} — <a href="{GITHUB_COMMIT}{esc(git["sha"])}">'
                   f'{esc(git["subject"])}</a></p>')

    body = "\n".join(filter(None, [
        breadcrumb(crumbs),
        '  <article class="note">',
        f"    <h1>{esc(note.title)}</h1>",
        note_meta_line(note),
        summary_html,
        tags_html,
        connects_html,
        '    <div class="prose">',
        body_html,
        "    </div>",
        "  </article>",
        backlinks_section(index, note),
        history,
        '  <p class="note-foot">Working note from <code>raw-notes/</code> — rough by design, '
        "not a settled club position.</p>",
    ]))
    return shell(note.title, body, description=note.summary[:200] if note.summary else "")


# ─── Glossary pages ──────────────────────────────────────────────────────────


def status_badge(status: str) -> str:
    status = status if status in GLOSSARY_STATUSES else "seed"
    return f'<span class="status status-{status}">{status}</span>'


def render_glossary_term(note: Note, index: LinkIndex) -> str:
    note.hydrate()
    renderer = MarkdownRenderer(resolve_link=make_resolver(index))
    body_html = renderer.render(note.body)

    meta = [status_badge(note.status)]
    extra = [a for a in note.aliases if a != note.term]
    if extra:
        meta.append("also called " + ", ".join(f"<em>{esc(a)}</em>" for a in extra))
    if note.contributors:
        meta.append("developed by " + ", ".join(esc(member_label(c)) for c in note.contributors))
    updated = note.front.get("last_updated") or (note.git or {}).get("date")
    if updated:
        meta.append("updated " + esc(fmt_date(updated)))
    github = GITHUB_BLOB + quote(f"raw-notes/{note.rel}", safe="/")
    meta.append(f'<a href="{esc(github)}">source on GitHub</a>')

    body = "\n".join(filter(None, [
        breadcrumb([("/wiki/", "Wiki"), ("/wiki/glossary/", "Glossary"), ("", note.term)]),
        '  <article class="note glossary-entry">',
        f"    <h1>{esc(note.term)}</h1>",
        '    <div class="note-byline">' + " · ".join(meta) + "</div>",
        '    <div class="prose">',
        body_html,
        "    </div>",
        "  </article>",
        backlinks_section(index, note),
        '  <p class="note-foot">A glossary entry is a definition under construction. '
        "To sharpen it, edit <code>raw-notes/commons/glossary/</code> and open a PR — "
        'see the <a href="https://github.com/worldmachines/worldmachines/blob/main/raw-notes/commons/glossary/README.md">'
        "glossary README</a>.</p>",
    ]))
    return shell(f"{note.term} — Glossary", body, active="/wiki/glossary/",
                 description=note.summary[:200] if note.summary else "")


def render_glossary_index(terms: list[Note], index: LinkIndex) -> str:
    if terms:
        rows = []
        for note in sorted(terms, key=lambda n: (n.term.lower(), n.rel)):
            summary = note.summary
            if not summary:
                note.hydrate()
                first = next((b for b in note.body.split("\n\n") if b.strip() and not b.startswith("#")), "")
                summary = re.sub(r"\s+", " ", re.sub(r"[*_`>]", "", first)).strip()[:220]
            extra = [a for a in note.aliases if a != note.term]
            aliases = f'<span class="muted">aka {esc(", ".join(extra))}</span>' if extra else ""
            backs = len(index.backlinks.get(note.url) or [])
            rows.append(
                f'    <li class="glossary-row">\n'
                f'      <div class="glossary-head"><a href="{esc(note.url)}">{esc(note.term)}</a>'
                f" {status_badge(note.status)} {aliases}</div>\n"
                f'      <p class="glossary-gloss">{MarkdownRenderer().inline(summary)}</p>\n'
                f'      <div class="glossary-meta">{backs} note{" links" if backs == 1 else "s link"} here</div>\n'
                f"    </li>"
            )
        listing = '  <ul class="glossary-list">\n' + "\n".join(rows) + "\n  </ul>"
    else:
        listing = '  <p class="empty-state">No glossary entries yet.</p>'

    body = f'''{breadcrumb([("/wiki/", "Wiki"), ("", "Glossary")])}
  <h1>Glossary</h1>
  <p class="lede">Terms the club is actively defining. A glossary entry is not a
  dictionary definition copied in from outside — it is <em>our</em> working
  definition, sharpened as the theory develops, with the notes that use the term
  linked underneath it.</p>
  <p class="lede small">Each entry carries a status: {status_badge("seed")} first draft,
  worth arguing with · {status_badge("developing")} in active use, still moving ·
  {status_badge("settled")} the club has converged.
  Add or evolve a term by editing <code>raw-notes/commons/glossary/</code> —
  <a href="https://github.com/worldmachines/worldmachines/blob/main/raw-notes/commons/glossary/README.md">how to contribute</a>.</p>
{listing}
'''
    return shell("Glossary", body, active="/wiki/glossary/",
                 description="Working definitions the World Machines book club is developing.")


# ─── Index pages ─────────────────────────────────────────────────────────────


def note_row(note: Note, show_member: bool = False) -> str:
    gloss = ""
    if note.summary:
        text = re.sub(r"\s+", " ", note.summary.strip())
        gloss = f'<p class="row-gloss">{esc(text[:240] + ("…" if len(text) > 240 else ""))}</p>'
    who = f' <span class="muted">{esc(member_label(note.member))}</span>' if show_member else ""
    return (f'      <li class="row"><a href="{esc(note.url)}">{esc(note.title)}</a>{who}\n'
            f"        {gloss}</li>")


def render_member_index(member: str, notes: list[Note]) -> str:
    groups: dict[str, list[Note]] = defaultdict(list)
    books: dict[str, list[Note]] = defaultdict(list)
    for note in notes:
        (books[note.book] if note.book else groups[note.folder]).append(note)

    sections = []
    if books:
        cards = []
        for book_id in sorted(books, key=lambda b: (book_title(b)[0].lower(), b)):
            title, author, year = book_title(book_id)
            meta = " · ".join(filter(None, [author, year, f"{len(books[book_id])} notes"]))
            cards.append(
                f'      <li class="book-card"><a href="/wiki/commons/reading/{slugify(book_id)}/">'
                f'{esc(title)}</a><span class="muted">{esc(meta)}</span></li>'
            )
        sections.append('  <section>\n    <h2>Books</h2>\n    <ul class="book-list">\n'
                        + "\n".join(cards) + "\n    </ul>\n  </section>")

    ordered = [f for f in FOLDER_ORDER if f in groups] + sorted(f for f in groups if f not in FOLDER_ORDER)
    for folder in ordered:
        items = sorted(groups[folder], key=lambda n: (n.title.lower(), n.rel))
        rows = "\n".join(note_row(n) for n in items)
        sections.append(f'  <section>\n    <h2>{esc(folder_label(folder))} '
                        f'<span class="count">{len(items)}</span></h2>\n'
                        f'    <ul class="rows">\n{rows}\n    </ul>\n  </section>')

    blurb = MEMBER_BLURBS.get(member, "")
    body = "\n".join(filter(None, [
        breadcrumb([("/wiki/", "Wiki"), ("", member_label(member))]),
        f"  <h1>{esc(member_label(member))}</h1>",
        f'  <p class="lede small">{len(notes)} published note{"" if len(notes) == 1 else "s"} from '
        f'<code>raw-notes/{esc(member)}/</code>.</p>',
        f'  <p class="lede">{blurb}</p>' if blurb else "",
        *sections,
    ]))
    return shell(member_label(member), body,
                 description=f"Working notes by {member_label(member)} in the World Machines wiki.")


def render_book_index(book_id: str, notes: list[Note]) -> str:
    title, author, year = book_title(book_id)
    rows = "\n".join(note_row(n) for n in sorted(notes, key=lambda n: n.rel))
    meta = " · ".join(filter(None, [author, year]))
    body = "\n".join(filter(None, [
        breadcrumb([("/wiki/", "Wiki"), ("/wiki/commons/", "Commons"), ("", title)]),
        f"  <h1>{esc(title)}</h1>",
        f'  <p class="lede small">{esc(meta)}{" · " if meta else ""}'
        f'{len(notes)} reading notes · source id <code>{esc(book_id)}</code></p>',
        "  <p class=\"lede\">Section-by-section reading notes produced by the club's ingestion "
        "pipeline and reviewed by a curator. The book's own text is never stored in the repo — "
        "these are notes <em>about</em> it, in reading order.</p>",
        f'  <ul class="rows">\n{rows}\n  </ul>',
    ]))
    return shell(title, body, description=f"Club reading notes on {title}.")


ALL_NOTES_SCRIPT = '''  <script>
    (function () {
      var box = document.getElementById('note-filter');
      var count = document.getElementById('note-count');
      if (!box) return;
      var rows = Array.prototype.slice.call(document.querySelectorAll('#all-notes .row'))
        .map(function (row) { return [row, row.textContent.toLowerCase()]; });
      box.addEventListener('input', function () {
        var q = box.value.trim().toLowerCase();
        var shown = 0;
        rows.forEach(function (pair) {
          var hit = !q || pair[1].indexOf(q) !== -1;
          pair[0].hidden = !hit;
          if (hit) shown++;
        });
        count.textContent = shown;
      });
    })();
  </script>
'''


def render_all_notes(notes: list[Note]) -> str:
    rows = []
    for note in sorted(notes, key=lambda n: (n.title.lower(), n.rel)):
        where = member_label(note.member)
        if note.book:
            where += " · " + book_title(note.book)[0]
        elif note.folder != "_root":
            where += " · " + folder_label(note.folder)
        rows.append(
            f'      <li class="row"><a href="{esc(note.url)}">{esc(note.title)}</a> '
            f'<span class="muted">{esc(where)}</span></li>'
        )
    body = f'''{breadcrumb([("/wiki/", "Wiki"), ("", "All notes")])}
  <h1>All notes</h1>
  <p class="lede small"><span id="note-count">{len(notes)}</span> of {len(notes)} notes</p>
  <input id="note-filter" type="text" placeholder="Filter by title or contributor…" autocomplete="off">
  <ul class="rows" id="all-notes">
{chr(10).join(rows)}
  </ul>
'''
    return shell("All notes", body, active="/wiki/all", script=ALL_NOTES_SCRIPT,
                 description="Every published note in the World Machines wiki.")


def render_home(notes: list[Note], glossary: list[Note], index: LinkIndex,
                commits: list[dict]) -> str:
    by_member: dict[str, list[Note]] = defaultdict(list)
    for note in notes:
        by_member[note.member].append(note)

    member_cards = []
    for member in sorted(by_member, key=lambda m: (m == "commons", member_label(m).lower())):
        items = by_member[member]
        folders = sorted({"Reading notes" if n.book else folder_label(n.folder) for n in items})
        member_cards.append(
            f'      <li class="member-card">\n'
            f'        <a href="/wiki/{slugify(member)}/">{esc(member_label(member))}</a>\n'
            f'        <span class="count">{len(items)}</span>\n'
            f'        <span class="muted">{esc(" · ".join(folders))}</span>\n'
            f"      </li>"
        )

    books: dict[str, list[Note]] = defaultdict(list)
    for note in notes:
        if note.book:
            books[note.book].append(note)
    book_cards = []
    for book_id in sorted(books, key=lambda b: (book_title(b)[0].lower(), b)):
        title, author, year = book_title(book_id)
        meta = " · ".join(filter(None, [author, year]))
        book_cards.append(
            f'      <li class="book-card">\n'
            f'        <a href="/wiki/commons/reading/{slugify(book_id)}/">{esc(title)}</a>\n'
            f'        <span class="count">{len(books[book_id])}</span>\n'
            f'        <span class="muted">{esc(meta)}</span>\n'
            f"      </li>"
        )

    by_path = {f"raw-notes/{n.rel}": n for n in notes}
    recent = []
    for commit in commits:
        touched = [by_path[f] for f in commit["files"] if f in by_path]
        if not touched:
            continue
        shown = touched[:5]
        links = ", ".join(f'<a href="{esc(n.url)}">{esc(n.title)}</a>' for n in shown)
        if len(touched) > len(shown):
            links += f' <span class="muted">+{len(touched) - len(shown)} more</span>'
        recent.append(
            f'      <li class="change">\n'
            f'        <div class="change-meta">{esc(fmt_date(commit["date"]))} · {esc(commit["author"])} · '
            f'<a href="{GITHUB_COMMIT}{esc(commit["sha"])}">{esc(commit["sha"][:7])}</a></div>\n'
            f'        <div class="change-subject">{esc(commit["subject"])}</div>\n'
            f'        <div class="change-notes">{links}</div>\n'
            f"      </li>"
        )
        if len(recent) >= 12:
            break

    glossary_line = ""
    if glossary:
        links = ", ".join(f'<a href="{esc(g.url)}">{esc(g.term)}</a>'
                          for g in sorted(glossary, key=lambda n: (n.term.lower(), n.rel)))
        glossary_line = (f'  <p class="lede">Currently defining: {links}. '
                         f'<a href="/wiki/glossary/">Open the glossary →</a></p>')

    dangling_total = sum(index.dangling.values())
    stamp = (f"generated from raw-notes at {commits[0]['sha'][:12]} ({commits[0]['date']})"
             if commits else "generated from raw-notes")
    body = f'''  <h1>Wiki</h1>
  <p class="lede">Everything the club has written in <code>raw-notes/</code>, published as it
  stands: reading notes on the books we work through, concept and entity pages, essays,
  and the loose fragments in between. Notes are rough by design — this is the working
  layer, not a finished encyclopedia. The <a href="/oracle">Oracle</a> searches the same
  corpus; this is the version you can read and link.</p>
{glossary_line}
  <ul class="stat-row">
    <li><b>{len(notes)}</b> notes</li>
    <li><b>{len(by_member)}</b> contributors</li>
    <li><b>{len(books)}</b> books</li>
    <li><b>{len(glossary)}</b> glossary terms</li>
    <li><b>{index.resolved_hits}</b> resolved links</li>
  </ul>

  <section>
    <h2>By contributor</h2>
    <ul class="member-list">
{chr(10).join(member_cards)}
    </ul>
  </section>

  <section>
    <h2>By book</h2>
    <p class="section-note">Communal reading notes in <code>raw-notes/commons/reading/</code>,
    one page per section of each source.</p>
    <ul class="book-list">
{chr(10).join(book_cards)}
    </ul>
  </section>

  <section>
    <h2>Recent changes</h2>
    <ul class="changes">
{chr(10).join(recent) if recent else '      <li class="change"><div class="change-subject">No git history available.</div></li>'}
    </ul>
  </section>

  <p class="note-foot">Links written <code>[[like this]]</code> resolve by exact,
  case-sensitive note id; {dangling_total} link{"" if dangling_total == 1 else "s"} point at
  notes that do not exist in this repo and are shown as <span class="wikilink-missing">plain
  grey text</span>. Browse <a href="/wiki/all">all notes</a>.</p>
'''
    return shell("Wiki", body, active="/wiki/", stamp=stamp,
                 description="The World Machines book club's working notes, published as a wiki.")


# ─── Stylesheet ──────────────────────────────────────────────────────────────

WIKI_CSS = """/* Wiki section styles. Loaded after /style.css, which supplies the design
   tokens (--bg, --text, --muted, --border, --link) and the site chrome. */

.wikinav {
  max-width: var(--max-width);
  margin: 0 auto;
  padding: 0.45rem 0 0.5rem;
  border-bottom: 1px solid var(--border);
  display: flex;
  gap: 1.2rem;
  font-family: system-ui, sans-serif;
  font-size: 0.75rem;
}
.wikinav a { color: var(--muted); }
.wikinav a:hover { color: var(--text); text-decoration: none; }
.wikinav a[aria-current="page"] { color: var(--text); }

main.wiki { max-width: var(--max-width); margin: 2rem auto 5rem; }

.breadcrumb {
  font-family: system-ui, sans-serif;
  font-size: 0.72rem;
  color: var(--muted);
  margin-bottom: 1.1rem;
}
.breadcrumb a { color: var(--muted); }
.breadcrumb a:hover { color: var(--text); }
.breadcrumb b { color: var(--border); font-weight: normal; margin: 0 0.15rem; }

main.wiki h1 {
  font-size: 1.5rem;
  font-weight: normal;
  line-height: 1.3;
  letter-spacing: -0.01em;
  margin-bottom: 0.6rem;
}

main.wiki .lede {
  font-size: 0.93rem;
  line-height: 1.75;
  color: #2a2a2a;
  margin-bottom: 1rem;
}
main.wiki .lede.small { font-family: system-ui, sans-serif; font-size: 0.78rem; color: var(--muted); }
.muted { color: var(--muted); }

.count {
  font-family: system-ui, sans-serif;
  font-size: 0.7rem;
  color: var(--muted);
  border: 1px solid var(--border);
  border-radius: 2px;
  padding: 0.05rem 0.3rem;
  vertical-align: middle;
}

.stat-row {
  list-style: none;
  display: flex;
  flex-wrap: wrap;
  gap: 0.35rem 1.4rem;
  font-family: system-ui, sans-serif;
  font-size: 0.76rem;
  color: var(--muted);
  border-top: 1px solid var(--border);
  border-bottom: 1px solid var(--border);
  padding: 0.6rem 0;
  margin: 1.5rem 0 2rem;
}
.stat-row b { color: var(--text); font-weight: 600; }

main.wiki section { margin-bottom: 2.5rem; }
main.wiki section > h2 {
  font-family: system-ui, sans-serif;
  font-size: 0.78rem;
  font-weight: 600;
  text-transform: uppercase;
  letter-spacing: 0.07em;
  color: var(--muted);
  padding-bottom: 0.45rem;
  border-bottom: 1px solid var(--border);
  margin-bottom: 0.9rem;
}
.section-note {
  font-family: system-ui, sans-serif;
  font-size: 0.76rem;
  color: var(--muted);
  margin-bottom: 0.8rem;
}

/* ─── Listings ─────────────────────────────────────────────── */

.member-list, .book-list, .rows, .changes, .glossary-list, .backlinks ul { list-style: none; }

.member-card, .book-card {
  padding: 0.6rem 0;
  border-bottom: 1px solid var(--border);
  display: flex;
  align-items: baseline;
  gap: 0.5rem;
  flex-wrap: wrap;
}
.member-card:last-child, .book-card:last-child { border-bottom: none; }
.member-card a, .book-card a { font-size: 1rem; color: var(--text); }
.member-card a:hover, .book-card a:hover { color: var(--link); text-decoration: none; }
.member-card .muted, .book-card .muted {
  font-family: system-ui, sans-serif;
  font-size: 0.73rem;
  margin-left: auto;
  text-align: right;
}

.rows .row {
  padding: 0.5rem 0;
  border-bottom: 1px solid var(--border);
  font-size: 0.95rem;
}
.rows .row:last-child { border-bottom: none; }
.rows .row a { color: var(--text); }
.rows .row a:hover { color: var(--link); text-decoration: none; }
.rows .row .muted { font-family: system-ui, sans-serif; font-size: 0.72rem; }
.row-gloss {
  font-family: system-ui, sans-serif;
  font-size: 0.78rem;
  color: var(--muted);
  line-height: 1.5;
  margin-top: 0.15rem;
}

#note-filter {
  width: 100%;
  margin: 0.4rem 0 1.2rem;
  font-family: system-ui, sans-serif;
  font-size: 0.85rem;
  padding: 0.45rem 0.6rem;
  border: 1px solid var(--border);
  border-radius: 3px;
  background: #fff;
}

.changes .change { padding: 0.7rem 0; border-bottom: 1px solid var(--border); }
.changes .change:last-child { border-bottom: none; }
.change-meta { font-family: system-ui, sans-serif; font-size: 0.71rem; color: var(--muted); }
.change-subject { font-size: 0.95rem; margin: 0.1rem 0 0.15rem; }
.change-notes { font-family: system-ui, sans-serif; font-size: 0.76rem; line-height: 1.6; }

/* ─── Note page ────────────────────────────────────────────── */

.note-byline {
  font-family: system-ui, sans-serif;
  font-size: 0.73rem;
  color: var(--muted);
  padding-bottom: 0.8rem;
  border-bottom: 1px solid var(--border);
  margin-bottom: 1.2rem;
}
.note-byline a { color: var(--muted); text-decoration: underline; text-decoration-color: var(--border); }
.note-byline a:hover { color: var(--text); }

.note-summary {
  font-size: 0.93rem;
  line-height: 1.7;
  color: #2a2a2a;
  border-left: 2px solid var(--border);
  padding: 0.1rem 0 0.1rem 0.9rem;
  margin-bottom: 1.1rem;
}

.tags { display: flex; flex-wrap: wrap; gap: 0.3rem; margin-bottom: 1.4rem; }
.tag {
  font-family: system-ui, sans-serif;
  font-size: 0.66rem;
  color: var(--muted);
  border: 1px solid var(--border);
  border-radius: 2px;
  padding: 0.08rem 0.35rem;
}
.note-connects { font-family: system-ui, sans-serif; font-size: 0.78rem; color: var(--muted); margin-bottom: 1.2rem; }

/* ─── Prose ────────────────────────────────────────────────── */

.prose { font-size: 0.97rem; line-height: 1.8; color: #2a2a2a; }
.prose h1, .prose h2, .prose h3, .prose h4, .prose h5, .prose h6 {
  font-weight: normal;
  line-height: 1.35;
  color: var(--text);
  margin: 2rem 0 0.6rem;
}
.prose h1 { font-size: 1.3rem; }
.prose h2 { font-size: 1.12rem; padding-top: 1.2rem; border-top: 1px solid var(--border); }
.prose h3 { font-size: 1rem; font-weight: 600; }
.prose h4, .prose h5, .prose h6 { font-size: 0.93rem; font-weight: 600; }
.prose p { margin-bottom: 0.9rem; }
.prose ul, .prose ol { margin: 0 0 1rem 1.3rem; }
.prose li { margin-bottom: 0.35rem; }
.prose li > ul, .prose li > ol { margin-top: 0.35rem; margin-bottom: 0.35rem; }
.prose blockquote {
  border-left: 2px solid var(--border);
  padding-left: 1rem;
  margin: 0 0 1rem;
  color: #444;
  font-style: italic;
}
.prose blockquote p:last-child { margin-bottom: 0; }
.prose hr { border: none; border-top: 1px solid var(--border); margin: 1.8rem 0; }
.prose code {
  font-family: 'Courier New', monospace;
  font-size: 0.85em;
  background: #f0ede8;
  padding: 0.1em 0.3em;
  border-radius: 2px;
}
.prose pre {
  background: #f0ede8;
  border: 1px solid var(--border);
  border-radius: 3px;
  padding: 0.8rem 0.9rem;
  overflow-x: auto;
  margin-bottom: 1rem;
}
.prose pre code { background: none; padding: 0; font-size: 0.8rem; line-height: 1.55; }
.prose img { max-width: 100%; height: auto; }

.table-wrap { overflow-x: auto; margin-bottom: 1.2rem; }
.prose table { border-collapse: collapse; font-size: 0.85rem; min-width: 100%; }
.prose th, .prose td {
  border: 1px solid var(--border);
  padding: 0.4rem 0.6rem;
  text-align: left;
  vertical-align: top;
}
.prose th { background: #f3f1ec; font-weight: 600; }

/* ─── Wiki links ───────────────────────────────────────────── */

.wikilink { border-bottom: 1px solid rgba(26, 76, 138, 0.25); }
.wikilink:hover { text-decoration: none; border-bottom-color: var(--link-hover); }
.wikilink-glossary { border-bottom-style: dotted; }
.wikilink-missing {
  color: #9a9a9a;
  border-bottom: 1px dotted #cfcbc4;
  cursor: help;
}

/* ─── Backlinks ────────────────────────────────────────────── */

.backlinks { margin-top: 3rem; }
.backlinks h2 {
  font-family: system-ui, sans-serif;
  font-size: 0.78rem;
  font-weight: 600;
  text-transform: uppercase;
  letter-spacing: 0.07em;
  color: var(--muted);
  padding-bottom: 0.45rem;
  border-bottom: 1px solid var(--border);
  margin-bottom: 0.7rem;
}
.backlinks li { padding: 0.3rem 0; font-size: 0.92rem; }
.backlinks li .muted { font-family: system-ui, sans-serif; font-size: 0.71rem; margin-left: 0.35rem; }
.backlinks .empty-state { padding: 0.5rem 0; font-size: 0.85rem; }

.note-history, .note-foot {
  font-family: system-ui, sans-serif;
  font-size: 0.73rem;
  color: var(--muted);
  margin-top: 1.5rem;
  padding-top: 0.9rem;
  border-top: 1px solid var(--border);
}
.note-foot code { font-size: 0.95em; }

/* ─── Glossary ─────────────────────────────────────────────── */

.glossary-row { padding: 0.9rem 0; border-bottom: 1px solid var(--border); }
.glossary-row:last-child { border-bottom: none; }
.glossary-head { display: flex; align-items: baseline; gap: 0.45rem; flex-wrap: wrap; }
.glossary-head a { font-size: 1.05rem; color: var(--text); }
.glossary-head a:hover { color: var(--link); text-decoration: none; }
.glossary-head .muted { font-family: system-ui, sans-serif; font-size: 0.72rem; }
.glossary-gloss {
  font-family: system-ui, sans-serif;
  font-size: 0.82rem;
  color: #444;
  line-height: 1.6;
  margin-top: 0.25rem;
}
.glossary-meta { font-family: system-ui, sans-serif; font-size: 0.7rem; color: var(--muted); margin-top: 0.25rem; }

.status {
  font-family: system-ui, sans-serif;
  font-size: 0.62rem;
  font-weight: 600;
  text-transform: uppercase;
  letter-spacing: 0.05em;
  padding: 0.1rem 0.38rem;
  border-radius: 2px;
}
.status-seed       { background: #fff3cd; color: #7a5200; }
.status-developing { background: #dbeafe; color: #1e3a8a; }
.status-settled    { background: #d1fae5; color: #065f46; }
"""


# ─── Manifest ────────────────────────────────────────────────────────────────


def load_manifest() -> dict[str, dict] | None:
    if not MANIFEST_PATH.exists():
        return None
    try:
        data = json.loads(MANIFEST_PATH.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError):
        return None
    if data.get("version") != MANIFEST_VERSION:
        return None
    return data.get("notes") or {}


def save_manifest(notes: list[Note]) -> bool:
    payload = {
        "version": MANIFEST_VERSION,
        "notes": {n.rel: n.to_manifest() for n in sorted(notes, key=lambda n: n.rel)},
    }
    return write(MANIFEST_PATH, json.dumps(payload, sort_keys=True, indent=1, ensure_ascii=False) + "\n")


# ─── Build ───────────────────────────────────────────────────────────────────


def collect_notes(changed: list[Path] | None) -> tuple[list[Note], dict[str, int], dict[str, Note], set[str]]:
    """Return (all notes, skip counts, previous-state notes, changed rel paths).

    A full build parses every file. An incremental build parses only `changed`
    and rehydrates the rest from the manifest, which is why the manifest has to
    carry every field the index pages and backlink sections read.
    """
    previous = load_manifest()
    if changed is None or previous is None:
        paths, skipped = scan_corpus()
        taken = reserved_urls()
        notes = []
        for path in paths:
            note = parse_note(path)
            note.url = assign_url(note, taken)
            notes.append(note)
        old = {rel: Note.from_manifest(rel, d) for rel, d in (previous or {}).items()}
        return notes, skipped, old, {n.rel for n in notes} | set(old)

    old = {rel: Note.from_manifest(rel, d) for rel, d in previous.items()}
    notes_by_rel = {rel: Note.from_manifest(rel, d) for rel, d in previous.items()}
    taken = reserved_urls() | {n.url for n in notes_by_rel.values()}
    skipped: dict[str, int] = defaultdict(int)
    touched: set[str] = set()

    for path in changed:
        rel = str(path.relative_to(NOTES_ROOT)) if path.is_absolute() else str(path)
        rel = rel[len("raw-notes/"):] if rel.startswith("raw-notes/") else rel
        full = NOTES_ROOT / rel
        ok, why = is_publishable(full)
        if not ok:
            if rel in notes_by_rel:  # published note that was deleted or emptied
                taken.discard(notes_by_rel[rel].url)
                del notes_by_rel[rel]
                touched.add(rel)
            if why not in ("not-markdown", "dotpath", "outside"):
                skipped[why] += 1
            continue
        note = parse_note(full)
        stale = notes_by_rel.get(rel)
        if stale is not None and stale.digest == note.digest:
            continue  # byte-identical: nothing to do
        note.url = stale.url if stale is not None else assign_url(note, taken)
        notes_by_rel[rel] = note
        touched.add(rel)

    return sorted(notes_by_rel.values(), key=lambda n: n.rel), dict(skipped), old, touched


def invalidated(notes: list[Note], old: dict[str, Note], touched: set[str],
                index: LinkIndex) -> set[str]:
    """Which note pages have to be re-rendered because `touched` changed.

    Three ways a page goes stale: it is the changed note; it is a note the
    changed note links to (its backlink list moved); or it links to an id whose
    existence flipped (a dangling link became live, or the reverse).
    """
    current = {n.rel: n for n in notes}
    flipped_ids: set[str] = set()
    for rel in touched:
        before, after = old.get(rel), current.get(rel)
        if before is None or after is None:
            flipped_ids.add((after or before).note_id)
            flipped_ids.update((after or before).aliases)
            continue
        if before.note_id != after.note_id:
            flipped_ids.update({before.note_id, after.note_id})
        flipped_ids.update(set(before.aliases) ^ set(after.aliases))

    stale = {rel for rel in touched if rel in current}
    for rel in touched:
        for source in (old.get(rel), current.get(rel)):
            if source is None:
                continue
            for target in source.outlinks:
                dest = index.lookup(target)
                if dest is not None:
                    stale.add(dest.rel)
    if flipped_ids:
        for note in notes:
            if flipped_ids & set(note.outlinks):
                stale.add(note.rel)
    return stale


def build(changed: list[Path] | None, quiet: bool = False) -> int:
    started = time.perf_counter()
    if not NOTES_ROOT.is_dir():
        print(f"error: {NOTES_ROOT} not found", file=sys.stderr)
        return 2

    notes, skipped, old, touched = collect_notes(changed)
    if not notes:
        print("error: no publishable notes found", file=sys.stderr)
        return 2

    last_commit, commits = git_history()
    for note in notes:
        note.git = last_commit.get(f"raw-notes/{note.rel}")

    index = LinkIndex(notes)
    glossary = [n for n in notes if n.kind == "glossary"]
    plain = [n for n in notes if n.kind != "glossary"]

    if changed is None:
        stale = {n.rel for n in notes}
    else:
        stale = invalidated(notes, old, touched, index)

    written = 0
    by_rel = {n.rel: n for n in notes}
    for rel in sorted(stale):
        note = by_rel.get(rel)
        if note is None:
            continue
        page = render_glossary_term(note, index) if note.kind == "glossary" \
            else render_note_page(note, index)
        written += write(note.out_path, page)

    # Pages removed along with their note.
    removed = 0
    for rel in sorted(touched):
        if rel in by_rel or rel not in old:
            continue
        gone = old[rel].out_path
        if gone.exists():
            gone.unlink()
            removed += 1

    by_member: dict[str, list[Note]] = defaultdict(list)
    for note in plain:
        by_member[note.member].append(note)
    for member, items in sorted(by_member.items()):
        written += write(OUT_ROOT / slugify(member) / "index.html",
                         render_member_index(member, items))

    books: dict[str, list[Note]] = defaultdict(list)
    for note in plain:
        if note.book:
            books[note.book].append(note)
    for book_id, items in sorted(books.items()):
        written += write(OUT_ROOT / "commons" / "reading" / slugify(book_id) / "index.html",
                         render_book_index(book_id, items))

    written += write(OUT_ROOT / "glossary" / "index.html", render_glossary_index(glossary, index))
    written += write(OUT_ROOT / "all.html", render_all_notes(plain))
    written += write(OUT_ROOT / "index.html", render_home(plain, glossary, index, commits))
    written += write(OUT_ROOT / "wiki.css", WIKI_CSS)
    written += save_manifest(notes)

    elapsed = time.perf_counter() - started
    mode = "full" if changed is None else f"incremental ({len(touched)} source change(s))"
    print(f"wiki [{mode}]: {len(plain)} notes, {len(glossary)} glossary terms, "
          f"{len(by_member)} contributors, {len(books)} books — "
          f"{len(stale)} page(s) rendered, {written} file(s) written"
          f"{f', {removed} removed' if removed else ''} in {elapsed:.2f}s")
    if quiet:
        return 0
    print(f"  links: {index.resolved_hits} resolved, "
          f"{sum(index.dangling.values())} dangling across {len(index.dangling)} targets")
    for note_id, hits in sorted(index.ambiguous.items()):
        print(f"  ambiguous id '{note_id}' ({len(hits)} notes) -> "
              f"{sorted(hits, key=lambda n: n.rel)[0].rel}")
    for alias, owner in index.alias_conflicts:
        print(f"  alias '{alias}' (glossary '{owner}') shadowed by a real note of that name")
    if skipped:
        print("  skipped: " + ", ".join(f"{k}={v}" for k, v in sorted(skipped.items())))
    top = sorted(index.dangling.items(), key=lambda kv: (-kv[1], kv[0]))[:8]
    if top:
        print("  most-linked missing notes: " + ", ".join(f"{t} ({c})" for t, c in top))
    return 0


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description="Build website/wiki/ from raw-notes/.")
    ap.add_argument("--full", action="store_true",
                    help="rebuild every page (default when --changed is absent)")
    ap.add_argument("--changed", nargs="*", metavar="PATH",
                    help="rebuild only the pages affected by these note paths "
                         "(repo-relative, e.g. raw-notes/aneesh/foo.md); an empty list is a no-op")
    ap.add_argument("--quiet", action="store_true", help="print the summary line only")
    args = ap.parse_args(argv)

    if args.changed is not None and not args.full:
        return build([Path(p) for p in args.changed], quiet=args.quiet)
    return build(None, quiet=args.quiet)


if __name__ == "__main__":
    raise SystemExit(main())
