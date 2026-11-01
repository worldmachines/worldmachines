#!/usr/bin/env python3
"""Publish the World Machines notes (raw-notes/**, wiki/**) as blyg items.

Dry run by default. See README.md in this directory.

    python3 tools/blyg-import/blyg_import.py                       # dry run, full corpus stats + sample
    BLYG_TOKEN=... python3 tools/blyg-import/blyg_import.py --execute --publish --limit 50 --only 'raw-notes/commons/glossary/*'
"""

from __future__ import annotations

import argparse
import copy
import datetime
import fnmatch
import json
import os
import sys
from pathlib import Path
from typing import Optional

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))

import corpus as C  # noqa: E402
from blyg_client import ApiError, BlygClient  # noqa: E402

REPO_ROOT = HERE.parent.parent


# ─── State ───────────────────────────────────────────────────────────────────

class State:
    """note/unit key -> {id, content_sha, byline_sha, published_version, published_sha}.

    content_sha    sha256 of the item's working copy as we last wrote it
    published_sha  sha256 of the text of the latest version we published
    byline_sha     sha256 of the byline in the last text we wrote
    Saved (atomically) after every successful API call.
    """

    def __init__(self, path: Path, api_base: str):
        self.path = path
        self.data = {"version": 1, "api_base": api_base, "items": {}}
        if path.exists():
            self.data = json.loads(path.read_text())
            if self.data.get("api_base") and self.data["api_base"].rstrip("/") != api_base.rstrip("/"):
                raise SystemExit(
                    f"state file {path} belongs to {self.data['api_base']}, not {api_base}. "
                    "Use --state to pick a state file for this blyg.")
            self.data["api_base"] = api_base

    @property
    def items(self) -> dict:
        return self.data["items"]

    def save(self) -> None:
        tmp = self.path.with_suffix(self.path.suffix + ".tmp")
        tmp.write_text(json.dumps(self.data, indent=1, sort_keys=True) + "\n")
        os.replace(tmp, self.path)

    def id(self, key: str) -> Optional[str]:
        e = self.items.get(key)
        return e["id"] if e else None

    def published_id(self, key: str) -> Optional[str]:
        e = self.items.get(key)
        return e["id"] if e and e.get("published_version") else None


# ─── The import ──────────────────────────────────────────────────────────────

