"""The notes corpus as blyg items: parsing, link resolution, rendering, splitting.

Nothing here talks to the network. `blyg_import.py` drives it.

Vocabulary:
  note  one Markdown file in the repo.
  unit  one blyg item. A note is one unit, or several numbered parts when it is
        longer than the item size budget. Part 1's key is the note path; part N's
        key is "<path>#part-N", so a note that later grows keeps its first item.
"""

from __future__ import annotations

import fnmatch
import hashlib
import json
import re
from collections import Counter, defaultdict
from dataclasses import dataclass, field
from pathlib import Path
from typing import Callable, Iterable, Optional

# Studio's id alphabet (src/identity.ts). Used only to make fake ids for dry runs.
ID_ALPHABET = "0123456789abcdefghjkmnpqrstvwxyz"

FRONTMATTER_RE = re.compile(r"\A---[ \t]*\r?\n(.*?)\r?\n---[ \t]*(?:\r?\n|\Z)", re.S)
# Obsidian links and embeds: no brackets inside. A link may wrap onto the next
# line (notes are hard-wrapped), but never across a blank line.
WIKILINK_RE = re.compile(r"(!?)\[\[((?:(?!\n[ \t]*\n)[^\[\]]){1,400}?)\]\]")
H1_RE = re.compile(r"^#[ \t]+(.+?)[ \t]*#*[ \t]*$")
ANY_H1_RE = re.compile(r"^#[ \t]+(.+?)[ \t]*#*[ \t]*$", re.M)
FENCE_RE = re.compile(r"^[ \t]{0,3}(`{3,}|~{3,})")
# Inline code: a backtick run, then the shortest text up to an equal run, not across a blank line.
CODE_SPAN_RE = re.compile(r"(`+)(?:(?!\1)(?!\n[ \t]*\n)[\s\S])+?\1")
FILE_EMBED_EXT = {
    ".png", ".jpg", ".jpeg", ".gif", ".svg", ".webp", ".bmp", ".pdf",
    ".mp3", ".mp4", ".wav", ".mov", ".webm", ".canvas", ".excalidraw",
}
# Studio's TK authoring tokens (src/tk.ts). A literal one outside code would make
# publish fail (unterminated scope), so it is backslash-escaped: the markdown
# still shows the brackets, and the raw text no longer contains the token.
TK_TOKENS = {"[TK]": r"\[TK\]", "[/TK]": r"\[/TK\]", "[=]": r"\[=\]"}
FOOTER_KEYS = (("connects", "Connects"), ("supports", "Supports"), ("contradicts", "Contradicts"))
# Room kept free in every part for the title, byline, part navigation and footer.
SPLIT_OVERHEAD = 1500
# A resolved link grows by roughly this much when `[[target]]` becomes `[[id | label]]`.
LINK_GROWTH = 32


# ─── Frontmatter ─────────────────────────────────────────────────────────────

def _unquote(value: str) -> str:
    value = value.strip()
    if len(value) >= 2 and value[0] == value[-1] and value[0] in "\"'":
        inner = value[1:-1]
        return inner.replace("''", "'") if value[0] == "'" else inner
    return value


def parse_frontmatter(raw: str) -> tuple[dict, str]:
    """(frontmatter, body). The YAML subset the corpus uses: scalars, inline
    lists, block lists, quoted scalars wrapped over several lines."""
    m = FRONTMATTER_RE.match(raw)
    if not m:
        return {}, raw
    block, body = m.group(1), raw[m.end():]
    data: dict = {}
    lines = block.splitlines()
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
        if rest.startswith("[") and rest.endswith("]") and not rest.startswith("[["):
            data[key] = [p for p in (_unquote(x) for x in rest[1:-1].split(",")) if p]
        elif rest:
            if rest[0] in "\"'" and not (len(rest) > 1 and rest.rstrip().endswith(rest[0])):
                quote, buf = rest[0], [rest]
                while i < len(lines):
                    buf.append(lines[i])
                    i += 1
                    if buf[-1].rstrip().endswith(quote):
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


# ─── Notes ───────────────────────────────────────────────────────────────────

def humanize(stem: str) -> str:
    text = re.sub(r"[-_]+", " ", stem).strip()
    return text[:1].upper() + text[1:] if text else stem


def strip_wikilinks(text: str) -> str:
    """Wikilinks reduced to their display text, for titles."""
    def plain(m: re.Match) -> str:
        link = parse_link(m.group(2))
        return link.display
    return WIKILINK_RE.sub(plain, text)


