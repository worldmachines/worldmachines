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
    website/wiki/index.html                     the front door — ideas first
    website/wiki/all.html                       A–Z index of every note
    website/wiki/hubs.html                      most-linked notes, ranked
    website/wiki/wanted/index.html              pages the corpus asks for but does not have
    website/wiki/wanted/<slug>.html             one page per wanted title
    website/wiki/topics/index.html              every shared tag
    website/wiki/topics/<slug>.html             one page per shared tag
    website/wiki/special.html                   maintenance desk (orphans, loose links, stats)
    website/wiki/orphans.html                   notes nothing links to
    website/wiki/loose-links.html               links resolved by normalisation — fix at source
    website/wiki/changes.html                   full recent-changes list from git
    website/wiki/search.html                    search results page (reads ?q=)
    website/wiki/search-index.json              prebuilt search index
    website/wiki/wiki.js                        search + filter behaviour (vanilla, no deps)
    website/wiki/wiki.css                       wiki-only styles (site style.css is loaded first)
    website/wiki/wiki-manifest.json             link graph + note index (input to --changed)
    website/wiki/<member>/index.html            per-contributor index
    website/wiki/<member>/<...>/<slug>.html     one page per note
    website/wiki/commons/reading/<book>/index.html   per-book index
    website/wiki/glossary/index.html            glossary index
    website/wiki/glossary/<term>.html           one page per glossary term

Conventions it follows
----------------------
* A note's wiki-link id is its filename stem. Resolution runs in tiers:
  **exact, case-sensitive match** first — the rule the knowledge lake uses
  (`tools/notes-pipeline/notes_to_parquet.py`), so the canonical graph is
  unchanged — then glossary `aliases:`, then a **normalised match** on the
  slug, which is how `[[Modernity Machine]]` reaches `modernity-machine.md`.
  Normalised hits are only taken when exactly one note claims the slug, and
  every one of them is listed on `/wiki/loose-links` so the club can tighten
  the link at source. A target no tier resolves becomes a **wanted link** —
  red, clickable, and pointing at a page that says who is asking for it.
* `connects:`, `supports:` and `contradicts:` frontmatter are rendered as
  links, so they count as edges in the graph too — otherwise a target's
  backlink list would disagree with what a reader can see pointing at it.
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
MANIFEST_VERSION = 2

GITHUB_REPO = "https://github.com/worldmachines/worldmachines"
GITHUB_BLOB = GITHUB_REPO + "/blob/main/"
GITHUB_COMMIT = GITHUB_REPO + "/commit/"
GITHUB_NEW = GITHUB_REPO + "/new/main/raw-notes/commons/concepts"

# A tag becomes a topic page once at least this many notes share it. Below the
# threshold a tag is one note's own keyword, not a topic anyone can browse.
TOPIC_MIN_NOTES = 2