class Importer:
    def __init__(self, units: list[C.Unit], index: C.LinkIndex, authors: C.Authors, state: State,
                 client: Optional[BlygClient], kind: str = "thread", publish_note: Optional[str] = None,
                 republish_note: Optional[str] = None, log=print):
        self.units = units
        self.by_key = {u.key: u for u in units}
        self.renderer = C.Renderer(index, C.units_by_note(units))
        self.authors = authors
        self.state = state
        self.client = client
        self.kind = kind
        self.publish_note = publish_note
        self.republish_note = republish_note
        self.log = log
        self.counts = {"create": 0, "patch": 0, "publish": 0, "error": 0}
        self.errors: list[str] = []

    def byline(self, unit: C.Unit) -> str:
        return C.render_byline(self.authors.author_for(unit.note))

    def render(self, unit: C.Unit, id_of, stats=None, targets=None) -> str:
        return self.renderer.render(unit, self.byline(unit), id_of, stats, targets)

    def order(self, selected: list[C.Unit]) -> list[C.Unit]:
        """Link targets before the notes that link to them (DFS post-order), so
        that most links resolve at first publish. Cycles are broken arbitrarily
        and fixed by the second publish round."""
        keys = {u.key for u in selected}
        edges: dict[str, list[str]] = {}
        for u in selected:
            targets: set = set()
            self.render(u, C.fake_id, targets=targets)
            edges[u.key] = sorted(t for t in targets if t in keys and t != u.key)
        done, out = set(), []
        for root in sorted(keys):
            if root in done:
                continue
            stack = [(root, iter(edges[root]))]
            done.add(root)
            while stack:
                node, it = stack[-1]
                nxt = next((t for t in it if t not in done), None)
                if nxt is None:
                    stack.pop()
                    out.append(node)
                else:
                    done.add(nxt)
                    stack.append((nxt, iter(edges[nxt])))
        return [self.by_key[k] for k in out]

    # Returns (ok, result); the caller writes state on success.
    def _call(self, what: str, unit: C.Unit, fn):
        try:
            result = fn()
        except ApiError as e:
            if e.status in (401, 403):
                raise SystemExit(f"auth failed ({e.status}) on {what} {unit.key}: {e.body[:300]}")
            self.counts["error"] += 1
            msg = f"{what} {unit.key}: HTTP {e.status} {e.body[:300]}"
            self.errors.append(msg)
            self.log("  ERROR " + msg)
            entry = self.state.items.get(unit.key)
            if entry is not None:
                entry["last_error"] = msg
                self.state.save()
            return False, None
        self.counts[what] += 1
        return True, result

    def _create(self, unit: C.Unit) -> None:
        content = self.render(unit, self.state.id)
        ok, item_id = self._call("create", unit, lambda: self.client.create_item(content, self.kind))
        if not ok:
            return
        self.state.items[unit.key] = {"id": item_id, "content_sha": C.sha(content),
                                      "byline_sha": C.sha(self.byline(unit)),
                                      "published_version": 0, "published_sha": None}
        self.state.save()
        self.log(f"  created {item_id}  {unit.key}")

    def _write(self, unit: C.Unit, content: str) -> bool:
        entry = self.state.items[unit.key]
        if entry.get("content_sha") == C.sha(content):
            return True
        ok, _ = self._call("patch", unit, lambda: self.client.update_item(entry["id"], content))
        if not ok:
            return False
        entry["content_sha"] = C.sha(content)
        entry["byline_sha"] = C.sha(self.byline(unit))
        entry.pop("last_error", None)
        self.state.save()
        self.log(f"  patched {entry['id']}  {unit.key}")
        return True

    def _publish(self, unit: C.Unit, content: str) -> None:
        entry = self.state.items[unit.key]
        note = self.republish_note if entry.get("published_version") else self.publish_note
        ok, version = self._call("publish", unit, lambda: self.client.publish_item(entry["id"], note))
        if not ok:
            return
        entry["published_version"] = version
        entry["published_sha"] = C.sha(content)
        entry.pop("last_error", None)
        self.state.save()
        self.log(f"  published v{version} {entry['id']}  {unit.key}")

    def sync(self, selected: list[C.Unit], publish: bool, republish_published: bool = False) -> None:
        order = self.order(selected)
        for u in order:
            if u.key not in self.state.items:
                self._create(u)
        rounds = 2 if (publish or republish_published) else 1
        for rnd in range(rounds):
            for u in order:
                entry = self.state.items.get(u.key)
                if entry is None:
                    continue
                go_public = publish or (republish_published and entry.get("published_version"))
                if not go_public:
                    self._write(u, self.render(u, self.state.id))
                    continue
                # Only links whose targets are already published: an unpublished
                # target is a publish error (Studio resolveTarget), so it is
                # written as plain text now and linked in the next round/run.
                content = self.render(u, self.state.published_id)
                if entry.get("published_version") and entry.get("published_sha") == C.sha(content):
                    continue
                if self._write(u, content):
                    self._publish(u, content)

    def plan_writes(self, selected: list[C.Unit], publish: bool, republish_published: bool = False) -> dict:
        """Exact write plan: replays sync() against a throwaway copy of the state
        with a client that only counts. Creates, patches and publishes, including
        the second-round republishes. Nothing is written, to the blyg or to disk."""
        planner = Importer(self.units, self.renderer.index, self.authors, _ScratchState(self.state),
                           _CountingClient(), kind=self.kind, publish_note=self.publish_note,
                           republish_note=self.republish_note, log=lambda *a: None)
        planner.renderer = self.renderer
        planner.sync(selected, publish=publish, republish_published=republish_published)
        c = planner.counts
        return {"create": c["create"], "patch": c["patch"], "publish": c["publish"],
                "total": c["create"] + c["patch"] + c["publish"]}

    def pending(self, selected: list[C.Unit]) -> dict:
        """What an --execute run would do first (creates are exact; edits are a floor)."""
        creates = sum(1 for u in selected if u.key not in self.state.items)
        changed = sum(1 for u in selected if u.key in self.state.items and
                      self.state.items[u.key].get("content_sha") != C.sha(self.render(u, self.state.id)))
        return {"create": creates, "changed": changed}