@dataclass
class Note:
    path: str              # posix path relative to the repo root
    front: dict
    body: str              # frontmatter stripped; the leading H1 removed when it is the title
    title: str
    aliases: list[str]

    @property
    def stem(self) -> str:
        return self.path.rsplit("/", 1)[-1][:-3] if self.path.lower().endswith(".md") else self.path.rsplit("/", 1)[-1]

    @property
    def parent(self) -> str:
        return self.path.rsplit("/", 1)[0] if "/" in self.path else ""

    @property
    def top(self) -> str:
        """The collaboration area: 'raw-notes/<dir>' or 'wiki'."""
        parts = self.path.split("/")
        return "/".join(parts[:2]) if parts[0] == "raw-notes" and len(parts) > 2 else parts[0]


def parse_note(path: str, raw: str) -> Note:
    raw = raw.replace("\r\n", "\n")
    front, body = parse_frontmatter(raw)
    title = ""
    for key in ("title", "term"):
        val = front.get(key)
        if isinstance(val, str) and val.strip():
            title = val.strip()
            break
    # A leading H1 is the note's title line; the item gets its own H1, so drop it.
    lines = body.split("\n")
    for idx, line in enumerate(lines):
        if not line.strip():
            continue
        m = H1_RE.match(line)
        if m:
            title = title or m.group(1).strip()
            body = "\n".join(lines[idx + 1:])
        break
    if not title:
        m = ANY_H1_RE.search(body)
        stem = path.rsplit("/", 1)[-1]
        title = m.group(1).strip() if m else humanize(stem[:-3] if stem.lower().endswith(".md") else stem)
    title = re.sub(r"\s+", " ", strip_wikilinks(title)).strip()
    aliases = as_list(front.get("aliases"))
    # Member essays are mirrored as "<Title> (part 1 of 3)" files; a link to
    # the essay's bare title means its first part.
    m = re.match(r"^(.*?)\s*\(part 1 of \d+\)$", title)
    if m and m.group(1):
        aliases.append(m.group(1))
    return Note(path=path, front=front, body=body.strip("\n"), title=title, aliases=aliases)


def load_corpus(root: Path, include: Iterable[str], exclude: Iterable[str] = ()) -> list[Note]:
    seen: dict[str, Note] = {}
    for pattern in include:
        for p in sorted(root.glob(pattern)):
            rel = p.relative_to(root).as_posix()
            if rel in seen or not p.is_file() or any(fnmatch.fnmatch(rel, x) for x in exclude):
                continue
            raw = p.read_bytes().decode("utf-8", errors="replace")
            if not raw.strip():
                continue
            seen[rel] = parse_note(rel, raw)
    return [seen[k] for k in sorted(seen)]


# ─── Attribution ─────────────────────────────────────────────────────────────

@dataclass
class Authors:
    authors: dict           # raw-notes dir -> {"name", "blyg"}
    handles: dict           # contributor handle -> raw-notes dir
    commons_dir: str = "commons"
    contributions_dir: str = "raw-notes/commons/contributions"

    @classmethod
    def load(cls, path: Path, **kw) -> "Authors":
        data = json.loads(path.read_text())
        return cls(authors=data.get("authors", {}), handles=data.get("handles", {}), **kw)

    def lookup(self, key: str) -> Optional[dict]:
        key = (key or "").strip().lstrip("@").lower()
        if not key:
            return None
        return self.authors.get(self.handles.get(key, key))

    def author_for(self, note: Note) -> Optional[dict]:
        """The person a note is attributed to, or None for shared notes."""
        parts = note.path.split("/")
        if parts[0] != "raw-notes" or len(parts) < 3:
            return None  # wiki/ and top-level files are shared
        if parts[1] == self.commons_dir:
            prefix = self.contributions_dir.rstrip("/") + "/"
            if note.path.startswith(prefix):
                for key in ("author", "handle"):
                    who = self.lookup(str(note.front.get(key) or ""))
                    if who:
                        return who
            return None
        return self.lookup(parts[1])


def render_byline(author: Optional[dict]) -> str:
    if not author or not author.get("name"):
        return ""
    name = re.sub(r"([\[\]*_`])", r"\\\1", author["name"].strip())
    url = (author.get("blyg") or "").strip()
    return f"*By [{name}]({url})*" if url else f"*By {name}*"


