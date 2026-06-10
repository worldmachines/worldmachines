"""Convert a directory of markdown notes into a single Parquet table.

Single-contributor source (e.g. one author's Obsidian vault):
    uv run notes_to_parquet.py SRC_DIR OUT_PATH --contributor aneesh --embed

Multi-contributor source (e.g. the repo's raw-notes/ directory, where each
top-level subdirectory is one contributor):
    uv run notes_to_parquet.py raw-notes OUT_PATH --multi-contributor --embed

Reads CF_AI_TOKEN (or CLOUDFLARE_API_TOKEN) and CLOUDFLARE_ACCOUNT_ID from
`.env` at the nearest repo root.
"""
from __future__ import annotations

import argparse
import os
import re
import sys
import time
from datetime import date, datetime
from pathlib import Path

import httpx
import pyarrow as pa
import pyarrow.parquet as pq
import yaml
from dotenv import load_dotenv


FRONTMATTER_RE = re.compile(r"\A---\s*\n(.*?)\n---\s*\n?(.*)\Z", re.DOTALL)
H1_RE = re.compile(r"^#\s+(.+?)\s*$", re.MULTILINE)
WIKI_LINK_RE = re.compile(r"\[\[([^\]\|#]+?)(?:[#\|][^\]]*)?\]\]")

EXCLUDED_DIR_NAMES = frozenset({"Excalidraw", "node_modules"})

EMBED_MODEL = "@cf/google/embeddinggemma-300m"
EMBED_DIM = 768


def parse_note(path: Path, root: Path, multi_contributor: bool, default_contributor: str) -> dict | None:
    raw = path.read_text(encoding="utf-8", errors="replace")
    if not raw.strip():
        return None

    m = FRONTMATTER_RE.match(raw)
    if m:
        fm_text, body = m.group(1), m.group(2)
        try:
            fm = yaml.safe_load(fm_text) or {}
        except yaml.YAMLError:
            fm = {}
    else:
        fm, body = {}, raw

    if not isinstance(fm, dict):
        fm = {}

    h1 = H1_RE.search(body)
    title = h1.group(1).strip() if h1 else path.stem

    rel = path.relative_to(root)
    parts = rel.parts
    if multi_contributor:
        # Layout: <src>/<contributor>/<...>/note.md. Top-level files (e.g.
        # raw-notes/README.md) are not notes and get skipped upstream.
        contributor = parts[0]
        category = parts[1] if len(parts) > 2 else "_root"
    else:
        contributor = default_contributor
        category = parts[0] if len(parts) > 1 else "_root"

    tags = fm.get("tags") or []
    if isinstance(tags, str):
        tags = [tags]
    tags = [str(t) for t in tags]

    last_updated = fm.get("last_updated")
    if isinstance(last_updated, datetime):
        last_updated = last_updated.date()
    elif isinstance(last_updated, str):
        try:
            last_updated = date.fromisoformat(last_updated)
        except ValueError:
            last_updated = None
    elif not isinstance(last_updated, date):
        last_updated = None

    body_stripped = body.strip()
    wiki_links = sorted({m.group(1).strip() for m in WIKI_LINK_RE.finditer(body_stripped)})

    return {
        "path": str(rel),
        "slug": path.stem,
        "title": title,
        "contributor": contributor,
        "category": category,
        "summary": fm.get("summary") if isinstance(fm.get("summary"), str) else None,
        "tags": tags,
        "last_updated": last_updated,
        "body": body_stripped,
        "word_count": len(body_stripped.split()),
        "char_count": len(body_stripped),
        "wiki_links": wiki_links,
        "excluded_from_oracle": False,
    }


def is_excluded(rel: Path) -> bool:
    return any(p.startswith(".") or p in EXCLUDED_DIR_NAMES for p in rel.parts[:-1])


def collect_rows(
    src: Path,
    oracle_excluded_cats: set[str],
    multi_contributor: bool,
    default_contributor: str,
) -> list[dict]:
    rows: list[dict] = []
    for path in sorted(src.rglob("*.md")):
        if path.stat().st_size == 0:
            continue
        rel = path.relative_to(src)
        if is_excluded(rel):
            continue
        # In multi-contributor layout, top-level files (raw-notes/README.md)
        # are not contributor notes and get skipped.
        if multi_contributor and len(rel.parts) < 2:
            continue
        row = parse_note(path, src, multi_contributor, default_contributor)
        if row is not None:
            row["excluded_from_oracle"] = row["category"] in oracle_excluded_cats
            rows.append(row)
    if not rows:
        raise SystemExit(f"No non-empty markdown files found under {src}")
    return rows


def embed_input(row: dict, max_chars: int) -> str:
    # EmbeddingGemma is asymmetric (model card): documents take the
    # 'title: {t} | text: {x}' prefix; queries take 'task: search result |
    # query: {q}'. The query side lives in website/functions/api/embed.js —
    # the two must stay in lockstep, and changing either means re-embedding
    # the corpus (push to tools/notes-pipeline/ triggers notes-ingest.yml).
    parts = []
    if row.get("summary"):
        parts.append(row["summary"])
    parts.append(row["body"][:max_chars])
    text = "\n\n".join(p for p in parts if p).strip()
    return f"title: {row['title'] or 'none'} | text: {text}"