class _ScratchState(State):
    """An in-memory copy of a State; save() is a no-op."""

    def __init__(self, src: State):
        self.path = src.path
        self.data = copy.deepcopy(src.data)

    def save(self) -> None:
        pass


class _CountingClient:
    """Stands in for BlygClient when planning: every call succeeds, nothing is sent."""

    def __init__(self):
        self.n = 0

    def create_item(self, content, kind):
        self.n += 1
        return C.fake_id(f"plan-{self.n}")

    def update_item(self, item_id, content):
        pass

    def publish_item(self, item_id, note=None):
        return 1


MIN_WRITE_INTERVAL = 1.1  # the 60/min delegated write budget, with margin


def pace_for(target_hours: float, planned_writes: int) -> float:
    """Seconds between writes so that planned_writes take about target_hours, never
    faster than the write budget allows."""
    if planned_writes <= 0:
        return MIN_WRITE_INTERVAL
    return max(MIN_WRITE_INTERVAL, target_hours * 3600.0 / planned_writes)


# ─── Stats and reporting ─────────────────────────────────────────────────────

def corpus_stats(imp: Importer, units: list[C.Unit]) -> C.LinkStats:
    stats = C.LinkStats()
    for u in units:
        imp.render(u, C.fake_id, stats=stats)
    return stats


def pct(n: int, d: int) -> str:
    return f"{100.0 * n / d:.1f}%" if d else "n/a"