def sha(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


# ─── Links ───────────────────────────────────────────────────────────────────

@dataclass
class Link:
    target: str
    heading: str
    alias: str

    @property
    def display(self) -> str:
        return self.alias or self.target or self.heading


def parse_link(inner: str) -> Link:
    inner = re.sub(r"\s+", " ", inner)  # a link wrapped onto the next line
    target, _, alias = inner.partition("|")
    target = target.rstrip("\\")  # `[[a\|b]]` inside a table
    target, _, heading = target.partition("#")
    return Link(target=target.strip(), heading=heading.strip(), alias=alias.strip())


def link_key(target: str) -> str:
    t = target.strip().replace("\\", "/")
    t = t.rsplit("/", 1)[-1]
    if t.lower().endswith(".md"):
        t = t[:-3]
    return t.strip().lower()


def slug_key(text: str) -> str:
    return re.sub(r"[^a-z0-9]+", "-", link_key(text)).strip("-")


@dataclass
class Resolution:
    note: Optional[Note]
    tier: str        # basename | title | slug | ''


class LinkIndex:
    """Resolve a wikilink target to a note: by filename basename (case-
    insensitive), then frontmatter/H1 title and aliases, then (optionally) a
    punctuation-insensitive slug of either. Several candidates on one tier are
    settled by proximity to the linking note: same directory, same top-level
    author dir, then commons, then path order. Every such case is recorded in
    `collisions`."""

    def __init__(self, notes: list[Note], slug_matching: bool = True, commons_top: str = "raw-notes/commons"):
        self.slug_matching = slug_matching
        self.commons_top = commons_top
        self.by_base: dict[str, list[Note]] = defaultdict(list)
        self.by_title: dict[str, list[Note]] = defaultdict(list)
        self.by_slug: dict[str, list[Note]] = defaultdict(list)
        for n in notes:
            self.by_base[n.stem.lower()].append(n)
            for name in dict.fromkeys([n.title.lower(), *(a.lower() for a in n.aliases)]):
                if name:
                    self.by_title[name].append(n)
            for name in dict.fromkeys([slug_key(n.stem), slug_key(n.title), *(slug_key(a) for a in n.aliases)]):
                if name and n not in self.by_slug[name]:
                    self.by_slug[name].append(n)
        # (tier, key) -> {"candidates": [...], "decisions": Counter[(source dir, chosen, rule)]}
        self.collisions: dict[tuple[str, str], dict] = {}

    def _choose(self, tier: str, key: str, cands: list[Note], source: Optional[Note]) -> Note:
        if len(cands) == 1:
            return cands[0]
        ordered = sorted(cands, key=lambda n: n.path)
        chosen, rule = ordered[0], "path order"
        if source is not None:
            for rule_name, pred in (
                ("same directory", lambda n: n.parent == source.parent),
                ("same author dir", lambda n: n.top == source.top),
                ("commons", lambda n: n.top == self.commons_top),
            ):
                hits = [n for n in ordered if pred(n)]
                if hits:
                    chosen, rule = hits[0], rule_name
                    break
        entry = self.collisions.setdefault((tier, key), {"candidates": [n.path for n in ordered], "decisions": Counter()})
        entry["decisions"][(source.parent if source else "", chosen.path, rule)] += 1
        return chosen

    def resolve(self, target: str, source: Optional[Note] = None) -> Resolution:
        key = link_key(target)
        if not key:
            return Resolution(None, "")
        tiers = [("basename", self.by_base, key), ("title", self.by_title, target.strip().lower())]
        if self.slug_matching:
            tiers.append(("slug", self.by_slug, slug_key(target)))
        for tier, table, k in tiers:
            cands = table.get(k)
            if cands:
                return Resolution(self._choose(tier, k, cands, source), tier)
        return Resolution(None, "")


@dataclass
class LinkStats:
    total: int = 0
    by_tier: Counter = field(default_factory=Counter)
    unresolved: Counter = field(default_factory=Counter)
    self_links: int = 0
    headings_dropped: int = 0
    embeds_file: Counter = field(default_factory=Counter)
    embeds_note: int = 0
    tk_escaped: int = 0
    footer_links: int = 0
    footer_resolved: int = 0


# ─── Code-aware text walking ─────────────────────────────────────────────────

def map_outside_code(text: str, fn: Callable[[str], str]) -> str:
    """Apply `fn` to every stretch of text outside fenced code blocks and inline
    code spans. Link grammar inside code is literal for Obsidian and for blyg.
    Stretches are whole runs of lines between fences, so a link that wraps onto
    the next line is seen whole."""
    out: list[str] = []
    prose: list[str] = []
    fence: Optional[str] = None

    def flush():
        if prose:
            chunk = "\n".join(prose)
            pieces, last = [], 0
            for cm in CODE_SPAN_RE.finditer(chunk):
                pieces.append(fn(chunk[last:cm.start()]))
                pieces.append(cm.group(0))
                last = cm.end()
            pieces.append(fn(chunk[last:]))
            out.append("".join(pieces))
            prose.clear()

    for line in text.split("\n"):
        m = FENCE_RE.match(line)
        if fence is not None:
            out.append(line)
            rest = line.strip()[len(m.group(1)):] if m else ""
            if m and m.group(1)[0] == fence[0] and len(m.group(1)) >= len(fence) and not rest.strip():
                fence = None
            continue
        if m:
            flush()
            fence = m.group(1)
            out.append(line)
            continue
        prose.append(line)
    flush()
    return "\n".join(out)


# ─── Rendering ───────────────────────────────────────────────────────────────

IdLookup = Callable[[str], Optional[str]]   # unit key -> blyg id, or None to render plain text


def label_text(text: str) -> str:
    """Studio's labelText (src/grammar.ts): one line, never `]]`."""
    return re.sub(r"\](?=\]|$)", "] ", re.sub(r"\s+", " ", text).strip())


def blyg_link(item_id: str, label: str) -> str:
    lab = label_text(label)
    return f"[[{item_id} | {lab}]]" if lab else f"[[{item_id}]]"


class Renderer:
    def __init__(self, index: LinkIndex, units_by_note: dict[str, list["Unit"]]):
        self.index = index
        self.units_by_note = units_by_note

    def _target_unit(self, note: Note) -> str:
        return note.path  # links to a split note go to part 1, whose key is the note path

    def rewrite_links(self, text: str, source: Note, id_of: IdLookup, stats: Optional[LinkStats] = None,
                      targets: Optional[set] = None) -> str:
        def one(m: re.Match) -> str:
            bang, inner = m.group(1), m.group(2)
            link = parse_link(inner)
            display = link.display
            if bang:
                name = link.target.rsplit("/", 1)[-1]
                ext = ("." + name.rsplit(".", 1)[-1].lower()) if "." in name else ""
                if ext in FILE_EMBED_EXT:
                    if stats:
                        stats.embeds_file[ext] += 1
                    return f"*(embedded file not imported: {name})*"
                if stats:
                    stats.embeds_note += 1
            if stats:
                stats.total += 1
            if not link.target:  # [[#heading]] inside the same note
                if stats:
                    stats.self_links += 1
                return display
            res = self.index.resolve(link.target, source)
            if res.note is None:
                if stats:
                    stats.unresolved[link_key(link.target)] += 1
                return display
            if res.note is source:
                if stats:
                    stats.self_links += 1
                return display
            if stats:
                stats.by_tier[res.tier] += 1
                if link.heading:
                    stats.headings_dropped += 1
            key = self._target_unit(res.note)
            if targets is not None:
                targets.add(key)
            item_id = id_of(key)
            return blyg_link(item_id, display) if item_id else display

        def segment(s: str) -> str:
            s = WIKILINK_RE.sub(one, s)
            for tok, esc in TK_TOKENS.items():
                if tok in s:
                    if stats:
                        stats.tk_escaped += s.count(tok)
                    s = s.replace(tok, esc)
            return s

        return map_outside_code(text, segment)

    def footer(self, note: Note, id_of: IdLookup, stats: Optional[LinkStats], targets: Optional[set]) -> str:
        lines = []
        for key, label in FOOTER_KEYS:
            entries = []
            for raw in as_list(note.front.get(key)):
                inner = raw[2:-2] if raw.startswith("[[") and raw.endswith("]]") else raw
                link = parse_link(inner)
                res = self.index.resolve(link.target, note)
                if stats:
                    stats.footer_links += 1
                if res.note is None or res.note is note:
                    entries.append(link.display)
                    continue
                if stats:
                    stats.footer_resolved += 1
                if targets is not None:
                    targets.add(res.note.path)
                item_id = id_of(res.note.path)
                entries.append(blyg_link(item_id, res.note.title) if item_id else res.note.title)
            if entries:
                lines.append(f"**{label}:** " + " · ".join(entries))
        return "\n\n".join(lines)

    def render(self, unit: "Unit", byline: str, id_of: IdLookup, stats: Optional[LinkStats] = None,
               targets: Optional[set] = None) -> str:
        note = unit.note
        title = note.title + (f" (part {unit.part} of {unit.parts})" if unit.parts > 1 else "")
        out = ["# " + title.replace("\n", " ")]
        if byline:
            out += ["", byline]
        if unit.parts > 1:
            nav = [f"Part {unit.part} of {unit.parts}."]
            siblings = self.units_by_note[note.path]
            for label, idx in (("Previous", unit.part - 2), ("Next", unit.part)):
                if 0 <= idx < len(siblings):
                    sib = siblings[idx]
                    if targets is not None:
                        targets.add(sib.key)
                    sid = id_of(sib.key)
                    text = f"part {sib.part}"
                    nav.append(f"{label}: {blyg_link(sid, text) if sid else text}.")
            out += ["", " ".join(nav)]
        body = self.rewrite_links(unit.body, note, id_of, stats, targets)
        if body.strip():
            out += ["", body.strip("\n")]
        if unit.part == unit.parts:
            foot = self.footer(note, id_of, stats, targets)
            if foot:
                out += ["", "---", "", foot]
        return "\n".join(out) + "\n"


# ─── Splitting ───────────────────────────────────────────────────────────────

def _blocks(body: str) -> list[str]:
    """Paragraph blocks: split on blank lines, never inside a code fence."""
    blocks, cur, fence = [], [], None
    for line in body.split("\n"):
        m = FENCE_RE.match(line)
        if fence is None and m:
            fence = m.group(1)
        elif fence is not None and m and m.group(1)[0] == fence[0] and len(m.group(1)) >= len(fence):
            fence = None
            cur.append(line)
            continue
        if fence is None and not line.strip():
            if cur:
                blocks.append("\n".join(cur))
                cur = []
            continue
        cur.append(line)
    if cur:
        blocks.append("\n".join(cur))
    return blocks


def _cost(text: str) -> int:
    return len(text) + LINK_GROWTH * text.count("[[")


def split_body(body: str, max_chars: int) -> list[str]:
    """Split a note body into parts whose rendered size stays under max_chars."""
    budget = max(200, max_chars - SPLIT_OVERHEAD)
    if _cost(body) <= budget:
        return [body]
    pieces: list[str] = []
    for block in _blocks(body):
        if _cost(block) <= budget:
            pieces.append(block)
            continue
        cur = ""
        for line in block.split("\n"):
            while _cost(line) > budget:  # a single enormous line: cut it
                cut = budget // 2
                head, line = line[:cut], line[cut:]
                if cur:
                    pieces.append(cur)
                    cur = ""
                pieces.append(head)
            if cur and _cost(cur) + _cost(line) + 1 > budget:
                pieces.append(cur)
                cur = line
            else:
                cur = f"{cur}\n{line}" if cur else line
        if cur:
            pieces.append(cur)
    parts, cur = [], ""
    for p in pieces:
        if cur and _cost(cur) + _cost(p) + 2 > budget:
            parts.append(cur)
            cur = p
        else:
            cur = f"{cur}\n\n{p}" if cur else p
    if cur:
        parts.append(cur)
    return parts


@dataclass
class Unit:
    key: str
    note: Note
    part: int
    parts: int
    body: str


def make_units(notes: list[Note], max_chars: int) -> list[Unit]:
    units = []
    for n in notes:
        bodies = split_body(n.body, max_chars)
        for i, b in enumerate(bodies, 1):
            key = n.path if i == 1 else f"{n.path}#part-{i}"
            units.append(Unit(key=key, note=n, part=i, parts=len(bodies), body=b))
    return units


def units_by_note(units: list[Unit]) -> dict[str, list[Unit]]:
    out: dict[str, list[Unit]] = defaultdict(list)
    for u in units:
        out[u.note.path].append(u)
    return out


def fake_id(key: str) -> str:
    """A stable, well-formed stand-in id for dry runs."""
    n = int(hashlib.sha256(key.encode()).hexdigest(), 16)
    chars = []
    for _ in range(26):
        n, r = divmod(n, 32)
        chars.append(ID_ALPHABET[r])
    return "".join(chars)
