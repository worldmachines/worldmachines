#!/usr/bin/env python3
"""Proves `--changed` is byte-identical to `--full`.

The incremental path exists to save time, never to produce different output, so
the only test that matters is: make a change, rebuild incrementally, then run a
full build and watch it write nothing. If the full build writes even one file,
the incremental pass missed a page and the deployed wiki would be stale.

    python3 website/scripts/verify_wiki_incremental.py

Each scenario is run and then undone, so the tree is left exactly as found.
"""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
NOTES = REPO / "raw-notes"
BUILD = [sys.executable, str(REPO / "website" / "scripts" / "build_wiki.py")]

# A well-connected note, so a change to it ripples through backlinks, the
# alongside lists and the wanted table at once.
SUBJECT = NOTES / "aneesh" / "concepts" / "divergence-machine.md"
# A wanted title several notes already link to; creating it must flip red links.
NEW_NOTE = NOTES / "aneesh" / "concepts" / "data-generation-process.md"


def run(args: list[str]) -> str:
    result = subprocess.run(BUILD + args, cwd=REPO, capture_output=True, text=True)
    if result.returncode != 0:
        print(result.stdout + result.stderr)
        raise SystemExit(f"build failed: {' '.join(args)}")
    return result.stdout.strip()


def written(line: str) -> int:
    for part in line.split(","):
        if "file(s) written" in part:
            return int(part.strip().split()[0])
    raise SystemExit(f"could not read file count from: {line}")


def check(name: str, changed: list[str]) -> bool:
    inc = run(["--changed", *changed, "--quiet"])
    full = run(["--full", "--quiet"])
    extra = written(full)
    status = "ok" if extra == 0 else "MISMATCH"
    print(f"  [{status}] {name}")
    print(f"       incremental: {inc.split('—', 1)[-1].strip()}")
    if extra:
        print(f"       full build then wrote {extra} more file(s) — incremental missed them")
    return extra == 0


def main() -> int:
    print("Baseline: full build, twice, must settle to zero writes.")
    run(["--full", "--quiet"])
    settle = written(run(["--full", "--quiet"]))
    print(f"  [{'ok' if settle == 0 else 'MISMATCH'}] deterministic ({settle} files on rebuild)")
    ok = settle == 0

    original = SUBJECT.read_text(encoding="utf-8")
    rel = str(SUBJECT.relative_to(REPO))

    # 1. Edit a note's prose and add a link to an existing note.
    SUBJECT.write_text(original + "\n\nA test paragraph linking [[modernity-machine]].\n",
                       encoding="utf-8")
    ok &= check("edit a note, add a link to an existing note", [rel])

    # 2. Add a link to a title nobody has written — a new wanted page appears.
    SUBJECT.write_text(original + "\n\nA test paragraph linking [[Some Unwritten Title]].\n",
                       encoding="utf-8")
    ok &= check("add a link to a title that does not exist", [rel])

    # 3. Revert.
    SUBJECT.write_text(original, encoding="utf-8")
    ok &= check("revert the note", [rel])

    # 4. Create a note that fulfils an existing wanted page: red links must turn
    #    live everywhere, and the wanted page must be deleted.
    NEW_NOTE.write_text(
        '---\nsummary: "Temporary note created by the incremental equivalence check."\n'
        "tags: [test-fixture]\n---\n\n# Data Generation Process\n\n"
        "Placeholder body linking [[divergence-machine]].\n",
        encoding="utf-8")
    ok &= check("create a note that fulfils a wanted page",
                [str(NEW_NOTE.relative_to(REPO))])

    # 5. Delete it again: the links must go back to red and the wanted page return.
    NEW_NOTE.unlink()
    ok &= check("delete that note again", [str(NEW_NOTE.relative_to(REPO))])

    # 6. Rename a note's title — every page that prints it must be redrawn.
    retitled = original.replace("# Divergence Machine", "# Divergence Machine (renamed)", 1)
    if retitled == original:
        raise SystemExit("fixture changed: expected an H1 to rewrite")
    SUBJECT.write_text(retitled, encoding="utf-8")
    ok &= check("rename a note's title", [rel])

    SUBJECT.write_text(original, encoding="utf-8")
    ok &= check("restore the title", [rel])

    # 7. A glossary entry inherits the audience of the notes named for it, so
    #    linking to one of those notes has to move the term page too.
    named = NOTES / "aneesh" / "concepts" / "Legibility.md"
    if named.exists():
        keep = named.read_text(encoding="utf-8")
        named.write_text(keep + "\n\nA test line linking [[divergence-machine]].\n",
                         encoding="utf-8")
        ok &= check("edit a note a glossary term is named for",
                    [str(named.relative_to(REPO))])
        named.write_text(keep, encoding="utf-8")
        ok &= check("revert it", [str(named.relative_to(REPO))])
    else:
        print("  [skip] no note named for a glossary term in this tree")

    # 8. A term page counts the notes tagged with its term, so a tag edit
    #    anywhere has to move it.
    tagged = original.replace("tags: [world-machines,", "tags: [legibility, world-machines,", 1)
    if tagged == original:
        raise SystemExit("fixture changed: expected a tags line to extend")
    SUBJECT.write_text(tagged, encoding="utf-8")
    ok &= check("add a tag that matches a glossary term", [rel])
    SUBJECT.write_text(original, encoding="utf-8")
    ok &= check("remove that tag again", [rel])

    print("\nPASS — incremental output is byte-identical to full."
          if ok else "\nFAIL — incremental and full disagree.")
    return 0 if ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