def print_stats(notes, units, stats: C.LinkStats, index: C.LinkIndex, top: int = 25) -> dict:
    total = stats.total
    base = stats.by_tier["basename"]
    title = stats.by_tier["title"]
    slug = stats.by_tier["slug"]
    resolved = base + title + slug
    split = [n for n in {u.note.path: u for u in units if u.parts > 1}]
    chars = sum(len(u.body) for u in units)
    print(f"notes: {len(notes)}   items after splitting: {len(units)}   body chars: {chars:,}")
    if split:
        print(f"split notes ({len(split)}): " + ", ".join(
            f"{p} -> {next(u.parts for u in units if u.note.path == p)} parts" for p in split))
    print(f"wikilinks in bodies: {total:,}")
    print(f"  resolved by basename:       {base:6,}  {pct(base, total)}")
    print(f"  + by title/alias:           {title:6,}  cumulative {pct(base + title, total)}")
    print(f"  + by slug (punctuation):    {slug:6,}  cumulative {pct(resolved, total)}")
    print(f"  self/same-note links (plain text): {stats.self_links:,}")
    print(f"  unresolved -> plain text:   {sum(stats.unresolved.values()):6,}  "
          f"{pct(sum(stats.unresolved.values()), total)}  ({len(stats.unresolved):,} distinct targets)")
    print(f"  #heading anchors dropped (link goes to the note): {stats.headings_dropped:,}")
    print(f"frontmatter connects/supports/contradicts links (footer): {stats.footer_links:,}, "
          f"resolved {pct(stats.footer_resolved, stats.footer_links)}")
    print(f"embeds: note embeds -> links {stats.embeds_note}, file embeds omitted {sum(stats.embeds_file.values())}"
          f" {dict(stats.embeds_file) or ''}")
    print(f"TK tokens escaped: {stats.tk_escaped}")
    print(f"\ntop {top} unresolved targets:")
    for t, c in stats.unresolved.most_common(top):
        print(f"  {c:5}  {t}")
    by_tier: dict[str, list] = {}
    for (tier, key), entry in index.collisions.items():
        by_tier.setdefault(tier, []).append((key, entry))
    dup_bases = {k: sorted(n.path for n in v) for k, v in index.by_base.items() if len(v) > 1}
    print(f"\nbasenames shared by several notes: {len(dup_bases)}")
    for k, paths in sorted(dup_bases.items()):
        print(f"  {k}: {', '.join(paths)}")
    print("\nname collisions met by links (several notes answer one link target):")
    for tier in ("basename", "title", "slug"):
        rows = by_tier.get(tier, [])
        print(f"  {tier}: {len(rows)} targets")
        for key, entry in sorted(rows)[: (100 if tier == "basename" else 8)]:
            print(f"    [[{key}]]  candidates: {', '.join(entry['candidates'])}")
            for (src, chosen, rule), n in sorted(entry["decisions"].items()):
                print(f"      from {src or '-'}/ ({n}x) -> {chosen}  [{rule}]")
    return {
        "notes": len(notes), "items": len(units), "split_notes": split,
        "links": total, "resolved": {"basename": base, "title": title, "slug": slug},
        "self_links": stats.self_links, "unresolved": dict(stats.unresolved.most_common()),
        "headings_dropped": stats.headings_dropped, "footer_links": stats.footer_links,
        "footer_resolved": stats.footer_resolved, "embeds_note": stats.embeds_note,
        "embeds_file": dict(stats.embeds_file), "tk_escaped": stats.tk_escaped,
        "collisions": [{"tier": t, "target": k, "candidates": e["candidates"],
                        "decisions": [{"from": s, "chosen": c, "rule": r, "count": n}
                                      for (s, c, r), n in sorted(e["decisions"].items())]}
                       for (t, k), e in sorted(index.collisions.items())],
    }


# ─── CLI ─────────────────────────────────────────────────────────────────────