def embed_batch(client: httpx.Client, account_id: str, token: str, texts: list[str]) -> list[list[float]]:
    url = f"https://api.cloudflare.com/client/v4/accounts/{account_id}/ai/run/{EMBED_MODEL}"
    for attempt in range(3):
        try:
            r = client.post(
                url,
                headers={"Authorization": f"Bearer {token}", "Content-Type": "application/json"},
                json={"text": texts},
                timeout=120.0,
            )
            r.raise_for_status()
            d = r.json()
            if not d.get("success"):
                raise RuntimeError(f"Cloudflare AI error: {d.get('errors')}")
            return d["result"]["data"]
        except (httpx.HTTPError, RuntimeError) as e:
            if attempt == 2:
                raise
            wait = 2 ** attempt
            print(f"  retry {attempt + 1} after {wait}s ({e})", file=sys.stderr)
            time.sleep(wait)
    raise RuntimeError("unreachable")


def add_embeddings(
    rows: list[dict],
    token: str,
    account_id: str,
    batch_size: int,
    max_chars: int,
) -> None:
    # Embed every row. Use the `excluded_from_oracle` column to filter at
    # query time — DuckDB's list_cosine_similarity rejects any NULL in its
    # argument across the whole batch, so the column must be NULL-free.
    todo: list[tuple[int, str]] = [(i, embed_input(r, max_chars)) for i, r in enumerate(rows)]
    print(f"embedding {len(todo)} rows ({EMBED_MODEL}, batch={batch_size}, max_chars={max_chars})")
    with httpx.Client() as client:
        done = 0
        for start in range(0, len(todo), batch_size):
            chunk = todo[start : start + batch_size]
            vecs = embed_batch(client, account_id, token, [t for _, t in chunk])
            if len(vecs) != len(chunk):
                raise RuntimeError(f"batch size mismatch: sent {len(chunk)}, got {len(vecs)}")
            for (idx, _), v in zip(chunk, vecs):
                if len(v) != EMBED_DIM:
                    raise RuntimeError(f"expected dim {EMBED_DIM}, got {len(v)}")
                rows[idx]["embedding"] = v
            done += len(chunk)
            print(f"  {done}/{len(todo)}")


def build_table(rows: list[dict], with_embeddings: bool) -> pa.Table:
    fields = [
        ("path", pa.string()),
        ("slug", pa.string()),
        ("title", pa.string()),
        ("contributor", pa.string()),
        ("category", pa.string()),
        ("summary", pa.string()),
        ("tags", pa.list_(pa.string())),
        ("last_updated", pa.date32()),
        ("body", pa.string()),
        ("word_count", pa.int32()),
        ("char_count", pa.int32()),
        ("wiki_links", pa.list_(pa.string())),
        ("excluded_from_oracle", pa.bool_()),
    ]
    if with_embeddings:
        # Variable-length list so blacklisted rows (e.g. _root) can be NULL
        # without tripping pyarrow's fixed-size-list null restriction.
        fields.append(("embedding", pa.list_(pa.float32())))
    return pa.Table.from_pylist(rows, schema=pa.schema(fields))


def find_dotenv(start: Path) -> Path | None:
    for d in [start, *start.parents]:
        p = d / ".env"
        if p.exists():
            return p
    return None


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("src", type=Path, help="Source directory of markdown notes")
    ap.add_argument("out", type=Path, help="Output Parquet file path")
    ap.add_argument("--embed", action="store_true", help="Also generate embeddings via Workers AI")
    ap.add_argument(
        "--multi-contributor",
        action="store_true",
        help="Source has one subdirectory per contributor (e.g. raw-notes/). "
        "Top-level files are skipped; the first path segment becomes `contributor`.",
    )
    ap.add_argument(
        "--contributor",
        default="unknown",
        help="Contributor name to attach to every row when the source is single-author "
        "(default: 'unknown'). Ignored when --multi-contributor is set.",
    )
    ap.add_argument(
        "--exclude-categories",
        default="_root",
        help=(
            "Comma-separated category names to mark `excluded_from_oracle=true`. "
            "Embeddings are still generated for these rows; the Oracle should filter "
            "them out at query time (default: _root)"
        ),
    )
    ap.add_argument("--embed-batch-size", type=int, default=50)
    ap.add_argument(
        "--embed-max-chars",
        type=int,
        default=6000,
        help="Max chars of body text sent to the embedding model (default: 6000, ~1500 tokens)",
    )
    args = ap.parse_args()

    if not args.src.is_dir():
        print(f"error: {args.src} is not a directory", file=sys.stderr)
        return 2

    excluded_cats = {s.strip() for s in args.exclude_categories.split(",") if s.strip()}
    rows = collect_rows(args.src, excluded_cats, args.multi_contributor, args.contributor)

    if args.embed:
        env_path = find_dotenv(Path(__file__).resolve().parent)
        if env_path:
            load_dotenv(env_path)
        # Use a different name than CLOUDFLARE_API_TOKEN so wrangler — which
        # auto-loads .env from cwd — does not pick up this narrow AI-scoped
        # token and use it instead of its OAuth creds for R2/Pages commands.
        token = os.environ.get("CF_AI_TOKEN") or os.environ.get("CLOUDFLARE_API_TOKEN")
        account_id = os.environ.get("CLOUDFLARE_ACCOUNT_ID")
        if not token or not account_id:
            print(
                "error: CF_AI_TOKEN and CLOUDFLARE_ACCOUNT_ID must be set "
                "(found .env: " + (str(env_path) if env_path else "<none>") + ")",
                file=sys.stderr,
            )
            return 2
        add_embeddings(rows, token, account_id, args.embed_batch_size, args.embed_max_chars)

    table = build_table(rows, with_embeddings=args.embed)
    args.out.parent.mkdir(parents=True, exist_ok=True)
    pq.write_table(table, args.out, compression="zstd")

    size_kb = args.out.stat().st_size / 1024
    suffix = " (with embeddings)" if args.embed else ""
    print(f"wrote {table.num_rows} rows{suffix} ({size_kb:.1f} KB) -> {args.out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