# How many entries the front page shows before handing off to the full listing.
HOME_HUBS = 22
HOME_WANTED = 8
HOME_CHANGES = 8

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
                 "digest", "front", "body", "git",
                 "tags", "supports", "contradicts", "connects", "words")

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
            "tags": self.tags, "supports": self.supports, "contradicts": self.contradicts,
            "connects": self.connects, "words": self.words,
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

    # `connects:`, `supports:` and `contradicts:` are rendered as links on the
    # page, so they belong in the graph too — otherwise the target's backlink
    # list would disagree with what a reader can see pointing at it.
    connects = as_list(front.get("connects"))
    supports = as_list(front.get("supports"))
    contradicts = as_list(front.get("contradicts"))
    outlinks = extract_wiki_links(body)
    for target in connects + supports + contradicts:
        outlinks[target] = outlinks.get(target, 0) + 1

    return Note(
        tags=as_list(front.get("tags")),
        supports=supports,
        contradicts=contradicts,
        connects=connects,
        words=len(body.split()),
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
    urls = {"/wiki/index", "/wiki/all", "/wiki/glossary/index",
            "/wiki/hubs", "/wiki/orphans", "/wiki/loose-links", "/wiki/changes",
            "/wiki/special", "/wiki/search", "/wiki/wanted/index",
            "/wiki/topics/index"}
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
    """Resolution, backlinks and the wanted list for the whole corpus, built from
    the manifest's outlink table — never from the rendering pass, so a partial
    rebuild sees exactly the graph a full one does.

    Resolution runs in tiers so that the canonical, case-sensitive graph the
    knowledge lake uses stays the primary reading, and normalisation only ever
    rescues links that would otherwise be dead:

        exact note id  →  glossary alias  →  normalised slug  →  wanted
    """

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

        # Normalised index. A slug claimed by more than one distinct note id is
        # not safe to guess at, so it resolves to nothing and stays wanted.
        claims: dict[str, set[str]] = defaultdict(set)
        owners: dict[str, Note] = {}
        for note in sorted(notes, key=lambda n: n.rel):
            key = slugify(note.note_id)
            claims[key].add(note.note_id)
            owners.setdefault(key, note)
        for alias, note in sorted(self.aliases.items()):
            key = slugify(alias)
            if key not in claims:
                claims[key].add(alias)
                owners.setdefault(key, note)
        self.by_slug = {k: owners[k] for k, ids in claims.items() if len(ids) == 1}
        self.slug_conflicts = {k: sorted(ids) for k, ids in claims.items() if len(ids) > 1}

        # Every way a note can be named, normalised — its filename stem and its
        # displayed title both count, because contributors use either.
        self.by_name: dict[str, list[Note]] = defaultdict(list)
        for note in sorted(notes, key=lambda n: n.rel):
            for key in dict.fromkeys([slugify(note.note_id), slugify(note.title)]):
                if key:
                    self.by_name[key].append(note)

        # A glossary term and the concept note of the same name are the same
        # idea at two stages of settling, so each page has to be able to find
        # the other. Match on the normalised name, never on identity.
        self.defined: dict[str, Note] = {}
        for note in sorted((n for n in notes if n.kind == "glossary"), key=lambda n: n.rel):
            for name in [note.term, note.note_id, *note.aliases]:
                self.defined.setdefault(slugify(name), note)

        # Tags become topic pages once shared. Everything downstream of this —
        # the topic pages, the topic index, the rail — reads this one table.
        buckets: dict[str, list[Note]] = defaultdict(list)
        labels: dict[str, dict[str, int]] = defaultdict(lambda: defaultdict(int))
        for note in sorted(notes, key=lambda n: n.rel):
            for tag in dict.fromkeys(note.tags):
                key = slugify(tag)
                if not key:
                    continue
                buckets[key].append(note)
                labels[key][tag] += 1
        self.topics = {k: v for k, v in buckets.items() if len(v) >= TOPIC_MIN_NOTES}
        self.topic_labels = {
            k: max(sorted(labels[k]), key=lambda t: labels[k][t]) for k in self.topics
        }

        # One pass over every edge in the corpus, in a fixed order.
        self.backlinks: dict[str, list[Note]] = defaultdict(list)
        self.targets: dict[str, list[Note]] = defaultdict(list)
        self.wanted: dict[str, int] = defaultdict(int)
        self.wanted_sources: dict[str, list[Note]] = defaultdict(list)
        self.loose: dict[str, Note] = {}
        self.loose_sources: dict[str, list[Note]] = defaultdict(list)
        self.resolved_hits = 0
        self.loose_hits = 0
        for note in sorted(notes, key=lambda n: n.rel):
            for target, count in sorted(note.outlinks.items()):
                dest, tier = self.resolve(target)
                if dest is None:
                    self.wanted[target] += count
                    self.wanted_sources[target].append(note)
                    continue
                self.resolved_hits += count
                if tier == "slug":
                    self.loose_hits += count
                    self.loose[target] = dest
                    self.loose_sources[target].append(note)
                if dest is not note:
                    if note not in self.backlinks[dest.url]:
                        self.backlinks[dest.url].append(note)
                    if dest not in self.targets[note.rel]:
                        self.targets[note.rel].append(dest)

    def resolve(self, target: str) -> tuple[Note | None, str]:
        """(destination, tier). Tier is exact | alias | slug | ''."""
        hit = self.by_id.get(target)
        if hit:
            return sorted(hit, key=lambda n: n.rel)[0], "exact"
        alias = self.aliases.get(target)
        if alias is not None:
            return alias, "alias"
        near = self.by_slug.get(slugify(target))
        if near is not None:
            return near, "slug"
        return None, ""

    def lookup(self, target: str) -> Note | None:
        return self.resolve(target)[0]

    def glossary_for(self, note: Note) -> Note | None:
        """The glossary entry that defines this note's subject, if there is one."""
        if note.kind == "glossary":
            return None
        for name in (note.note_id, note.title):
            hit = self.defined.get(slugify(name))
            if hit is not None:
                return hit
        return None

    def notes_for_term(self, term: Note) -> list[Note]:
        """Notes whose own name is this glossary term — the working pages behind
        the definition, as opposed to everything that merely mentions it."""
        keys = sorted({slugify(n) for n in [term.term, term.note_id, *term.aliases] if slugify(n)})
        seen: list[Note] = []
        for key in keys:
            for note in self.by_name.get(key) or []:
                if note.kind != "glossary" and note not in seen:
                    seen.append(note)
        return sorted(seen, key=lambda n: (-self.inbound(n), n.title.lower(), n.rel))

    def inbound(self, note: Note) -> int:
        return len(self.backlinks.get(note.url) or [])

    def outbound(self, note: Note) -> int:
        return len(self.targets.get(note.rel) or [])

    def alongside(self, note: Note, limit: int = 7) -> list[tuple[Note, int]]:
        """Notes that get cited in the same breath as this one.

        For every note S that links here, count what else S links to. A note
        that keeps turning up next to this one in other people's arguments is a
        lateral move worth offering — and unlike a folder, nobody had to file it.

        Invalidation note: this reading depends only on `sources(note)` and what
        those sources link to, so it can only change when a note that links here
        changes. `invalidated()` already re-renders every target of a changed
        note, which is exactly that set.
        """
        scores: dict[str, int] = defaultdict(int)
        seen: dict[str, Note] = {}
        for source in self.backlinks.get(note.url) or []:
            for peer in self.targets.get(source.rel) or []:
                if peer is note:
                    continue
                scores[peer.rel] += 1
                seen[peer.rel] = peer
        ranked = sorted(scores.items(), key=lambda kv: (-kv[1], seen[kv[0]].title.lower(), kv[0]))
        return [(seen[rel], hits) for rel, hits in ranked[:limit] if hits > 1]

    def wanted_groups(self) -> list[dict]:
        """Wanted targets folded by slug, newest spelling wins the display name.

        `[[Data Generation Process]]` and `[[data-generation-process]]` are one
        missing page, not two, so they share one wanted page and pool the notes
        asking for them.
        """
        groups: dict[str, dict] = {}
        for target in sorted(self.wanted):
            key = slugify(target)
            group = groups.setdefault(key, {"slug": key, "names": [], "hits": 0, "sources": []})
            group["names"].append(target)
            group["hits"] += self.wanted[target]
            for source in self.wanted_sources[target]:
                if source not in group["sources"]:
                    group["sources"].append(source)
        for group in groups.values():
            # The most-linked spelling is the one the club actually writes.
            group["name"] = max(group["names"], key=lambda t: (self.wanted[t], t))
            group["sources"].sort(key=lambda n: (n.member, n.title.lower(), n.rel))
        return sorted(groups.values(), key=lambda g: (-len(g["sources"]), -g["hits"], g["slug"]))


def wanted_url(slug: str) -> str:
    return f"/wiki/wanted/{slug}"


def topic_url(slug: str) -> str:
    return f"/wiki/topics/{slug}"


def make_resolver(index: LinkIndex):
    def resolve(target: str, anchor: str, label: str) -> str:
        dest, tier = index.resolve(target)
        if dest is None:
            # Classic red link: the page does not exist, and saying so out loud
            # is an invitation, not an error. It goes somewhere useful.
            return (f'<a class="wikilink-wanted" href="{esc(wanted_url(slugify(target)))}" '
                    f'title="No note is called &quot;{esc(target)}&quot; yet — see who is asking for it">'
                    f"{esc(label)}</a>")
        frag = f"#{esc(slugify(anchor))}" if anchor else ""
        cls = "wikilink wikilink-glossary" if dest.kind == "glossary" else "wikilink"
        # A normalised hit reads as an ordinary link; the mismatch is a job for
        # an editor, listed on /wiki/loose-links, not a wart for every reader.
        hint = (f' title="Written [[{esc(target)}]], resolved to {esc(dest.note_id)}"'
                if tier == "slug" else "")
        return f'<a class="{cls}" href="{esc(dest.url)}{frag}"{hint}>{esc(label)}</a>'
    return resolve


# ─── Page shell ──────────────────────────────────────────────────────────────


WIKINAV_ITEMS = [
    ("/wiki/", "Index"),
    ("/wiki/all", "A–Z"),
    ("/wiki/glossary/", "Glossary"),
    ("/wiki/topics/", "Topics"),
    ("/wiki/hubs", "Most linked"),
    ("/wiki/wanted/", "Wanted"),
    ("/wiki/special", "Special"),
]


def wikinav(active: str = "") -> str:
    links = "".join(
        f'<a href="{href}"{" aria-current=\"page\"" if href == active else ""}>{esc(label)}</a>'
        for href, label in WIKINAV_ITEMS
    )
    return f'''  <nav class="wikinav" aria-label="Wiki sections">
    <div class="wikinav-links">{links}</div>
    <form class="wikisearch" action="/wiki/search" method="get" role="search">
      <label class="visually-hidden" for="wiki-q">Search the wiki</label>
      <input id="wiki-q" name="q" type="search" placeholder="Search the wiki" autocomplete="off"
             spellcheck="false" aria-describedby="wiki-q-hint">
      <span id="wiki-q-hint" class="visually-hidden">Press slash to jump here</span>
      <div id="wiki-q-results" class="wikisearch-results" hidden></div>
    </form>
  </nav>'''


def shell(title: str, body: str, active: str = "", description: str = "",
          script: str = "", stamp: str = "", wide: bool = False) -> str:
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
<body class="wiki-page">
  <header>
    <h1><a href="/" style="color:inherit">World Machines</a></h1>
    <a href="/submit" class="submit-link">Submit</a>
  </header>
{SITENAV}
{wikinav(active)}
  <main class="wiki{' wiki-wide' if wide else ''}">
{body}
  </main>
  <script src="/wiki/wiki.js" defer></script>
{tail}</body>
</html>
'''


# ─── The index plate ─────────────────────────────────────────────────────────
#
# One typographic primitive, used on the front page, the most-linked page, the
# topic pages, the wanted list and the orphan list. A row is always the same
# claim: a name, what it is, and the number of notes leaning on it — set with
# the figure in the margin like the page reference in a back-of-book index.
# Type size steps with that figure, so a column of rows reads as a skyline
# before you read a single word.

PLATE_STEPS = ((60, "mag-4"), (25, "mag-3"), (8, "mag-2"), (0, "mag-1"))


def magnitude(count: int) -> str:
    for floor, cls in PLATE_STEPS:
        if count >= floor:
            return cls
    return "mag-1"


def plate_row(href: str, name: str, figure: int, gloss: str = "", meta: str = "",
              scaled: bool = True, unit: str = "", wanted: bool = False) -> str:
    """One line of the index plate."""
    cls = "plate-row " + (magnitude(figure) if scaled else "mag-1")
    if wanted:
        cls += " plate-wanted"
    gloss_html = f'\n      <p class="plate-gloss">{gloss}</p>' if gloss else ""
    meta_html = f'<span class="plate-meta">{meta}</span>' if meta else ""
    unit_html = f'<span class="plate-unit">{esc(unit)}</span>' if unit else ""
    return (f'      <li class="{cls}">\n'
            f'        <span class="plate-line">'
            f'<a class="plate-name" href="{esc(href)}">{esc(name)}</a>'
            f'<span class="plate-leader" aria-hidden="true"></span>'
            f'<span class="plate-figure">{figure}{unit_html}</span></span>'
            f"{meta_html}{gloss_html}\n      </li>")


def plate(rows: list[str], extra: str = "") -> str:
    if not rows:
        return '    <p class="empty-state">Nothing here yet.</p>'
    cls = f"plate {extra}".strip()
    return f'    <ul class="{cls}">\n' + "\n".join(rows) + "\n    </ul>"


def section(label: str, inner: str, aside: str = "", note: str = "", ident: str = "") -> str:
    """A labelled register: eyebrow on the left, a link or count on the right."""
    right = f'<span class="section-aside">{aside}</span>' if aside else ""
    note_html = f'\n    <p class="section-note">{note}</p>' if note else ""
    attr = f' id="{esc(ident)}"' if ident else ""
    return (f'  <section{attr}>\n    <h2 class="register">'
            f'<span>{esc(label)}</span>{right}</h2>{note_html}\n{inner}\n  </section>')


def figure_band(pairs: list[tuple[str, str]]) -> str:
    cells = "".join(
        f'      <div class="band-cell"><b>{value}</b><span>{esc(label)}</span></div>\n'
        for value, label in pairs
    )
    return f'  <div class="figure-band">\n{cells}  </div>'


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
    updated = (note.front or {}).get("last_updated") or (note.git or {}).get("date")
    if updated:
        bits.append(f"updated {esc(fmt_date(updated))}")
    github = GITHUB_BLOB + quote(f"raw-notes/{note.rel}", safe="/")
    bits.append(f'<a href="{esc(github)}">source on GitHub</a>')
    return '    <div class="note-byline">' + " · ".join(bits) + "</div>"


def rail_block(label: str, inner: str, count: str = "") -> str:
    figure = f'<span class="rail-count">{esc(count)}</span>' if count else ""
    return (f'    <div class="rail-block">\n      <h2 class="rail-label">'
            f"<span>{esc(label)}</span>{figure}</h2>\n{inner}\n    </div>")


def rail_note_list(notes: list[Note], index: LinkIndex, show: int = 8,
                   more_label: str = "more") -> str:
    """A list of notes, first `show` open, the rest behind a native disclosure."""
    def row(note: Note) -> str:
        return (f'        <li><a href="{esc(note.url)}">{esc(note.title)}</a>'
                f'<span class="rail-where">{esc(member_label(note.member))}</span></li>')

    head, tail = notes[:show], notes[show:]
    out = '      <ul class="rail-list">\n' + "\n".join(row(n) for n in head) + "\n      </ul>"
    if tail:
        out += (f'\n      <details class="rail-more">\n'
                f'        <summary>{len(tail)} {esc(more_label)}</summary>\n'
                f'        <ul class="rail-list">\n' + "\n".join(row(n) for n in tail)
                + "\n        </ul>\n      </details>")
    return out


def note_rail(note: Note, index: LinkIndex) -> str:
    blocks: list[str] = []

    # Bearings: where this note sits in the graph, in figures.
    inbound, outbound = index.inbound(note), index.outbound(note)
    blocks.append(
        '    <div class="rail-block rail-bearings">\n'
        f'      <div class="bearing"><b>{inbound}</b><span>linked from</span></div>\n'
        f'      <div class="bearing"><b>{outbound}</b><span>links out</span></div>\n'
        f'      <div class="bearing"><b>{note.words or 0}</b><span>words</span></div>\n'
        "    </div>"
    )

    # The settled definition, when the club has one for this note's subject.
    term = index.glossary_for(note)
    if term is not None:
        gloss = re.sub(r"\s+", " ", term.summary or "").strip()
        gloss = gloss[:180] + ("…" if len(gloss) > 180 else "")
        blocks.append(rail_block("Defined as", (
            f'      <a class="rail-term" href="{esc(term.url)}">{esc(term.term)}</a>\n'
            f"      {status_badge(term.status)}\n"
            f'      <p class="rail-gloss">{esc(gloss)}</p>'
        )))

    refs = sorted(index.backlinks.get(note.url) or [],
                  key=lambda n: (-index.inbound(n), n.title.lower(), n.rel))
    blocks.append(rail_block(
        "What links here",
        rail_note_list(refs, index) if refs
        else '      <p class="rail-empty">Nothing links here yet. It is an <a href="/wiki/orphans">orphan</a>.</p>',
        count=str(len(refs)),
    ))

    peers = index.alongside(note)
    if peers:
        rows = "\n".join(
            f'        <li><a href="{esc(peer.url)}">{esc(peer.title)}</a>'
            f'<span class="rail-where">{hits}</span></li>'
            for peer, hits in peers
        )
        blocks.append(rail_block("Mentioned alongside", (
            f'      <ul class="rail-list rail-scored">\n{rows}\n      </ul>\n'
            '      <p class="rail-hint">Notes the same pages link to.</p>'
        )))

    # Typed edges the contributor declared by hand.
    resolver = make_resolver(index)
    for label, targets in (("Supports", note.supports), ("Contradicts", note.contradicts),
                           ("Connects", note.connects)):
        if targets:
            links = "".join(f'<li>{resolver(t, "", t)}</li>' for t in targets)
            blocks.append(rail_block(label, f'      <ul class="rail-edges">{links}</ul>'))

    if note.tags:
        chips = []
        for tag in dict.fromkeys(note.tags):
            key = slugify(tag)
            if key in index.topics:
                chips.append(f'<a class="tag" href="{esc(topic_url(key))}">{esc(tag)}</a>')
            else:
                chips.append(f'<span class="tag tag-lone" title="Only this note uses it">{esc(tag)}</span>')
        blocks.append(rail_block("Topics", '      <div class="tags">' + "".join(chips) + "</div>"))

    return '  <aside class="rail" aria-label="Connections">\n' + "\n".join(blocks) + "\n  </aside>"


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
        summary_html = ('    <div class="note-summary">' + renderer.inline(note.summary.strip())
                        + "</div>")

    git = note.git or {}
    history = ""
    if git:
        history = (f'    <p class="note-history">Last changed {esc(fmt_date(git["date"]))} by '
                   f'{esc(git["author"])} — <a href="{GITHUB_COMMIT}{esc(git["sha"])}">'
                   f'{esc(git["subject"])}</a></p>')

    body = "\n".join(filter(None, [
        breadcrumb(crumbs),
        '  <div class="spread">',
        '  <article class="note">',
        f"    <h1>{esc(note.title)}</h1>",
        note_meta_line(note),
        summary_html,
        '    <div class="prose">',
        body_html,
        "    </div>",
        history,
        '    <p class="note-foot">Working note from <code>raw-notes/</code> — rough by design, '
        "not a settled club position.</p>",
        "  </article>",
        note_rail(note, index),
        "  </div>",
    ]))
    return shell(note.title, body, wide=True,
                 description=note.summary[:200] if note.summary else "")


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
    updated = (note.front or {}).get("last_updated") or (note.git or {}).get("date")
    if updated:
        meta.append("updated " + esc(fmt_date(updated)))
    github = GITHUB_BLOB + quote(f"raw-notes/{note.rel}", safe="/")
    meta.append(f'<a href="{esc(github)}">source on GitHub</a>')

    blocks: list[str] = []
    inbound = index.inbound(note)
    blocks.append(
        '    <div class="rail-block rail-bearings">\n'
        f'      <div class="bearing"><b>{inbound}</b><span>notes use it</span></div>\n'
        f'      <div class="bearing"><b>{note.words or 0}</b><span>words</span></div>\n'
        "    </div>"
    )

    # The working pages that carry this term. A definition and the notes that
    # bear its name are one idea at two stages, so the entry says which is which.
    working = index.notes_for_term(note)
    if working:
        rows = "\n".join(
            f'        <li><a href="{esc(n.url)}">{esc(n.title)}</a>'
            f'<span class="rail-where">{index.inbound(n)}</span></li>' for n in working)
        blocks.append(rail_block("The notes behind it", (
            f'      <ul class="rail-list rail-scored">\n{rows}\n      </ul>\n'
            '      <p class="rail-hint">Notes named for this term. The definition is '
            "the summary; these are the argument.</p>"
        )))

    refs = sorted(index.backlinks.get(note.url) or [],
                  key=lambda n: (-index.inbound(n), n.title.lower(), n.rel))
    named = {n.rel for n in working}
    using = [n for n in refs if n.rel not in named]
    blocks.append(rail_block(
        "Used in",
        rail_note_list(using, index) if using
        else '      <p class="rail-empty">No note has used this term yet.</p>',
        count=str(len(using)),
    ))
    rail = '  <aside class="rail" aria-label="Connections">\n' + "\n".join(blocks) + "\n  </aside>"

    body = "\n".join(filter(None, [
        breadcrumb([("/wiki/", "Wiki"), ("/wiki/glossary/", "Glossary"), ("", note.term)]),
        '  <div class="spread">',
        '  <article class="note glossary-entry">',
        '    <p class="eyebrow">Glossary term</p>',
        f"    <h1>{esc(note.term)}</h1>",
        '    <div class="note-byline">' + " · ".join(meta) + "</div>",
        '    <div class="prose">',
        body_html,
        "    </div>",
        '    <p class="note-foot">A glossary entry is a definition under construction. '
        "To sharpen it, edit <code>raw-notes/commons/glossary/</code> and open a PR — "
        f'see the <a href="{GITHUB_BLOB}raw-notes/commons/glossary/README.md">'
        "glossary README</a>.</p>",
        "  </article>",
        rail,
        "  </div>",
    ]))
    return shell(f"{note.term} — Glossary", body, active="/wiki/glossary/", wide=True,
                 description=note.summary[:200] if note.summary else "")


def glossary_card(note: Note, index: LinkIndex) -> str:
    summary = note.summary
    if not summary:
        note.hydrate()
        first = next((b for b in note.body.split("\n\n") if b.strip() and not b.startswith("#")), "")
        summary = re.sub(r"\s+", " ", re.sub(r"[*_`>]", "", first)).strip()[:220]
    extra = [a for a in note.aliases if a != note.term]
    aliases = f'<span class="muted">also called {esc(", ".join(extra))}</span>' if extra else ""
    backs = index.inbound(note)
    return (
        f'      <li class="term-card">\n'
        f'        <div class="term-head"><a href="{esc(note.url)}">{esc(note.term)}</a>'
        f" {status_badge(note.status)} {aliases}</div>\n"
        f'        <p class="term-gloss">{MarkdownRenderer().inline(summary)}</p>\n'
        f'        <div class="term-meta">{backs} note{" links" if backs == 1 else "s link"} here</div>\n'
        f"      </li>"
    )


def undefined_candidates(index: LinkIndex, notes: list[Note], limit: int = 10) -> list[Note]:
    """Load-bearing concepts with no agreed definition — the glossary's worklist."""
    out = []
    for note in sorted(notes, key=lambda n: (-index.inbound(n), n.title.lower(), n.rel)):
        if note.kind == "glossary" or note.folder not in ("concepts", "synthesis"):
            continue
        if index.glossary_for(note) is not None:
            continue
        out.append(note)
        if len(out) >= limit:
            break
    return out


def render_glossary_index(terms: list[Note], index: LinkIndex, notes: list[Note]) -> str:
    if terms:
        cards = "\n".join(glossary_card(n, index)
                          for n in sorted(terms, key=lambda n: (n.term.lower(), n.rel)))
        listing = f'    <ul class="term-list">\n{cards}\n    </ul>'
    else:
        listing = '    <p class="empty-state">No glossary entries yet.</p>'

    waiting = undefined_candidates(index, notes)
    rows = [plate_row(n.url, n.title, index.inbound(n), meta=esc(member_label(n.member)))
            for n in waiting]

    body = f'''{breadcrumb([("/wiki/", "Wiki"), ("", "Glossary")])}
  <p class="eyebrow">The vocabulary the club has agreed on</p>
  <h1>Glossary</h1>
  <p class="lede">A glossary entry is not a dictionary definition copied in from
  outside. It is <em>our</em> working definition, sharpened as the theory
  develops, with every note that uses the term gathered underneath it.</p>
  <p class="lede small">Status says how settled a term is: {status_badge("seed")} first
  draft, worth arguing with · {status_badge("developing")} in active use, still
  moving · {status_badge("settled")} the club has converged. Add or evolve a term
  by editing <code>raw-notes/commons/glossary/</code> —
  <a href="{GITHUB_BLOB}raw-notes/commons/glossary/README.md">how to contribute</a>.</p>
{section("Defined", listing, aside=f"{len(terms)} terms")}
{section("Waiting for a definition", plate(rows),
         aside='<a href="/wiki/hubs">all →</a>',
         note="The concepts the corpus leans on hardest that no entry defines yet. "
              "The figure is how many notes link to them.")}
'''
    return shell("Glossary", body, active="/wiki/glossary/",
                 description="Working definitions the World Machines book club is developing.")


# ─── Index pages ─────────────────────────────────────────────────────────────


def clip(text: str, limit: int) -> str:
    text = re.sub(r"\s+", " ", (text or "").strip())
    return text[:limit] + ("…" if len(text) > limit else "")


def note_plate_row(note: Note, index: LinkIndex, scaled: bool = True,
                   gloss_len: int = 0, show_member: bool = False) -> str:
    meta = esc(member_label(note.member)) if show_member else ""
    return plate_row(note.url, note.title, index.inbound(note),
                     gloss=esc(clip(note.summary, gloss_len)) if gloss_len else "",
                     meta=meta, scaled=scaled)


def render_member_index(member: str, notes: list[Note], index: LinkIndex) -> str:
    groups: dict[str, list[Note]] = defaultdict(list)
    books: dict[str, list[Note]] = defaultdict(list)
    for note in notes:
        (books[note.book] if note.book else groups[note.folder]).append(note)

    sections = []
    if books:
        rows = []
        for book_id in sorted(books, key=lambda b: (book_title(b)[0].lower(), b)):
            title, author, year = book_title(book_id)
            rows.append(plate_row(f"/wiki/commons/reading/{slugify(book_id)}/", title,
                                  len(books[book_id]), unit=" notes", scaled=False,
                                  meta=esc(" · ".join(filter(None, [author, year])))))
        sections.append(section("Books read", plate(rows)))

    ordered = ([f for f in FOLDER_ORDER if f in groups]
               + sorted(f for f in groups if f not in FOLDER_ORDER))
    for folder in ordered:
        items = sorted(groups[folder], key=lambda n: (-index.inbound(n), n.title.lower(), n.rel))
        rows = "\n".join(note_plate_row(n, index, gloss_len=180) for n in items)
        sections.append(section(folder_label(folder), plate([rows]),
                                aside=f"{len(items)}"))

    blurb = MEMBER_BLURBS.get(member, "")
    total_in = sum(index.inbound(n) for n in notes)
    body = "\n".join(filter(None, [
        breadcrumb([("/wiki/", "Wiki"), ("", member_label(member))]),
        '  <p class="eyebrow">Contributor</p>',
        f"  <h1>{esc(member_label(member))}</h1>",
        f'  <p class="lede">{blurb}</p>' if blurb else "",
        figure_band([(str(len(notes)), "notes"), (str(total_in), "inbound links"),
                     (str(len(books)), "books")]),
        '  <p class="lede small">Ranked by how much the rest of the corpus leans on each note. '
        f'Source files live in <code>raw-notes/{esc(member)}/</code>.</p>',
        *sections,
    ]))
    return shell(member_label(member), body,
                 description=f"Working notes by {member_label(member)} in the World Machines wiki.")


def render_book_index(book_id: str, notes: list[Note], index: LinkIndex) -> str:
    title, author, year = book_title(book_id)
    # Reading order carries the meaning here, so the figures do not scale the
    # type — the sequence is the structure, not the ranking.
    rows = [note_plate_row(n, index, scaled=False, gloss_len=190)
            for n in sorted(notes, key=lambda n: n.rel)]
    meta = " · ".join(filter(None, [author, year]))
    body = "\n".join(filter(None, [
        breadcrumb([("/wiki/", "Wiki"), ("/wiki/commons/", "Commons"), ("", title)]),
        '  <p class="eyebrow">Book</p>',
        f"  <h1>{esc(title)}</h1>",
        f'  <p class="lede small">{esc(meta)}{" · " if meta else ""}'
        f'source id <code>{esc(book_id)}</code></p>',
        "  <p class=\"lede\">Section-by-section reading notes produced by the club's ingestion "
        "pipeline and reviewed by a curator. The book's own text is never stored in the repo — "
        "these are notes <em>about</em> it, in reading order. The figure on each row is how "
        "many other notes link to it.</p>",
        section("In reading order", plate(rows), aside=f"{len(notes)} notes"),
    ]))
    return shell(title, body, description=f"Club reading notes on {title}.")


ALPHABET = "ABCDEFGHIJKLMNOPQRSTUVWXYZ"


def letter_of(title: str) -> str:
    for ch in slugify(title):
        if ch.isalpha():
            return ch.upper()
        if ch.isdigit():
            return "#"
    return "#"


def render_all_notes(notes: list[Note], index: LinkIndex) -> str:
    groups: dict[str, list[Note]] = defaultdict(list)
    for note in notes:
        groups[letter_of(note.title)].append(note)

    jump = "".join(
        f'<a href="#letter-{ch}">{ch}</a>' if ch in groups
        else f'<span class="jump-off">{ch}</span>'
        for ch in ["#"] + list(ALPHABET)
    )

    blocks = []
    for letter in ["#"] + list(ALPHABET):
        items = groups.get(letter)
        if not items:
            continue
        rows = "\n".join(
            f'      <li class="az-row" data-search="{esc((n.title + " " + member_label(n.member)).lower())}">'
            f'<a href="{esc(n.url)}">{esc(n.title)}</a>'
            f'<span class="az-where">{esc(member_label(n.member))}</span>'
            f'<span class="az-figure">{index.inbound(n)}</span></li>'
            for n in sorted(items, key=lambda n: (n.title.lower(), n.rel))
        )
        anchor = f"letter-{letter}" if letter != "#" else "letter-#"
        blocks.append(
            f'  <section class="az-block" id="{esc(anchor)}">\n'
            f'    <h2 class="az-letter">{esc(letter)}</h2>\n'
            f'    <ul class="az-list">\n{rows}\n    </ul>\n  </section>'
        )

    body = f'''{breadcrumb([("/wiki/", "Wiki"), ("", "A–Z")])}
  <p class="eyebrow">Every note, by title</p>
  <h1>A–Z</h1>
  <p class="lede small">The flat index. <span id="az-count">{len(notes)}</span> of {len(notes)} notes
  shown — the figure on the right is how many notes link to each one.</p>
  <input id="az-filter" type="search" placeholder="Filter by title or contributor" autocomplete="off" spellcheck="false">
  <nav class="az-jump" aria-label="Jump to letter">{jump}</nav>
{chr(10).join(blocks)}
'''
    return shell("A–Z", body, active="/wiki/all",
                 description="Every published note in the World Machines wiki, A to Z.")


# ─── Special pages ───────────────────────────────────────────────────────────


def render_hubs(notes: list[Note], index: LinkIndex) -> str:
    ranked = sorted(notes, key=lambda n: (-index.inbound(n), n.title.lower(), n.rel))
    ranked = [n for n in ranked if index.inbound(n) > 0]
    rows = [note_plate_row(n, index, gloss_len=200, show_member=True) for n in ranked[:150]]
    body = f'''{breadcrumb([("/wiki/", "Wiki"), ("", "Most linked")])}
  <p class="eyebrow">What the corpus leans on</p>
  <h1>Most linked</h1>
  <p class="lede">Nobody decided these were the important notes. They are the notes
  the rest of the writing keeps reaching for, ranked by how many other notes link
  to them. The type grows with the count, so the club's centre of gravity is
  visible before you read a word.</p>
{section("Ranked by inbound links", plate(rows), aside=f"top {len(rows)} of {len(ranked)}")}
'''
    return shell("Most linked", body, active="/wiki/hubs",
                 description="The World Machines notes the rest of the corpus links to most.")


def render_orphans(notes: list[Note], index: LinkIndex) -> str:
    orphans = sorted((n for n in notes if index.inbound(n) == 0),
                     key=lambda n: (n.member, n.title.lower(), n.rel))
    by_member: dict[str, list[Note]] = defaultdict(list)
    for note in orphans:
        by_member[note.member].append(note)
    blocks = []
    for member in sorted(by_member):
        rows = [plate_row(n.url, n.title, index.outbound(n), unit=" out",
                          gloss=esc(clip(n.summary, 170)), scaled=False)
                for n in by_member[member]]
        blocks.append(section(member_label(member), plate(rows),
                              aside=f"{len(by_member[member])}"))
    body = f'''{breadcrumb([("/wiki/", "Wiki"), ("/wiki/special", "Special"), ("", "Orphans")])}
  <p class="eyebrow">Written, but never linked to</p>
  <h1>Orphans</h1>
  <p class="lede">{len(orphans)} notes that nothing else points at. An orphan is not
  a bad note — it is usually a good one nobody has connected yet. Linking to it
  from a note that belongs near it is the cheapest useful edit in the wiki. The
  figure is how many links each one makes outward.</p>
{chr(10).join(blocks) if blocks else '  <p class="empty-state">No orphans. Every note is linked from somewhere.</p>'}
'''
    return shell("Orphans", body, active="/wiki/special",
                 description="World Machines notes that no other note links to.")


def render_loose_links(index: LinkIndex) -> str:
    rows = []
    for target in sorted(index.loose, key=lambda t: (-len(index.loose_sources[t]), t)):
        dest = index.loose[target]
        sources = index.loose_sources[target]
        rows.append(
            f'      <li class="loose-row">\n'
            f'        <code class="loose-written">[[{esc(target)}]]</code>\n'
            f'        <span class="loose-arrow" aria-hidden="true">→</span>\n'
            f'        <a class="loose-dest" href="{esc(dest.url)}">{esc(dest.note_id)}</a>\n'
            f'        <span class="loose-count">{len(sources)} note{"" if len(sources) == 1 else "s"}</span>\n'
            f"      </li>"
        )
    body = f'''{breadcrumb([("/wiki/", "Wiki"), ("/wiki/special", "Special"), ("", "Loose links")])}
  <p class="eyebrow">Links the wiki repaired on the way through</p>
  <h1>Loose links</h1>
  <p class="lede">Wiki-links resolve on the exact, case-sensitive filename stem —
  the same rule the knowledge lake uses. These {len(index.loose)} were written a
  different way and would have been dead ends, so the wiki matched them on the
  normalised name and sent the reader to the right page anyway.</p>
  <p class="lede small">They still read as ordinary links, because a reader should
  not have to care. An editor should: rewriting each one at source in
  <code>raw-notes/</code> makes the published graph and the lake's graph agree.</p>
{section("Written one way, resolved another",
         f'    <ul class="loose-list">\n{chr(10).join(rows)}\n    </ul>' if rows
         else '    <p class="empty-state">Every link matches a filename exactly.</p>',
         aside=f"{index.loose_hits} occurrences")}
'''
    return shell("Loose links", body, active="/wiki/special",
                 description="Wiki-links that only resolve after name normalisation.")


def render_changes(notes: list[Note], commits: list[dict], limit: int = 80) -> str:
    by_path = {f"raw-notes/{n.rel}": n for n in notes}
    rows = []
    for commit in commits:
        touched = [by_path[f] for f in commit["files"] if f in by_path]
        if not touched:
            continue
        shown = touched[:8]
        links = ", ".join(f'<a href="{esc(n.url)}">{esc(n.title)}</a>' for n in shown)
        if len(touched) > len(shown):
            links += f' <span class="muted">+{len(touched) - len(shown)} more</span>'
        rows.append(
            f'      <li class="change">\n'
            f'        <div class="change-meta">{esc(fmt_date(commit["date"]))} · {esc(commit["author"])} · '
            f'<a href="{GITHUB_COMMIT}{esc(commit["sha"])}">{esc(commit["sha"][:7])}</a> · '
            f'{len(touched)} note{"" if len(touched) == 1 else "s"}</div>\n'
            f'        <div class="change-subject">{esc(commit["subject"])}</div>\n'
            f'        <div class="change-notes">{links}</div>\n'
            f"      </li>"
        )
        if len(rows) >= limit:
            break
    body = f'''{breadcrumb([("/wiki/", "Wiki"), ("/wiki/special", "Special"), ("", "Recent changes")])}
  <p class="eyebrow">What the club has been writing</p>
  <h1>Recent changes</h1>
  <p class="lede">Every commit that touched a published note, newest first, straight
  from the repository history.</p>
{section("Commits", f'    <ul class="changes">\n{chr(10).join(rows)}\n    </ul>' if rows
         else '    <p class="empty-state">No git history available.</p>',
         aside=f"latest {len(rows)}")}
'''
    return shell("Recent changes", body, active="/wiki/special",
                 description="Recent changes to the World Machines wiki.")


def render_special(notes: list[Note], glossary: list[Note], index: LinkIndex,
                   books: dict, commits: list[dict]) -> str:
    orphans = sum(1 for n in notes if index.inbound(n) == 0)
    wanted = index.wanted_groups()
    entries = [
        ("/wiki/hubs", "Most linked",
         "Notes ranked by how many others point at them.",
         f"{sum(1 for n in notes if index.inbound(n) > 0)} linked"),
        ("/wiki/wanted/", "Wanted pages",
         "Titles the writing keeps naming that no note answers to yet.",
         f"{len(wanted)} wanted"),
        ("/wiki/orphans", "Orphans",
         "Notes nothing links to — good writing waiting to be connected.",
         f"{orphans} orphans"),
        ("/wiki/loose-links", "Loose links",
         "Links that only resolve after normalising the name. Fixable at source.",
         f"{len(index.loose)} links"),
        ("/wiki/changes", "Recent changes",
         "Every commit that touched a published note.",
         f"{len(commits)} commits"),
        ("/wiki/topics/", "Topics",
         "Tags shared by two or more notes, each with its own page.",
         f"{len(index.topics)} topics"),
        ("/wiki/all", "A–Z",
         "The flat index of every note by title.",
         f"{len(notes)} notes"),
    ]
    rows = "\n".join(
        f'      <li class="special-row">\n'
        f'        <a href="{esc(href)}">{esc(label)}</a>\n'
        f'        <span class="special-figure">{esc(figure)}</span>\n'
        f'        <p class="special-gloss">{esc(gloss)}</p>\n      </li>'
        for href, label, gloss, figure in entries
    )
    body = f'''{breadcrumb([("/wiki/", "Wiki"), ("", "Special")])}
  <p class="eyebrow">Maintenance desk</p>
  <h1>Special pages</h1>
  <p class="lede">Views of the wiki as a structure rather than as a text. Most of
  them double as a to-do list: an orphan wants linking, a wanted page wants
  writing, a loose link wants tightening.</p>
{figure_band([(str(len(notes)), "notes"), (str(len(glossary)), "defined"),
              (str(index.resolved_hits), "links resolved"), (str(len(wanted)), "pages wanted"),
              (str(orphans), "orphans"), (str(len(books)), "books")])}
{section("Views", f'    <ul class="special-list">\n{rows}\n    </ul>')}
'''
    return shell("Special pages", body, active="/wiki/special",
                 description="Structural views of the World Machines wiki.")


# ─── Wanted pages ────────────────────────────────────────────────────────────


def wanted_template(name: str) -> str:
    return (f"---\nsummary: \"One sentence a newcomer could read and not be lost.\"\n"
            f"tags: []\nlast_updated: \n---\n\n# {name}\n\n"
            "Why this note exists: several notes already link to this title.\n")


def render_wanted_page(group: dict, index: LinkIndex) -> str:
    name = group["name"]
    sources = group["sources"]
    spellings = [n for n in group["names"] if n != name]
    rows = [plate_row(n.url, n.title, index.inbound(n), gloss=esc(clip(n.summary, 190)),
                      meta=esc(member_label(n.member)), scaled=False) for n in sources]
    new_url = (f"{GITHUB_NEW}?filename={quote(group['slug'] + '.md')}"
               f"&value={quote(wanted_template(name))}")
    aka = ""
    if spellings:
        aka = ('  <p class="lede small">Also written ' +
               ", ".join(f"<code>[[{esc(s)}]]</code>" for s in spellings) + ".</p>")
    body = "\n".join(filter(None, [
        breadcrumb([("/wiki/", "Wiki"), ("/wiki/wanted/", "Wanted"), ("", name)]),
        '  <p class="eyebrow wanted-eyebrow">This page does not exist yet</p>',
        f"  <h1>{esc(name)}</h1>",
        f'  <p class="lede">{len(sources)} note{"" if len(sources) == 1 else "s"} '
        f'link{"s" if len(sources) == 1 else ""} to <code>[[{esc(name)}]]</code>, and nothing in '
        "<code>raw-notes/</code> answers to that name. Whoever writes it gets "
        f"{len(sources)} inbound link{'' if len(sources) == 1 else 's'} the moment they commit.</p>",
        aka,
        f'  <p class="write-cta"><a class="write-button" href="{esc(new_url)}">'
        f"Start this note on GitHub</a><span>Creates "
        f"<code>raw-notes/commons/concepts/{esc(group['slug'])}.md</code> — move it "
        "into your own folder if it is yours.</span></p>",
        section("Notes asking for it", plate(rows), aside=f"{group['hits']} links"),
    ]))
    return shell(f"{name} — wanted", body, active="/wiki/wanted/",
                 description=f"{len(sources)} World Machines notes link to “{name}”, "
                             "which has not been written yet.")


def render_wanted_index(groups: list[dict], index: LinkIndex) -> str:
    rows = [plate_row(wanted_url(g["slug"]), g["name"], len(g["sources"]),
                      unit=" notes", wanted=True,
                      meta=esc(", ".join(member_label(m) for m in
                                         sorted({s.member for s in g["sources"]}))))
            for g in groups]
    body = f'''{breadcrumb([("/wiki/", "Wiki"), ("", "Wanted")])}
  <p class="eyebrow wanted-eyebrow">Named, not written</p>
  <h1>Wanted pages</h1>
  <p class="lede">Every title the club has put in double brackets that no note
  answers to. This is the most honest to-do list the project has: each one is a
  page somebody already assumed existed, ranked by how many notes are waiting for
  it. Writing one is the highest-leverage note you can add, because its inbound
  links are there before you start.</p>
{section("Ranked by how many notes want them", plate(rows, extra="plate-wanted-list"),
         aside=f"{len(groups)} wanted")}
'''
    return shell("Wanted pages", body, active="/wiki/wanted/",
                 description="Titles the World Machines corpus links to but has not written.")


# ─── Topic pages ─────────────────────────────────────────────────────────────


def render_topic_page(slug: str, label: str, notes: list[Note], index: LinkIndex) -> str:
    ranked = sorted(notes, key=lambda n: (-index.inbound(n), n.title.lower(), n.rel))
    rows = [note_plate_row(n, index, gloss_len=190, show_member=True) for n in ranked]
    members = sorted({n.member for n in notes})
    body = f'''{breadcrumb([("/wiki/", "Wiki"), ("/wiki/topics/", "Topics"), ("", label)])}
  <p class="eyebrow">Topic</p>
  <h1>{esc(label)}</h1>
  <p class="lede small">{len(notes)} notes tagged <code>{esc(label)}</code> ·
  {esc(", ".join(member_label(m) for m in members))}</p>
{section("Tagged notes", plate(rows), aside=f"{len(notes)}")}
'''
    return shell(f"{label} — topic", body, active="/wiki/topics/",
                 description=f"World Machines notes tagged {label}.")


def render_topics_index(index: LinkIndex) -> str:
    ranked = sorted(index.topics.items(),
                    key=lambda kv: (-len(kv[1]), index.topic_labels[kv[0]]))
    rows = [plate_row(topic_url(slug), index.topic_labels[slug], len(notes),
                      unit=" notes", scaled=False)
            for slug, notes in ranked]
    body = f'''{breadcrumb([("/wiki/", "Wiki"), ("", "Topics")])}
  <p class="eyebrow">The keywords the notes carry</p>
  <h1>Topics</h1>
  <p class="lede">Tags out of the notes' own frontmatter. A tag becomes a topic
  page once at least {TOPIC_MIN_NOTES} notes share it — below that it is one
  note's keyword, not a place to browse. Topics cut across contributors and
  books, which is what makes them worth following.</p>
{section("Every shared tag", plate(rows, extra="plate-dense"), aside=f"{len(ranked)} topics")}
'''
    return shell("Topics", body, active="/wiki/topics/",
                 description="Topics shared across the World Machines notes.")


# ─── Search ──────────────────────────────────────────────────────────────────


def render_search() -> str:
    body = f'''{breadcrumb([("/wiki/", "Wiki"), ("", "Search")])}
  <p class="eyebrow">Titles, summaries and topics</p>
  <h1>Search</h1>
  <form class="search-page-form" action="/wiki/search" method="get" role="search">
    <label class="visually-hidden" for="search-q">Search the wiki</label>
    <input id="search-q" name="q" type="search" placeholder="Search the wiki" autocomplete="off"
           spellcheck="false" autofocus>
    <button type="submit">Search</button>
  </form>
  <p class="lede small" id="search-status">Type to search every note, definition and topic.</p>
  <div id="search-results"></div>
  <noscript><p class="lede">Search needs JavaScript. The
  <a href="/wiki/all">A–Z index</a> lists every note without it.</p></noscript>
'''
    return shell("Search", body, description="Search the World Machines wiki.")


def render_home(notes: list[Note], glossary: list[Note], index: LinkIndex,
                commits: list[dict]) -> str:
    """The front door.

    A wiki's home page is not a table of contents for a filesystem. This one is
    organised around a claim the corpus actually makes about itself: there are
    three vocabularies here — the terms the club has agreed to define, the
    concepts it leans on whether or not anyone defined them, and the titles it
    keeps naming but has never written. The gap between the three is the honest
    state of the project, so it is the first thing on the page.
    """
    by_member: dict[str, list[Note]] = defaultdict(list)
    books: dict[str, list[Note]] = defaultdict(list)
    for note in notes:
        by_member[note.member].append(note)
        if note.book:
            books[note.book].append(note)

    # 1. Defined — the deliberate vocabulary.
    terms = sorted(glossary, key=lambda n: (n.term.lower(), n.rel))
    defined = (f'    <ul class="term-list">\n'
               + "\n".join(glossary_card(n, index) for n in terms) + "\n    </ul>"
               ) if terms else '    <p class="empty-state">No terms defined yet.</p>'

    # 2. Load-bearing — the emergent vocabulary, measured not asserted.
    ranked = sorted((n for n in notes if index.inbound(n) > 0),
                    key=lambda n: (-index.inbound(n), n.title.lower(), n.rel))
    hub_rows = [note_plate_row(n, index, show_member=True) for n in ranked[:HOME_HUBS]]

    # 3. Wanted — the vocabulary with nothing behind it.
    wanted = index.wanted_groups()
    wanted_rows = [plate_row(wanted_url(g["slug"]), g["name"], len(g["sources"]),
                             unit=" notes", wanted=True) for g in wanted[:HOME_WANTED]]

    by_path = {f"raw-notes/{n.rel}": n for n in notes}
    recent = []
    for commit in commits:
        touched = [by_path[f] for f in commit["files"] if f in by_path]
        if not touched:
            continue
        shown = touched[:4]
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
        if len(recent) >= HOME_CHANGES:
            break

    book_rows = []
    for book_id in sorted(books, key=lambda b: (-len(books[b]), book_title(b)[0].lower(), b)):
        title, author, year = book_title(book_id)
        book_rows.append(plate_row(f"/wiki/commons/reading/{slugify(book_id)}/", title,
                                   len(books[book_id]), unit=" notes", scaled=False,
                                   meta=esc(" · ".join(filter(None, [author, year])))))

    member_rows = []
    for member in sorted(by_member, key=lambda m: (m == "commons", member_label(m).lower())):
        items = by_member[member]
        folders = sorted({"Reading notes" if n.book else folder_label(n.folder) for n in items})
        member_rows.append(plate_row(f"/wiki/{slugify(member)}/", member_label(member),
                                     len(items), unit=" notes", scaled=False,
                                     meta=esc(" · ".join(folders))))

    stamp = (f"generated from raw-notes at {commits[0]['sha'][:12]} ({commits[0]['date']})"
             if commits else "generated from raw-notes")
    body = f'''  <p class="eyebrow">A book club writing its own theory, in the open</p>
  <h1 class="home-title">The wiki</h1>
  <p class="lede home-lede">{len(notes)} working notes held together by
  {index.resolved_hits} links. Nothing here is finished — this is the layer where
  the thinking happens, and the fastest way through it is to follow a concept
  sideways rather than read a folder top to bottom.</p>
{figure_band([(str(len(glossary)), "terms defined"),
              (str(len(ranked)), "notes linked to"),
              (str(len(wanted)), "pages wanted"),
              (str(len(index.topics)), "shared topics"),
              (str(len(books)), "books read")])}
{section("Defined", defined,
         aside='<a href="/wiki/glossary/">the glossary →</a>',
         note="Terms the club has argued about on purpose. Each carries a status and "
              "gathers every note that uses it.")}
{section("Load-bearing", plate(hub_rows),
         aside='<a href="/wiki/hubs">all →</a>',
         note="Nobody nominated these. They are the notes the rest of the writing keeps "
              "reaching for, ranked by inbound links — the club's centre of gravity, measured.")}
{section("Wanted", plate(wanted_rows, extra="plate-wanted-list"),
         aside='<a href="/wiki/wanted/">all →</a>',
         note="Titles the notes keep linking to that nobody has written. Whoever writes one "
              "inherits its inbound links on the first commit.")}
{section("Open threads", f'    <ul class="changes">\n{chr(10).join(recent)}\n    </ul>' if recent
         else '    <p class="empty-state">No git history available.</p>',
         aside='<a href="/wiki/changes">all changes →</a>')}
{section("On the table", plate(book_rows),
         aside='<a href="/wiki/topics/">browse topics →</a>',
         note="Books the club reads together. Notes are written about them section by "
              "section; the source text never enters the repository.")}
{section("Who wrote it", plate(member_rows, extra="plate-dense"),
         aside='<a href="/wiki/all">A–Z →</a>',
         note="The folder view. Useful when you know whose note you are after, less useful "
              "than following a link when you do not.")}
  <p class="note-foot">The <a href="/oracle">Oracle</a> answers questions against
  this same corpus; the wiki is the version you can read, link and edit. Source
  notes live in <code>raw-notes/</code> — every page links to its own file on GitHub.</p>
'''
    return shell("Wiki", body, active="/wiki/", stamp=stamp,
                 description="The World Machines book club's working notes, published as a wiki.")


# ─── Stylesheet ──────────────────────────────────────────────────────────────

WIKI_CSS = """/* Wiki styles. Loaded after /style.css, which supplies the site tokens
   (--bg, --text, --muted, --border, --link) and the header/nav chrome.

   The wiki is a different room in the same building. It keeps the site's paper,
   ink and navy, and adds three things of its own: a wider measure with a rail
   for lateral movement, a display face the rest of the site never uses, and one
   red reserved exclusively for pages that do not exist yet. */

:root {
  --wiki-width: 1060px;
  --wiki-measure: 660px;
  --wiki-rail: 268px;

  /* Ink and paper, one step off the site's own */
  --wiki-rule:    #d8d3ca;   /* hairlines, leader dots */
  --wiki-plate:   #f2efe9;   /* the index-plate ground */
  --wiki-figure:  #6f695e;   /* warm grey for numbers, so they sit behind names */
  --wiki-prose:   #26251f;

  /* The only red in the wiki. It means: this page has not been written. */
  --wiki-wanted:      #8f2c22;
  --wiki-wanted-tint: #f6ece9;

  /* Display: a Venetian old-style with a wider aperture than the body Georgia.
     Every fallback in the stack is a real old-style, so the pairing survives. */
  --wiki-display: 'Iowan Old Style', 'Palatino Linotype', Palatino, 'Book Antiqua',
                  'URW Palladio L', Georgia, serif;
  /* Figures are data, so they are set in a fixed pitch and aligned in a column. */
  --wiki-mono: ui-monospace, 'SF Mono', SFMono-Regular, Menlo, Consolas,
               'Liberation Mono', monospace;
  --wiki-ui: system-ui, -apple-system, 'Segoe UI', sans-serif;
}

.visually-hidden {
  position: absolute; width: 1px; height: 1px; overflow: hidden;
  clip: rect(0 0 0 0); clip-path: inset(50%); white-space: nowrap;
}

/* The wiki widens the whole chrome, not just the content, so the room changes
   at the door rather than halfway down the page. */
body.wiki-page header,
body.wiki-page .sitenav { max-width: var(--wiki-width); }

main.wiki { max-width: var(--wiki-width); margin: 2.2rem auto 6rem; }
main.wiki > h1,
main.wiki > .eyebrow,
main.wiki > .lede,
main.wiki > .note-foot,
main.wiki > .breadcrumb,
main.wiki > form { max-width: 46rem; }

:where(main.wiki) :focus-visible {
  outline: 2px solid var(--link);
  outline-offset: 2px;
  border-radius: 1px;
}

/* ─── Wiki toolbar ─────────────────────────────────────────── */

.wikinav {
  max-width: var(--wiki-width);
  margin: 0 auto;
  padding: 0.5rem 0 0.55rem;
  border-bottom: 1px solid var(--border);
  display: flex;
  align-items: center;
  gap: 0.6rem 1.15rem;
  flex-wrap: wrap;
  font-family: var(--wiki-ui);
  font-size: 0.75rem;
}
.wikinav-links { display: flex; gap: 1.15rem; flex-wrap: wrap; }
.wikinav a { color: var(--muted); }
.wikinav a:hover { color: var(--text); text-decoration: none; }
.wikinav a[aria-current="page"] { color: var(--text); font-weight: 600; }

.wikisearch { position: relative; margin-left: auto; flex: 0 1 15rem; min-width: 11rem; }
.wikisearch input {
  width: 100%;
  font-family: var(--wiki-ui);
  font-size: 0.75rem;
  color: var(--text);
  padding: 0.3rem 0.55rem;
  border: 1px solid var(--wiki-rule);
  border-radius: 2px;
  background: #fff;
}
.wikisearch input::placeholder { color: #9a948a; }
.wikisearch-results {
  position: absolute;
  z-index: 20;
  top: calc(100% + 4px);
  right: 0;
  width: min(30rem, 84vw);
  max-height: 26rem;
  overflow-y: auto;
  background: #fff;
  border: 1px solid var(--wiki-rule);
  border-radius: 2px;
  box-shadow: 0 6px 22px rgba(28, 28, 28, 0.09);
}
.wikisearch-results a {
  display: block;
  padding: 0.45rem 0.6rem;
  border-bottom: 1px solid #efece6;
  color: var(--text);
}
.wikisearch-results a:last-child { border-bottom: none; }
.wikisearch-results a:hover,
.wikisearch-results a.is-active { background: var(--wiki-plate); text-decoration: none; }
.wikisearch-results .r-title { font-family: var(--wiki-display); font-size: 0.92rem; }
.wikisearch-results .r-where {
  font-family: var(--wiki-mono);
  font-size: 0.62rem;
  color: var(--wiki-figure);
  text-transform: uppercase;
  letter-spacing: 0.04em;
  margin-left: 0.4rem;
}
.wikisearch-results .r-gloss {
  font-family: var(--wiki-ui);
  font-size: 0.72rem;
  color: var(--muted);
  line-height: 1.45;
  margin-top: 0.1rem;
}
.wikisearch-results .r-empty {
  padding: 0.6rem;
  font-family: var(--wiki-ui);
  font-size: 0.75rem;
  color: var(--muted);
}

/* ─── Headings and orientation ─────────────────────────────── */

.breadcrumb {
  font-family: var(--wiki-ui);
  font-size: 0.72rem;
  color: var(--muted);
  margin-bottom: 1.2rem;
}
.breadcrumb a { color: var(--muted); }
.breadcrumb a:hover { color: var(--text); }
.breadcrumb b { color: var(--wiki-rule); font-weight: normal; margin: 0 0.2rem; }

.eyebrow {
  font-family: var(--wiki-mono);
  font-size: 0.66rem;
  text-transform: uppercase;
  letter-spacing: 0.12em;
  color: var(--wiki-figure);
  margin-bottom: 0.5rem;
}
.wanted-eyebrow { color: var(--wiki-wanted); }

main.wiki h1 {
  font-family: var(--wiki-display);
  font-size: 2rem;
  font-weight: normal;
  line-height: 1.16;
  letter-spacing: -0.015em;
  margin-bottom: 0.7rem;
}
main.wiki .home-title { font-size: 2.9rem; letter-spacing: -0.025em; }

main.wiki .lede {
  font-size: 0.95rem;
  line-height: 1.72;
  color: var(--wiki-prose);
  margin-bottom: 1rem;
}
main.wiki .home-lede { font-size: 1.06rem; line-height: 1.65; }
main.wiki .lede.small {
  font-family: var(--wiki-ui);
  font-size: 0.78rem;
  line-height: 1.6;
  color: var(--muted);
}
.muted { color: var(--muted); }
.empty-state { font-family: var(--wiki-ui); font-size: 0.82rem; color: var(--muted); }

/* ─── Figure band ──────────────────────────────────────────── */

.figure-band {
  display: flex;
  flex-wrap: wrap;
  gap: 0 2.6rem;
  border-top: 1px solid var(--text);
  border-bottom: 1px solid var(--wiki-rule);
  padding: 0.75rem 0 0.7rem;
  margin: 1.6rem 0 2.6rem;
}
.band-cell { display: flex; align-items: baseline; gap: 0.4rem; }
.band-cell b {
  font-family: var(--wiki-mono);
  font-size: 1.05rem;
  font-weight: 600;
  font-variant-numeric: tabular-nums;
  color: var(--text);
}
.band-cell span {
  font-family: var(--wiki-ui);
  font-size: 0.72rem;
  color: var(--muted);
}

/* ─── Registers (section headings) ─────────────────────────── */

main.wiki section { margin-bottom: 3rem; }
main.wiki section:last-of-type { margin-bottom: 1.5rem; }

.register {
  display: flex;
  align-items: baseline;
  justify-content: space-between;
  gap: 1rem;
  font-family: var(--wiki-mono);
  font-size: 0.68rem;
  font-weight: 600;
  text-transform: uppercase;
  letter-spacing: 0.14em;
  color: var(--text);
  padding-bottom: 0.4rem;
  border-bottom: 1px solid var(--text);
  margin-bottom: 0.9rem;
}
.section-aside {
  font-family: var(--wiki-ui);
  font-size: 0.7rem;
  font-weight: normal;
  letter-spacing: 0;
  text-transform: none;
  color: var(--muted);
  white-space: nowrap;
}
.section-aside a { color: var(--link); }
.section-note {
  font-family: var(--wiki-ui);
  font-size: 0.77rem;
  line-height: 1.6;
  color: var(--muted);
  max-width: 42rem;
  margin: -0.3rem 0 1rem;
}

/* ─── The index plate ──────────────────────────────────────────
   name ······················ figure
   One row is one claim: what it is called, and how much of the corpus
   leans on it. Type size steps with the figure, so a column of rows
   reads as a skyline before you read a word. */

.plate { list-style: none; }
.plate-row {
  padding: 0.42rem 0;
  border-bottom: 1px solid #ebe8e2;
}
.plate-row:last-child { border-bottom: none; }

.plate-line { display: flex; align-items: baseline; gap: 0.5rem; }
.plate-name {
  font-family: var(--wiki-display);
  color: var(--text);
  line-height: 1.25;
  flex: 0 1 auto;
}
.plate-name:hover { color: var(--link); text-decoration: none; }
.plate-leader {
  flex: 1 1 auto;
  min-width: 1.25rem;
  align-self: center;
  border-bottom: 1px dotted var(--wiki-rule);
  transform: translateY(0.12em);
}
.plate-figure {
  flex: 0 0 auto;
  font-family: var(--wiki-mono);
  font-size: 0.78rem;
  font-variant-numeric: tabular-nums;
  color: var(--wiki-figure);
}
.plate-unit { font-size: 0.85em; color: var(--muted); }
.plate-meta {
  display: block;
  font-family: var(--wiki-ui);
  font-size: 0.7rem;
  color: var(--muted);
  margin-top: 0.06rem;
}
.plate-gloss {
  font-family: var(--wiki-ui);
  font-size: 0.775rem;
  line-height: 1.55;
  color: var(--muted);
  max-width: 44rem;
  margin-top: 0.18rem;
}

/* Magnitude classes: the one place in the wiki where size means something. */
.mag-1 .plate-name { font-size: 1rem; }
.mag-2 .plate-name { font-size: 1.14rem; }
.mag-3 .plate-name { font-size: 1.34rem; }
.mag-4 .plate-name { font-size: 1.62rem; letter-spacing: -0.012em; }
.mag-3, .mag-4 { padding: 0.52rem 0; }

.plate-dense .plate-row { padding: 0.3rem 0; }
.plate-dense .plate-name { font-size: 0.95rem; }

/* Wanted rows: the red is functional, never decorative. */
.plate-wanted .plate-name { color: var(--wiki-wanted); }
.plate-wanted .plate-name:hover { color: var(--wiki-wanted); text-decoration: underline; }
.plate-wanted .plate-figure { color: var(--wiki-wanted); }
.plate-wanted-list .plate-leader { border-bottom-color: #e3cec9; }

/* ─── Note page: prose plus a rail ─────────────────────────── */

.spread {
  display: grid;
  grid-template-columns: minmax(0, var(--wiki-measure)) var(--wiki-rail);
  gap: 3.2rem;
  align-items: start;
}
@media (max-width: 960px) {
  .spread { grid-template-columns: minmax(0, 1fr); gap: 2.4rem; }
}

.note { min-width: 0; }
.note h1 { margin-bottom: 0.55rem; }

.eyebrow + h1 { margin-top: 0; }

.note-byline {
  font-family: var(--wiki-ui);
  font-size: 0.73rem;
  color: var(--muted);
  padding-bottom: 0.8rem;
  border-bottom: 1px solid var(--wiki-rule);
  margin-bottom: 1.3rem;
}
.note-byline a { color: var(--muted); text-decoration: underline; text-decoration-color: var(--wiki-rule); }
.note-byline a:hover { color: var(--text); }

.note-summary {
  font-family: var(--wiki-display);
  font-size: 1.06rem;
  line-height: 1.62;
  color: var(--wiki-prose);
  border-left: 2px solid var(--text);
  padding: 0.05rem 0 0.05rem 1rem;
  margin-bottom: 1.5rem;
}

/* ─── The rail ─────────────────────────────────────────────── */

.rail {
  font-family: var(--wiki-ui);
  min-width: 0;
  position: sticky;
  top: 1.2rem;
  max-height: calc(100vh - 2.4rem);
  overflow-y: auto;
  overscroll-behavior: contain;
}
@media (max-width: 960px) {
  .rail {
    position: static;
    max-height: none;
    overflow: visible;
    border-top: 1px solid var(--text);
    padding-top: 1.4rem;
  }
}

.rail-block { margin-bottom: 1.7rem; }
.rail-block:last-child { margin-bottom: 0; }

.rail-label {
  display: flex;
  align-items: baseline;
  justify-content: space-between;
  gap: 0.5rem;
  font-family: var(--wiki-mono);
  font-size: 0.63rem;
  font-weight: 600;
  text-transform: uppercase;
  letter-spacing: 0.12em;
  color: var(--text);
  padding-bottom: 0.32rem;
  border-bottom: 1px solid var(--wiki-rule);
  margin-bottom: 0.55rem;
}
.rail-count { font-variant-numeric: tabular-nums; color: var(--wiki-figure); font-weight: normal; }

.rail-bearings {
  display: flex;
  gap: 1.4rem;
  flex-wrap: wrap;
  background: var(--wiki-plate);
  border: 1px solid var(--wiki-rule);
  padding: 0.6rem 0.75rem;
}
.bearing { display: flex; flex-direction: column; line-height: 1.2; }
.bearing b {
  font-family: var(--wiki-mono);
  font-size: 1rem;
  font-weight: 600;
  font-variant-numeric: tabular-nums;
}
.bearing span { font-size: 0.66rem; color: var(--muted); }

.rail-list { list-style: none; }
.rail-list li {
  display: flex;
  align-items: baseline;
  justify-content: space-between;
  gap: 0.5rem;
  padding: 0.24rem 0;
  font-size: 0.815rem;
  line-height: 1.4;
}
.rail-list a { color: var(--text); }
.rail-list a:hover { color: var(--link); text-decoration: none; }
.rail-where {
  flex: 0 0 auto;
  font-family: var(--wiki-mono);
  font-size: 0.63rem;
  color: var(--wiki-figure);
  font-variant-numeric: tabular-nums;
}
.rail-more { margin-top: 0.3rem; }
.rail-more summary {
  font-family: var(--wiki-mono);
  font-size: 0.66rem;
  color: var(--link);
  cursor: pointer;
  letter-spacing: 0.03em;
}
.rail-more summary:hover { color: var(--link-hover); }
.rail-more[open] summary { margin-bottom: 0.25rem; }

.rail-term {
  font-family: var(--wiki-display);
  font-size: 1.08rem;
  color: var(--text);
  margin-right: 0.35rem;
}
.rail-term:hover { color: var(--link); text-decoration: none; }
.rail-gloss { font-size: 0.755rem; line-height: 1.5; color: var(--muted); margin-top: 0.35rem; }
.rail-hint { font-size: 0.68rem; line-height: 1.45; color: var(--muted); margin-top: 0.35rem; }
.rail-empty { font-size: 0.76rem; color: var(--muted); line-height: 1.5; }

.rail-edges { list-style: none; }
.rail-edges li { padding: 0.2rem 0; font-size: 0.8rem; line-height: 1.4; }

/* ─── Prose ────────────────────────────────────────────────── */

.prose { font-size: 1rem; line-height: 1.78; color: var(--wiki-prose); }
.prose h1, .prose h2, .prose h3, .prose h4, .prose h5, .prose h6 {
  font-family: var(--wiki-display);
  font-weight: normal;
  line-height: 1.3;
  color: var(--text);
  margin: 2.1rem 0 0.6rem;
}
.prose h1 { font-size: 1.4rem; }
.prose h2 { font-size: 1.22rem; padding-top: 1.1rem; border-top: 1px solid var(--wiki-rule); }
.prose h3 { font-size: 1.08rem; }
.prose h4, .prose h5, .prose h6 { font-size: 0.96rem; font-weight: 600; font-family: inherit; }
.prose p { margin-bottom: 0.95rem; }
.prose ul, .prose ol { margin: 0 0 1rem 1.35rem; }
.prose li { margin-bottom: 0.38rem; }
.prose li > ul, .prose li > ol { margin-top: 0.38rem; margin-bottom: 0.38rem; }
.prose blockquote {
  border-left: 2px solid var(--wiki-rule);
  padding-left: 1rem;
  margin: 0 0 1rem;
  color: #43413a;
  font-style: italic;
}
.prose blockquote p:last-child { margin-bottom: 0; }
.prose hr { border: none; border-top: 1px solid var(--wiki-rule); margin: 1.9rem 0; }
.prose code {
  font-family: var(--wiki-mono);
  font-size: 0.83em;
  background: var(--wiki-plate);
  padding: 0.1em 0.3em;
  border-radius: 2px;
}
.prose pre {
  background: var(--wiki-plate);
  border: 1px solid var(--wiki-rule);
  border-radius: 2px;
  padding: 0.8rem 0.9rem;
  overflow-x: auto;
  margin-bottom: 1rem;
}
.prose pre code { background: none; padding: 0; font-size: 0.78rem; line-height: 1.55; }
.prose img { max-width: 100%; height: auto; }

.table-wrap { overflow-x: auto; margin-bottom: 1.2rem; }
.prose table { border-collapse: collapse; font-size: 0.85rem; min-width: 100%; }
.prose th, .prose td {
  border: 1px solid var(--wiki-rule);
  padding: 0.4rem 0.6rem;
  text-align: left;
  vertical-align: top;
}
.prose th { background: var(--wiki-plate); font-weight: 600; }

/* ─── Wiki links ───────────────────────────────────────────── */

.wikilink { border-bottom: 1px solid rgba(26, 76, 138, 0.28); }
.wikilink:hover { text-decoration: none; border-bottom-color: var(--link-hover); }
.wikilink-glossary { border-bottom-style: dotted; }

/* A red link is an invitation, not an error: it goes to a page that says who
   is asking for it and offers to start the note. */
.wikilink-wanted {
  color: var(--wiki-wanted);
  border-bottom: 1px dotted rgba(143, 44, 34, 0.5);
}
.wikilink-wanted:hover {
  color: #6f201a;
  background: var(--wiki-wanted-tint);
  text-decoration: none;
}

.note-history, .note-foot {
  font-family: var(--wiki-ui);
  font-size: 0.73rem;
  line-height: 1.6;
  color: var(--muted);
  margin-top: 1.6rem;
  padding-top: 0.9rem;
  border-top: 1px solid var(--wiki-rule);
}
.note-foot code { font-size: 0.95em; }

/* ─── Glossary cards ───────────────────────────────────────── */

.term-list { list-style: none; }
.term-card {
  padding: 0.95rem 0;
  border-bottom: 1px solid #ebe8e2;
}
.term-card:last-child { border-bottom: none; }
.term-head { display: flex; align-items: baseline; gap: 0.5rem; flex-wrap: wrap; }
.term-head a { font-family: var(--wiki-display); font-size: 1.4rem; color: var(--text); }
.term-head a:hover { color: var(--link); text-decoration: none; }
.term-head .muted { font-family: var(--wiki-ui); font-size: 0.72rem; }
.term-gloss {
  font-size: 0.9rem;
  line-height: 1.65;
  color: var(--wiki-prose);
  max-width: 44rem;
  margin-top: 0.3rem;
}
.term-meta {
  font-family: var(--wiki-mono);
  font-size: 0.66rem;
  color: var(--wiki-figure);
  margin-top: 0.35rem;
}

.status {
  font-family: var(--wiki-ui);
  font-size: 0.62rem;
  font-weight: 600;
  text-transform: uppercase;
  letter-spacing: 0.05em;
  padding: 0.1rem 0.38rem;
  border-radius: 2px;
  white-space: nowrap;
}
.status-seed       { background: #fff3cd; color: #7a5200; }
.status-developing { background: #dbeafe; color: #1e3a8a; }
.status-settled    { background: #d1fae5; color: #065f46; }

/* ─── A–Z ──────────────────────────────────────────────────── */

#az-filter, .search-page-form input {
  width: 100%;
  max-width: 30rem;
  font-family: var(--wiki-ui);
  font-size: 0.85rem;
  padding: 0.45rem 0.6rem;
  border: 1px solid var(--wiki-rule);
  border-radius: 2px;
  background: #fff;
  margin: 0.5rem 0 1rem;
}
.search-page-form { display: flex; gap: 0.5rem; align-items: flex-start; max-width: 36rem; }
.search-page-form button {
  font-family: var(--wiki-ui);
  font-size: 0.8rem;
  margin: 0.5rem 0 1rem;
  padding: 0.45rem 0.9rem;
  border: 1px solid var(--text);
  border-radius: 2px;
  background: var(--text);
  color: var(--bg);
  cursor: pointer;
}
.search-page-form button:hover { background: #333; }

.az-jump {
  display: flex;
  flex-wrap: wrap;
  gap: 0.1rem 0.42rem;
  font-family: var(--wiki-mono);
  font-size: 0.75rem;
  border-top: 1px solid var(--wiki-rule);
  border-bottom: 1px solid var(--wiki-rule);
  padding: 0.5rem 0;
  margin-bottom: 2rem;
  position: sticky;
  top: 0;
  background: var(--bg);
  z-index: 5;
}
.az-jump a { color: var(--link); }
.jump-off { color: #c9c4ba; }

.az-block { margin-bottom: 2rem; }
.az-letter {
  font-family: var(--wiki-display);
  font-size: 1.5rem;
  font-weight: normal;
  color: var(--wiki-figure);
  border-bottom: 1px solid var(--text);
  padding-bottom: 0.2rem;
  margin-bottom: 0.5rem;
}
.az-list { list-style: none; columns: 2; column-gap: 2.6rem; }
@media (max-width: 720px) { .az-list { columns: 1; } }
.az-row {
  display: flex;
  align-items: baseline;
  gap: 0.5rem;
  padding: 0.22rem 0;
  break-inside: avoid;
  font-size: 0.9rem;
}
.az-row a { color: var(--text); flex: 1 1 auto; }
.az-row a:hover { color: var(--link); text-decoration: none; }
.az-where { font-family: var(--wiki-ui); font-size: 0.68rem; color: var(--muted); }
.az-figure {
  font-family: var(--wiki-mono);
  font-size: 0.68rem;
  color: var(--wiki-figure);
  font-variant-numeric: tabular-nums;
  min-width: 1.6rem;
  text-align: right;
}

/* ─── Changes ──────────────────────────────────────────────── */

.changes { list-style: none; }
.changes .change { padding: 0.7rem 0; border-bottom: 1px solid #ebe8e2; }
.changes .change:last-child { border-bottom: none; }
.change-meta { font-family: var(--wiki-mono); font-size: 0.67rem; color: var(--wiki-figure); }
.change-subject { font-family: var(--wiki-display); font-size: 1.02rem; margin: 0.15rem 0 0.2rem; }
.change-notes { font-family: var(--wiki-ui); font-size: 0.765rem; line-height: 1.65; }

/* ─── Wanted page ──────────────────────────────────────────── */

.write-cta {
  display: flex;
  align-items: center;
  gap: 0.85rem;
  flex-wrap: wrap;
  background: var(--wiki-wanted-tint);
  border: 1px solid #e3cec9;
  padding: 0.85rem 1rem;
  margin: 1.4rem 0 2.4rem;
  max-width: 46rem;
}
.write-button {
  font-family: var(--wiki-ui);
  font-size: 0.8rem;
  font-weight: 600;
  background: var(--wiki-wanted);
  color: #fff;
  padding: 0.42rem 0.85rem;
  border-radius: 2px;
  white-space: nowrap;
}
.write-button:hover { background: #6f201a; color: #fff; text-decoration: none; }
.write-cta span {
  font-family: var(--wiki-ui);
  font-size: 0.72rem;
  line-height: 1.5;
  color: #6d5551;
  flex: 1 1 14rem;
}

/* ─── Special pages ────────────────────────────────────────── */

.special-list { list-style: none; }
.special-row { padding: 0.7rem 0; border-bottom: 1px solid #ebe8e2; }
.special-row:last-child { border-bottom: none; }
.special-row > a { font-family: var(--wiki-display); font-size: 1.2rem; color: var(--text); }
.special-row > a:hover { color: var(--link); text-decoration: none; }
.special-figure {
  font-family: var(--wiki-mono);
  font-size: 0.68rem;
  color: var(--wiki-figure);
  margin-left: 0.5rem;
}
.special-gloss {
  font-family: var(--wiki-ui);
  font-size: 0.78rem;
  line-height: 1.55;
  color: var(--muted);
  margin-top: 0.15rem;
  max-width: 42rem;
}

.loose-list { list-style: none; }
.loose-row {
  display: flex;
  align-items: baseline;
  gap: 0.55rem;
  flex-wrap: wrap;
  padding: 0.36rem 0;
  border-bottom: 1px solid #ebe8e2;
}
.loose-row:last-child { border-bottom: none; }
.loose-written {
  font-family: var(--wiki-mono);
  font-size: 0.76rem;
  background: var(--wiki-plate);
  padding: 0.08em 0.32em;
  border-radius: 2px;
  color: var(--wiki-figure);
}
.loose-arrow { color: var(--wiki-rule); }
.loose-dest { font-family: var(--wiki-mono); font-size: 0.76rem; }
.loose-count {
  margin-left: auto;
  font-family: var(--wiki-mono);
  font-size: 0.66rem;
  color: var(--wiki-figure);
}

/* ─── Tags ─────────────────────────────────────────────────── */

.tags { display: flex; flex-wrap: wrap; gap: 0.25rem; }
.tag {
  font-family: var(--wiki-ui);
  font-size: 0.66rem;
  color: var(--link);
  border: 1px solid var(--wiki-rule);
  border-radius: 2px;
  padding: 0.08rem 0.35rem;
  background: #fff;
}
a.tag:hover { border-color: var(--link); text-decoration: none; }
.tag-lone { color: var(--muted); background: none; border-style: dashed; }

/* ─── Search results page ──────────────────────────────────── */

#search-results { list-style: none; max-width: 46rem; }
.sr-item { padding: 0.7rem 0; border-bottom: 1px solid #ebe8e2; }
.sr-item:last-child { border-bottom: none; }
.sr-item a { font-family: var(--wiki-display); font-size: 1.15rem; color: var(--text); }
.sr-item a:hover { color: var(--link); text-decoration: none; }
.sr-where {
  font-family: var(--wiki-mono);
  font-size: 0.64rem;
  text-transform: uppercase;
  letter-spacing: 0.05em;
  color: var(--wiki-figure);
  margin-left: 0.45rem;
}
.sr-gloss {
  font-family: var(--wiki-ui);
  font-size: 0.79rem;
  line-height: 1.55;
  color: var(--muted);
  margin-top: 0.15rem;
}

@media (prefers-reduced-motion: reduce) {
  * { animation-duration: 0.01ms !important; transition-duration: 0.01ms !important; }
  html { scroll-behavior: auto !important; }
}

@media (max-width: 600px) {
  main.wiki .home-title { font-size: 2.1rem; }
  main.wiki h1 { font-size: 1.6rem; }
  .mag-4 .plate-name { font-size: 1.3rem; }
  .mag-3 .plate-name { font-size: 1.15rem; }
  .figure-band { gap: 0 1.4rem; }
  .wikisearch { margin-left: 0; flex: 1 1 100%; }
}
"""


WIKI_JS = r"""/* Wiki behaviour: search, and the A-Z filter. No dependencies, no network
   beyond one fetch of the prebuilt index, and every page works without it —
   search degrades to the A-Z list, which is plain HTML.

   The index is [title, url-after-/wiki/, gloss, where, kind]. */
(function () {
  'use strict';

  var KINDS = { definition: 0, note: 1, topic: 2, contributor: 3, book: 3, wanted: 4 };
  var index = null;
  var pending = null;

  function load() {
    if (index) return Promise.resolve(index);
    if (!pending) {
      pending = fetch('/wiki/search-index.json')
        .then(function (r) { return r.ok ? r.json() : { n: [] }; })
        .then(function (data) { index = data.n || []; return index; })
        .catch(function () { index = []; return index; });
    }
    return pending;
  }

  function score(row, q, terms) {
    var title = row[0].toLowerCase();
    var hay = title + ' ' + row[2].toLowerCase() + ' ' + row[3].toLowerCase();
    var s = 0;
    if (title === q) s = 1000;
    else if (title.indexOf(q) === 0) s = 600;
    else if (title.indexOf(q) !== -1) s = 320;
    else if (row[2].toLowerCase().indexOf(q) !== -1) s = 120;
    if (!s) {
      // Every word has to appear somewhere, so "massey place" still finds things.
      for (var i = 0; i < terms.length; i++) {
        if (hay.indexOf(terms[i]) === -1) return 0;
      }
      s = 60;
    }
    return s - (KINDS[row[4]] === undefined ? 2 : KINDS[row[4]]) * 4;
  }

  function search(rows, query, limit) {
    var q = query.trim().toLowerCase();
    if (q.length < 2) return [];
    var terms = q.split(/\s+/);
    var hits = [];
    for (var i = 0; i < rows.length; i++) {
      var s = score(rows[i], q, terms);
      if (s > 0) hits.push([s, rows[i]]);
    }
    hits.sort(function (a, b) {
      if (b[0] !== a[0]) return b[0] - a[0];
      return a[1][0].toLowerCase() < b[1][0].toLowerCase() ? -1 : 1;
    });
    return hits.slice(0, limit).map(function (h) { return h[1]; });
  }

  function el(tag, cls, text) {
    var node = document.createElement(tag);
    if (cls) node.className = cls;
    if (text) node.textContent = text;
    return node;
  }

  function href(row) { return '/wiki/' + row[1]; }

  /* ---- toolbar search: instant dropdown ---- */

  var box = document.getElementById('wiki-q');
  var panel = document.getElementById('wiki-q-results');

  if (box && panel) {
    var active = -1;

    function close() { panel.hidden = true; panel.textContent = ''; active = -1; }

    function draw(rows) {
      panel.textContent = '';
      if (!rows.length) {
        panel.appendChild(el('div', 'r-empty', 'No match. Try a different word.'));
        panel.hidden = false;
        return;
      }
      rows.forEach(function (row) {
        var a = el('a', null);
        a.href = href(row);
        var line = el('div', null);
        line.appendChild(el('span', 'r-title', row[0]));
        line.appendChild(el('span', 'r-where', row[3]));
        a.appendChild(line);
        if (row[2]) a.appendChild(el('div', 'r-gloss', row[2]));
        panel.appendChild(a);
      });
      panel.hidden = false;
      active = -1;
    }

    function run() {
      var q = box.value;
      if (q.trim().length < 2) { close(); return; }
      load().then(function (rows) {
        if (box.value !== q) return;   // a later keystroke already won
        draw(search(rows, q, 10));
      });
    }

    box.addEventListener('input', run);
    box.addEventListener('focus', function () { if (box.value.trim().length >= 2) run(); });

    box.addEventListener('keydown', function (e) {
      var items = panel.querySelectorAll('a');
      if (e.key === 'Escape') { close(); box.blur(); return; }
      if (!items.length) return;
      if (e.key === 'ArrowDown' || e.key === 'ArrowUp') {
        e.preventDefault();
        active += (e.key === 'ArrowDown' ? 1 : -1);
        if (active < 0) active = items.length - 1;
        if (active >= items.length) active = 0;
        for (var i = 0; i < items.length; i++) {
          items[i].classList.toggle('is-active', i === active);
        }
        items[active].scrollIntoView({ block: 'nearest' });
      } else if (e.key === 'Enter' && active >= 0) {
        e.preventDefault();
        window.location.href = items[active].href;
      }
    });

    document.addEventListener('click', function (e) {
      if (!panel.hidden && !panel.contains(e.target) && e.target !== box) close();
    });

    document.addEventListener('keydown', function (e) {
      var tag = (e.target.tagName || '').toLowerCase();
      if (e.key === '/' && tag !== 'input' && tag !== 'textarea' && !e.metaKey && !e.ctrlKey) {
        e.preventDefault();
        box.focus();
        box.select();
      }
    });
  }

  /* ---- /wiki/search: the full results page ---- */

  var results = document.getElementById('search-results');
  var status = document.getElementById('search-status');

  if (results) {
    var field = document.getElementById('search-q');

    function show(query) {
      if (!query || query.trim().length < 2) {
        results.textContent = '';
        if (status) status.textContent = 'Type at least two letters to search.';
        return;
      }
      load().then(function (rows) {
        var hits = search(rows, query, 80);
        results.textContent = '';
        if (status) {
          status.textContent = hits.length
            ? hits.length + (hits.length === 80 ? '+ matches for ' : ' matches for ') + '“' + query + '”'
            : 'Nothing matches “' + query + '”. The A–Z index lists every note.';
        }
        var list = el('ul', null);
        hits.forEach(function (row) {
          var li = el('li', 'sr-item');
          var a = el('a', null, row[0]);
          a.href = href(row);
          li.appendChild(a);
          li.appendChild(el('span', 'sr-where', row[3]));
          if (row[2]) li.appendChild(el('div', 'sr-gloss', row[2]));
          list.appendChild(li);
        });
        results.appendChild(list);
      });
    }

    var q0 = new URLSearchParams(window.location.search).get('q') || '';
    if (field) {
      field.value = q0;
      field.addEventListener('input', function () { show(field.value); });
    }
    if (box) box.value = q0;
    if (q0) show(q0);
  }

  /* ---- A-Z filter ---- */

  var azFilter = document.getElementById('az-filter');
  if (azFilter) {
    var azCount = document.getElementById('az-count');
    var rows = Array.prototype.slice.call(document.querySelectorAll('.az-row'));
    var blocks = Array.prototype.slice.call(document.querySelectorAll('.az-block'));
    azFilter.addEventListener('input', function () {
      var q = azFilter.value.trim().toLowerCase();
      var shown = 0;
      rows.forEach(function (row) {
        var hit = !q || row.getAttribute('data-search').indexOf(q) !== -1;
        row.hidden = !hit;
        if (hit) shown++;
      });
      blocks.forEach(function (block) {
        block.hidden = !block.querySelector('.az-row:not([hidden])');
      });
      if (azCount) azCount.textContent = shown;
    });
  }
})();
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


def build_search_index(notes: list[Note], glossary: list[Note], index: LinkIndex,
                       books: dict[str, list[Note]]) -> str:
    """One prebuilt array the client filters in memory: no service, no network
    beyond this file. Rows are [title, url after /wiki/, gloss, where, kind]."""
    rows: list[list[str]] = []

    def add(title: str, url: str, gloss: str, where: str, kind: str) -> None:
        rows.append([title, url[len("/wiki/"):], clip(gloss, 150), where, kind])

    for note in sorted(glossary, key=lambda n: (n.term.lower(), n.rel)):
        add(note.term, note.url, note.summary, "definition", "definition")
    for note in sorted(notes, key=lambda n: (n.title.lower(), n.rel)):
        where = member_label(note.member)
        if note.book:
            where += " · " + book_title(note.book)[0]
        elif note.folder != "_root":
            where += " · " + folder_label(note.folder)
        add(note.title, note.url, note.summary, where, "note")
    for slug in sorted(index.topics, key=lambda s: index.topic_labels[s]):
        count = len(index.topics[slug])
        add(index.topic_labels[slug], topic_url(slug), f"{count} notes tagged this way",
            "topic", "topic")
    for group in index.wanted_groups():
        add(group["name"], wanted_url(group["slug"]),
            f"{len(group['sources'])} notes link to this title; nobody has written it yet",
            "wanted", "wanted")
    for member in sorted({n.member for n in notes}):
        add(member_label(member), f"/wiki/{slugify(member)}/",
            "Contributor index", "contributor", "contributor")
    for book_id in sorted(books):
        title, author, year = book_title(book_id)
        add(title, f"/wiki/commons/reading/{slugify(book_id)}/",
            " · ".join(filter(None, [author, year, f"{len(books[book_id])} reading notes"])),
            "book", "book")

    return json.dumps({"n": rows}, ensure_ascii=False, separators=(",", ":")) + "\n"


def prune(directory: Path, keep: set[str]) -> int:
    """Delete generated pages whose subject no longer exists.

    Wanted pages and topic pages are derived wholesale from the link graph, so
    the generator owns every file in these directories — an entry that drops out
    of the graph has to take its page with it, or a full and an incremental
    build would disagree about what is on disk.
    """
    if not directory.is_dir():
        return 0
    removed = 0
    for path in sorted(directory.glob("*.html")):
        if path.name != "index.html" and path.stem not in keep:
            path.unlink()
            removed += 1
    return removed


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

    The incremental build must be byte-identical to a full one, so this has to
    over-approximate rather than guess. A page goes stale when:

    1. it *is* a changed note;
    2. a changed note links to it — its "What links here" and its "Mentioned
       alongside" both read off the set of notes linking here, and both can only
       move when one of those linkers moves;
    3. it links to a name whose resolution flipped — a wanted link became live,
       or a live one became wanted. Resolution is by exact id, by glossary
       alias, *and* by normalised slug, so all three name spaces are tracked;
    4. it displays a changed note's title. Backlink lists and alongside lists
       print titles, so renaming a note dirties everything that lists it: its
       linkers' targets (the co-citation neighbourhood) as well as its targets;
    5. it is defined by a changed glossary entry, or was.
    """
    current = {n.rel: n for n in notes}
    flipped_ids: set[str] = set()
    flipped_slugs: set[str] = set()
    renamed: list[Note] = []
    glossary_keys: set[str] = set()

    def names_of(note: Note) -> set[str]:
        return {note.note_id, *note.aliases}

    for rel in touched:
        before, after = old.get(rel), current.get(rel)
        if before is None or after is None:
            only = after or before
            flipped_ids |= names_of(only)
            renamed.append(only)
            if only.kind == "glossary":
                glossary_keys |= {slugify(n) for n in [only.term, only.note_id, *only.aliases]}
        else:
            flipped_ids |= names_of(before) ^ names_of(after)
            if before.title != after.title or before.url != after.url:
                renamed.append(after)
            if "glossary" in (before.kind, after.kind):
                glossary_keys |= {slugify(n) for n in
                                  [before.term, before.note_id, after.term, after.note_id,
                                   *before.aliases, *after.aliases]}
    flipped_slugs = {slugify(n) for n in flipped_ids if slugify(n)}

    stale = {rel for rel in touched if rel in current}

    # (2) and part of (4): everything a changed note points at.
    for rel in touched:
        for source in (old.get(rel), current.get(rel)):
            if source is None:
                continue
            for target in source.outlinks:
                dest = index.lookup(target)
                if dest is not None:
                    stale.add(dest.rel)

    # (4): the co-citation neighbourhood of a renamed note — every note that
    # shares a linker with it lists its title in "Mentioned alongside".
    for note in renamed:
        for source in index.backlinks.get(note.url) or []:
            for peer in index.targets.get(source.rel) or []:
                stale.add(peer.rel)

    # (3): links whose resolution flipped, in either name space.
    if flipped_ids or flipped_slugs:
        for note in notes:
            targets = set(note.outlinks)
            if flipped_ids & targets:
                stale.add(note.rel)
            elif flipped_slugs & {slugify(t) for t in targets}:
                stale.add(note.rel)

    # (5): notes a changed glossary entry does or did define.
    for key in glossary_keys:
        for note in index.by_name.get(key) or []:
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
                         render_member_index(member, items, index))

    books: dict[str, list[Note]] = defaultdict(list)
    for note in plain:
        if note.book:
            books[note.book].append(note)
    for book_id, items in sorted(books.items()):
        written += write(OUT_ROOT / "commons" / "reading" / slugify(book_id) / "index.html",
                         render_book_index(book_id, items, index))

    # Derived surfaces. Every one of them reads the whole link graph, which the
    # manifest reconstructs exactly in both modes, so they are rebuilt on every
    # run — `write()` is a no-op when the bytes match, and rebuilding is what
    # keeps `--changed` byte-identical to `--full`.
    wanted = index.wanted_groups()
    for group in wanted:
        written += write(OUT_ROOT / "wanted" / f"{group['slug']}.html",
                         render_wanted_page(group, index))
    removed += prune(OUT_ROOT / "wanted", {g["slug"] for g in wanted})

    for slug in sorted(index.topics):
        written += write(OUT_ROOT / "topics" / f"{slug}.html",
                         render_topic_page(slug, index.topic_labels[slug],
                                           index.topics[slug], index))
    removed += prune(OUT_ROOT / "topics", set(index.topics))

    written += write(OUT_ROOT / "wanted" / "index.html", render_wanted_index(wanted, index))
    written += write(OUT_ROOT / "topics" / "index.html", render_topics_index(index))
    written += write(OUT_ROOT / "glossary" / "index.html",
                     render_glossary_index(glossary, index, plain))
    written += write(OUT_ROOT / "hubs.html", render_hubs(plain, index))
    written += write(OUT_ROOT / "orphans.html", render_orphans(plain, index))
    written += write(OUT_ROOT / "loose-links.html", render_loose_links(index))
    written += write(OUT_ROOT / "changes.html", render_changes(plain, commits))
    written += write(OUT_ROOT / "special.html",
                     render_special(plain, glossary, index, books, commits))
    written += write(OUT_ROOT / "search.html", render_search())
    written += write(OUT_ROOT / "all.html", render_all_notes(plain, index))
    written += write(OUT_ROOT / "index.html", render_home(plain, glossary, index, commits))
    written += write(OUT_ROOT / "search-index.json",
                     build_search_index(plain, glossary, index, books))
    written += write(OUT_ROOT / "wiki.css", WIKI_CSS)
    written += write(OUT_ROOT / "wiki.js", WIKI_JS)
    written += save_manifest(notes)

    elapsed = time.perf_counter() - started
    mode = "full" if changed is None else f"incremental ({len(touched)} source change(s))"
    print(f"wiki [{mode}]: {len(plain)} notes, {len(glossary)} glossary terms, "
          f"{len(by_member)} contributors, {len(books)} books, "
          f"{len(index.topics)} topics, {len(wanted)} wanted — "
          f"{len(stale)} note page(s) rendered, {written} file(s) written"
          f"{f', {removed} removed' if removed else ''} in {elapsed:.2f}s")
    if quiet:
        return 0
    orphans = sum(1 for n in plain if index.inbound(n) == 0)
    print(f"  links: {index.resolved_hits} resolved "
          f"({index.loose_hits} of them by normalisation, across {len(index.loose)} names), "
          f"{sum(index.wanted.values())} wanted across {len(index.wanted)} targets")
    print(f"  graph: {orphans} orphan note(s)")
    for note_id, hits in sorted(index.ambiguous.items()):
        print(f"  ambiguous id '{note_id}' ({len(hits)} notes) -> "
              f"{sorted(hits, key=lambda n: n.rel)[0].rel}")
    for alias, owner in index.alias_conflicts:
        print(f"  alias '{alias}' (glossary '{owner}') shadowed by a real note of that name")
    for slug, ids in sorted(index.slug_conflicts.items()):
        print(f"  slug '{slug}' claimed by {len(ids)} names {ids} — left unresolved")
    if skipped:
        print("  skipped: " + ", ".join(f"{k}={v}" for k, v in sorted(skipped.items())))
    top = sorted(wanted, key=lambda g: (-len(g["sources"]), g["slug"]))[:6]
    if top:
        print("  most-wanted pages: "
              + ", ".join(f"{g['name']} ({len(g['sources'])})" for g in top))
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