def load_config(path: Path) -> dict:
    cfg = json.loads(path.read_text())
    cfg.pop("_comment", None)
    return cfg


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    mode = ap.add_mutually_exclusive_group()
    mode.add_argument("--dry-run", action="store_true", help="no writes (the default)")
    mode.add_argument("--execute", action="store_true", help="write to the blyg (needs BLYG_TOKEN)")
    ap.add_argument("--publish", action="store_true", help="publish items (else leave drafts)")
    ap.add_argument("--update-attribution", action="store_true",
                    help="only items whose byline changed (after editing authors.json); republishes published ones")
    ap.add_argument("--limit", type=int, help="only the first N selected notes (path order)")
    ap.add_argument("--only", action="append", default=[], metavar="GLOB",
                    help="only notes whose repo path matches GLOB (repeatable)")
    ap.add_argument("--state", type=Path, default=HERE / "state.json")
    ap.add_argument("--config", type=Path, default=HERE / "config.json")
    ap.add_argument("--authors", type=Path, default=HERE / "authors.json")
    ap.add_argument("--root", type=Path, default=REPO_ROOT, help="repo root")
    ap.add_argument("--api-base", help="overrides BLYG_API_BASE and config")
    ap.add_argument("--interval", "--write-interval", dest="interval", type=float,
                    help="seconds between writes (default from config); overrides --target-hours")
    ap.add_argument("--target-hours", type=float, metavar="H",
                    help="stretch the run to about H hours: interval = max(1.1, H*3600 / planned writes)")
    ap.add_argument("--sample", type=int, default=2, help="dry run: how many transformed notes to print")
    ap.add_argument("--report", type=Path, help="write full stats (unresolved, collisions) as JSON")
    ap.add_argument("--quiet-stats", action="store_true", help="skip the corpus statistics")
    args = ap.parse_args(argv)

    cfg = load_config(args.config)
    api_base = (args.api_base or os.environ.get("BLYG_API_BASE") or cfg["api_base"]).rstrip("/")
    notes = C.load_corpus(args.root, cfg["include"], cfg.get("exclude", []))
    units = C.make_units(notes, int(cfg["max_chars"]))
    index = C.LinkIndex(notes, slug_matching=cfg.get("slug_matching", True),
                        commons_top=f"raw-notes/{cfg.get('commons_dir', 'commons')}")
    authors = C.Authors.load(args.authors, commons_dir=cfg.get("commons_dir", "commons"),
                             contributions_dir=cfg.get("contributions_dir", "raw-notes/commons/contributions"))
    state = State(args.state, api_base)

    # Selection.
    chosen = [n for n in notes if not args.only or any(fnmatch.fnmatch(n.path, g) for g in args.only)]
    if args.limit is not None:
        chosen = chosen[: args.limit]
    chosen_paths = {n.path for n in chosen}
    selected = [u for u in units if u.note.path in chosen_paths]

    imp = Importer(units, index, authors, state, None, kind=cfg.get("kind", "thread"),
                   publish_note=cfg.get("publish_note"), republish_note=cfg.get("republish_note"))
    if args.update_attribution:
        selected = [u for u in selected if u.key in state.items
                    and state.items[u.key].get("byline_sha") != C.sha(imp.byline(u))]

    if not args.quiet_stats:
        print(f"== corpus ({args.root}) ==")
        report = print_stats(notes, units, corpus_stats(imp, units), index)
        if args.report:
            args.report.write_text(json.dumps(report, indent=1) + "\n")
            print(f"\nfull report: {args.report}")

    print(f"\n== selection: {len(chosen)} notes, {len(selected)} items"
          f"{' (byline changed)' if args.update_attribution else ''} -> {api_base} ==")
    plan = imp.pending(selected)
    print(f"to create: {plan['create']}   existing items whose text changed: {plan['changed']}   "
          "publish: " + ("yes" if args.publish else
                            "republish items already published" if args.update_attribution else "no (drafts)"))

    writes = imp.plan_writes(selected, publish=args.publish, republish_published=args.update_attribution)
    if args.interval is not None:
        interval, why = args.interval, "--write-interval"
    elif args.target_hours is not None:
        interval, why = pace_for(args.target_hours, writes["total"]), f"--target-hours {args.target_hours:g}"
    else:
        interval, why = float(cfg.get("write_interval_seconds", MIN_WRITE_INTERVAL)), "config"
    secs = writes["total"] * interval
    eta = datetime.datetime.now() + datetime.timedelta(seconds=secs)
    print(f"planned writes: {writes['total']} (create {writes['create']}, patch {writes['patch']}, "
          f"publish {writes['publish']})   interval: {interval:.2f}s ({why})   "
          f"duration ~{secs / 3600:.2f}h   ETA ~{eta:%Y-%m-%d %H:%M} local", flush=True)

    if not args.execute:
        sample = sorted(selected, key=lambda u: -u.body.count("[["))[: args.sample]
        for u in sample:
            print(f"\n----- sample: {u.key} (ids are stand-ins) -----")
            text = imp.render(u, lambda k: state.id(k) or C.fake_id(k))
            print(text if len(text) < 4000 else text[:4000] + f"\n[... {len(text) - 4000:,} more chars]")
        print("\nDry run: nothing was written. Add --execute to write.")
        return 0

    token = os.environ.get("BLYG_TOKEN")
    if not token:
        print("BLYG_TOKEN is not set.", file=sys.stderr)
        return 2
    imp.client = BlygClient(api_base, token, write_interval=interval)
    imp.sync(selected, publish=args.publish, republish_published=args.update_attribution)
    c = imp.counts
    print(f"\ndone: created {c['create']}, patched {c['patch']}, published {c['publish']}, errors {c['error']}")
    for e in imp.errors[:20]:
        print("  " + e)
    return 1 if c["error"] else 0


if __name__ == "__main__":
    sys.exit(main())
