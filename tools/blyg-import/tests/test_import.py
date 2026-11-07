"""Unit tests: python3 -m unittest discover -s tools/blyg-import/tests"""

import json
import sys
import tempfile
import unittest
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parent))

import corpus as C  # noqa: E402
from blyg_client import ApiError  # noqa: E402
from blyg_import import Importer, State, pace_for  # noqa: E402

AUTHORS = C.Authors(
    authors={"aneesh": {"name": "Aneesh Sathe", "blyg": "https://blyg.aneeshsathe.com/"},
             "venkat": {"name": "Venkatesh Rao", "blyg": None},
             "kyle": {"name": "Kyle Mathews", "blyg": None}},
    handles={"vgr": "venkat"},
)


def note(path, text):
    return C.parse_note(path, text)


def corpus(*pairs, max_chars=100000):
    notes = [note(p, t) for p, t in pairs]
    units = C.make_units(notes, max_chars)
    index = C.LinkIndex(notes)
    return notes, units, index


class FakeClient:
    """Records calls; an in-memory Studio that, like the real one, refuses to
    publish a [[id]] whose target is not published."""

    def __init__(self, fail_after=None):
        self.items, self.calls, self.fail_after, self.n = {}, [], fail_after, 0

    def _tick(self):
        self.n += 1
        if self.fail_after is not None and self.n > self.fail_after:
            raise RuntimeError("simulated crash")

    def create_item(self, content, kind):
        self._tick()
        item_id = C.fake_id(f"item{len(self.items)}")
        self.items[item_id] = {"content": content, "version": 0}
        self.calls.append(("create", item_id))
        return item_id

    def update_item(self, item_id, content):
        self._tick()
        self.items[item_id]["content"] = content
        self.calls.append(("patch", item_id))

    def publish_item(self, item_id, note=None):
        self._tick()
        import re
        for target in re.findall(r"\[\[([0-9a-z]{26})", self.items[item_id]["content"]):
            if self.items.get(target, {}).get("version", 0) == 0:
                raise ApiError(422, "item is a draft, not published", "POST", f"/items/{item_id}/publish")
        self.items[item_id]["version"] += 1
        self.items[item_id]["published"] = self.items[item_id]["content"]
        self.calls.append(("publish", item_id))
        return self.items[item_id]["version"]


class FrontmatterTest(unittest.TestCase):
    def test_strip_and_title_from_frontmatter(self):
        n = note("raw-notes/aneesh/x.md", "---\ntitle: \"Real Title\"\naliases:\n- 'Other'\n- Second\ntags: [a, b]\n---\n\n# Heading\n\nBody text.\n")
        self.assertEqual(n.title, "Real Title")
        self.assertEqual(n.aliases, ["Other", "Second"])
        self.assertEqual(n.front["tags"], ["a", "b"])
        self.assertEqual(n.body, "Body text.")  # leading H1 dropped; the item gets its own
        self.assertNotIn("---", n.body)

    def test_title_from_h1_then_filename(self):
        self.assertEqual(note("a/b/c.md", "# The H1\n\ntext").title, "The H1")
        self.assertEqual(note("a/b/some-file_name.md", "just text").title, "Some file name")
        self.assertEqual(note("a/b/c.md", "intro\n\n# Later H1\n").title, "Later H1")

    def test_no_frontmatter_and_wikilink_in_title(self):
        n = note("a/b/c.md", "# About [[x|Ex]]\nbody")
        self.assertEqual(n.title, "About Ex")
        self.assertEqual(n.front, {})

    def test_multiline_quoted_scalar(self):
        fm, body = C.parse_frontmatter("---\nsummary: \"one\n  two\"\nk: v\n---\nB")
        self.assertEqual(fm["summary"], "one two")
        self.assertEqual(fm["k"], "v")
        self.assertEqual(body, "B")


class LinkResolutionTest(unittest.TestCase):
    def setUp(self):
        self.notes, self.units, self.index = corpus(
            ("raw-notes/aneesh/concepts/legibility.md", "# Legibility (A)\n"),
            ("raw-notes/commons/glossary/legibility.md", "---\naliases: [Seeing like a state]\n---\n# Legibility\n"),
            ("raw-notes/kyle/legibility.md", "# Kyle legibility\n"),
            ("raw-notes/aneesh/concepts/a.md", "# A\n"),
            ("raw-notes/sean/s.md", "# Sean\n"),
            ("raw-notes/commons/glossary/modernity-machine.md", "# The Modernity Machine\n"),
        )
        self.by = {n.path: n for n in self.notes}

    def res(self, target, src):
        return self.index.resolve(target, self.by[src])

    def test_basename_case_insensitive_and_path(self):
        r = self.res("A", "raw-notes/sean/s.md")
        self.assertEqual((r.note.path, r.tier), ("raw-notes/aneesh/concepts/a.md", "basename"))
        self.assertEqual(self.res("concepts/a.md", "raw-notes/sean/s.md").note.path, "raw-notes/aneesh/concepts/a.md")

    def test_collision_rules(self):
        self.assertEqual(self.res("legibility", "raw-notes/aneesh/concepts/a.md").note.path,
                         "raw-notes/aneesh/concepts/legibility.md")      # same directory
        self.assertEqual(self.res("Legibility", "raw-notes/kyle/legibility.md").note.path,
                         "raw-notes/kyle/legibility.md")                 # (self)
        self.assertEqual(self.res("legibility", "raw-notes/sean/s.md").note.path,
                         "raw-notes/commons/glossary/legibility.md")     # commons
        self.assertIn(("basename", "legibility"), self.index.collisions)

    def test_title_alias_and_slug(self):
        r = self.res("the modernity machine", "raw-notes/sean/s.md")
        self.assertEqual((r.note.path, r.tier), ("raw-notes/commons/glossary/modernity-machine.md", "title"))
        r = self.res("Seeing like a state", "raw-notes/sean/s.md")
        self.assertEqual(r.tier, "title")
        r = self.res("modernity machine", "raw-notes/sean/s.md")
        self.assertEqual(r.tier, "slug")
        self.assertIsNone(self.res("nothing here", "raw-notes/sean/s.md").note)

    def test_rewrite_forms(self):
        r = C.Renderer(self.index, C.units_by_note(self.units))
        src = self.by["raw-notes/sean/s.md"]
        ids = lambda k: C.fake_id(k)
        aid = C.fake_id("raw-notes/aneesh/concepts/a.md")
        stats = C.LinkStats()
        out = r.rewrite_links("[[a]] [[a|alias here]] [[a#Sec]] [[missing|Shown]] [[nope]] `[[a]]` ![[pic.png]] [TK]",
                              src, ids, stats)
        self.assertEqual(out, f"[[{aid} | a]] [[{aid} | alias here]] [[{aid} | a]] Shown nope `[[a]]` "
                              r"*(embedded file not imported: pic.png)* \[TK\]")
        self.assertEqual(stats.total, 5)
        self.assertEqual(sum(stats.unresolved.values()), 2)
        self.assertEqual(stats.headings_dropped, 1)
        self.assertEqual(stats.tk_escaped, 1)

    def test_fenced_code_untouched_and_unknown_id_plain(self):
        r = C.Renderer(self.index, C.units_by_note(self.units))
        src = self.by["raw-notes/sean/s.md"]
        text = "```\n[[a]]\n```\n[[a]]"
        out = r.rewrite_links(text, src, lambda k: None)
        self.assertEqual(out, "```\n[[a]]\n```\na")

    def test_wrapped_link_and_multiline_code_span(self):
        r = C.Renderer(self.index, C.units_by_note(self.units))
        src = self.by["raw-notes/sean/s.md"]
        aid = C.fake_id("raw-notes/aneesh/concepts/a.md")
        self.assertEqual(r.rewrite_links("on [[a|the\nproject]] x", src, C.fake_id), f"on [[{aid} | the project]] x")
        self.assertEqual(r.rewrite_links("`code\n[[a]]` [[a]]", src, C.fake_id), f"`code\n[[a]]` [[{aid} | a]]")
        self.assertEqual(r.rewrite_links("[[a\n\nb]]", src, C.fake_id), "[[a\n\nb]]")  # never across a blank line

    def test_self_link_is_plain(self):
        r = C.Renderer(self.index, C.units_by_note(self.units))
        src = self.by["raw-notes/sean/s.md"]
        self.assertEqual(r.rewrite_links("[[s]] [[#Top]]", src, C.fake_id), "s Top")

    def test_label_never_closes_early(self):
        self.assertEqual(C.blyg_link("x" * 26, "a  b\n c"), "[[" + "x" * 26 + " | a b c]]")
        self.assertTrue(C.label_text("ends]").endswith("] "))


class AttributionTest(unittest.TestCase):
    def test_personal_dirs(self):
        self.assertEqual(C.render_byline(AUTHORS.author_for(note("raw-notes/aneesh/x.md", "x"))),
                         "*By [Aneesh Sathe](https://blyg.aneeshsathe.com/)*")
        self.assertEqual(C.render_byline(AUTHORS.author_for(note("raw-notes/kyle/sub/x.md", "x"))),
                         "*By Kyle Mathews*")

    def test_commons_wiki_and_unknown(self):
        for p in ("raw-notes/commons/glossary/x.md", "wiki/decisions/x.md", "raw-notes/README.md", "raw-notes/zed/x.md"):
            self.assertEqual(C.render_byline(AUTHORS.author_for(note(p, "x"))), "", p)

    def test_contributions_use_frontmatter_handle(self):
        n = note("raw-notes/commons/contributions/e/e-p01.md", "---\nauthor: \"vgr\"\n---\n# E\n")
        self.assertEqual(C.render_byline(AUTHORS.author_for(n)), "*By Venkatesh Rao*")
        n = note("raw-notes/commons/reading/b/x.md", "---\nauthor: \"vgr\"\n---\n# E\n")
        self.assertEqual(C.render_byline(AUTHORS.author_for(n)), "")

    def test_ai_byline_for_pipeline_notes_only(self):
        lines = {"raw-notes/commons/reading/": "*AI reading*", "raw-notes/commons/synthesis/": "*AI canon*",
                 "_comment": "ignored"}
        self.assertEqual(C.ai_byline("raw-notes/commons/reading/book/ch1.md", lines), "*AI reading*")
        self.assertEqual(C.ai_byline("raw-notes/commons/synthesis/x.md", lines), "*AI canon*")
        for p in ("raw-notes/commons/glossary/x.md", "raw-notes/commons/contributions/e/e-p01.md",
                  "raw-notes/aneesh/x.md", "wiki/x.md"):
            self.assertEqual(C.ai_byline(p, lines), "", p)

    def test_real_config_labels_the_four_pipeline_areas(self):
        cfg = json.loads((Path(__file__).resolve().parent.parent / "config.json").read_text())
        keys = sorted(k for k in cfg["ai_bylines"] if not k.startswith("_"))
        self.assertEqual(keys, ["raw-notes/commons/entities/", "raw-notes/commons/reading/",
                                "raw-notes/commons/summaries/", "raw-notes/commons/synthesis/"])
        for k in keys:
            self.assertIn("AI", cfg["ai_bylines"][k])
            self.assertIn("not by a member", cfg["ai_bylines"][k])

    def test_byline_placed_under_title(self):
        notes, units, index = corpus(("raw-notes/aneesh/x.md", "# X\n\nBody"))
        r = C.Renderer(index, C.units_by_note(units))
        text = r.render(units[0], C.render_byline(AUTHORS.author_for(notes[0])), C.fake_id)
        self.assertEqual(text, "# X\n\n*By [Aneesh Sathe](https://blyg.aneeshsathe.com/)*\n\nBody\n")

    def test_real_authors_json_has_names_only(self):
        data = json.loads((HERE.parent / "authors.json").read_text())
        self.assertNotIn("@", json.dumps(data["authors"]))
        for v in data["authors"].values():
            self.assertEqual(set(v), {"name", "blyg"})


class SplitTest(unittest.TestCase):
    def test_small_note_is_one_part(self):
        self.assertEqual(C.split_body("short", 5000), ["short"])

    def test_split_respects_budget_and_fences(self):
        para = ("word " * 150).strip()
        body = "\n\n".join([para] * 30 + ["```\ncode\n\nmore code\n```"] + [para] * 5)
        parts = C.split_body(body, 4000)
        self.assertGreater(len(parts), 1)
        for p in parts:
            self.assertLessEqual(len(p), 4000 - C.SPLIT_OVERHEAD)
            self.assertEqual(p.count("```") % 2, 0)
        self.assertEqual("".join(body.split()), "".join("".join(parts).split()))

    def test_one_huge_line(self):
        parts = C.split_body("x" * 10000, 3000)
        self.assertEqual("".join(parts), "x" * 10000)
        self.assertTrue(all(len(p) <= 1500 for p in parts))

    def test_parts_are_linked(self):
        para = ("word " * 150).strip()
        notes, units, index = corpus(("raw-notes/kyle/big.md", "# Big\n\n" + "\n\n".join([para] * 20)), max_chars=4000)
        self.assertGreater(len(units), 1)
        self.assertEqual(units[0].key, "raw-notes/kyle/big.md")
        self.assertEqual(units[1].key, "raw-notes/kyle/big.md#part-2")
        r = C.Renderer(index, C.units_by_note(units))
        mid = r.render(units[1], "", C.fake_id)
        self.assertIn(f"Previous: [[{C.fake_id(units[0].key)} | part 1]]", mid)
        self.assertIn(f"# Big (part 2 of {len(units)})", mid)
        for u in units:
            self.assertLessEqual(len(r.render(u, "*By Kyle Mathews*", C.fake_id)), 4000)


class StateTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.state_path = Path(self.tmp.name) / "state.json"
        # a <-> b is a cycle; c -> a; d is alone.
        self.notes, self.units, self.index = corpus(
            ("raw-notes/aneesh/a.md", "# A\n\nsee [[b]]"),
            ("raw-notes/aneesh/b.md", "# B\n\nsee [[a]]"),
            ("raw-notes/commons/c.md", "# C\n\nsee [[a]] and [[missing]]"),
            ("raw-notes/kyle/d.md", "# D\n"),
        )

    def tearDown(self):
        self.tmp.cleanup()

    def importer(self, client, authors=AUTHORS):
        return Importer(self.units, self.index, authors, State(self.state_path, "http://x/api"), client, log=lambda *a: None)

    def test_publish_resolves_cycles_and_is_idempotent(self):
        client = FakeClient()
        imp = self.importer(client)
        imp.sync(self.units, publish=True)
        self.assertEqual(imp.counts["error"], 0)
        state = json.loads(self.state_path.read_text())["items"]
        ida, idb = state["raw-notes/aneesh/a.md"]["id"], state["raw-notes/aneesh/b.md"]["id"]
        self.assertIn(f"[[{idb} | b]]", client.items[ida]["published"])
        self.assertIn(f"[[{ida} | a]]", client.items[idb]["published"])
        creates = [c for c in client.calls if c[0] == "create"]
        self.assertEqual(len(creates), 4)
        first = len(client.calls)
        # Re-run: nothing to do.
        imp2 = self.importer(client)
        imp2.sync(self.units, publish=True)
        self.assertEqual(len(client.calls), first)
        self.assertEqual(imp2.counts, {"create": 0, "patch": 0, "publish": 0, "error": 0})

    def test_drafts_only(self):
        client = FakeClient()
        imp = self.importer(client)
        imp.sync(self.units, publish=False)
        self.assertFalse(any(c[0] == "publish" for c in client.calls))
        ida = json.loads(self.state_path.read_text())["items"]["raw-notes/aneesh/a.md"]["id"]
        idb = json.loads(self.state_path.read_text())["items"]["raw-notes/aneesh/b.md"]["id"]
        self.assertIn(f"[[{idb} | b]]", client.items[ida]["content"])  # drafts may link drafts

    def test_crash_resumes_without_duplicates(self):
        client = FakeClient(fail_after=5)
        with self.assertRaises(RuntimeError):
            self.importer(client).sync(self.units, publish=True)
        client.fail_after = None
        imp = self.importer(client)
        imp.sync(self.units, publish=True)
        self.assertEqual(len([c for c in client.calls if c[0] == "create"]), 4)
        self.assertEqual(len(client.items), 4)
        for e in json.loads(self.state_path.read_text())["items"].values():
            self.assertGreaterEqual(e["published_version"], 1)

    def test_update_attribution_touches_only_changed_bylines(self):
        client = FakeClient()
        self.importer(client).sync(self.units, publish=True)
        changed = C.Authors(authors={**AUTHORS.authors, "kyle": {"name": "Kyle Mathews", "blyg": "https://k.example/blyg/"}},
                            handles=AUTHORS.handles)
        imp = self.importer(client, changed)
        state = imp.state.items
        selected = [u for u in self.units if state[u.key]["byline_sha"] != C.sha(imp.byline(u))]
        self.assertEqual([u.key for u in selected], ["raw-notes/kyle/d.md"])
        before = len(client.calls)
        imp.sync(selected, publish=False, republish_published=True)
        self.assertEqual([c[0] for c in client.calls[before:]], ["patch", "publish"])
        did = state["raw-notes/kyle/d.md"]["id"]
        self.assertIn("*By [Kyle Mathews](https://k.example/blyg/)*", client.items[did]["published"])

    def test_plan_writes_matches_real_run_and_writes_nothing(self):
        imp = self.importer(None)
        plan = imp.plan_writes(self.units, publish=True)
        self.assertFalse(self.state_path.exists())  # planning never touches the state file
        self.assertEqual(imp.state.items, {})
        client = FakeClient()
        real = self.importer(client)
        real.sync(self.units, publish=True)
        self.assertEqual(plan["create"], real.counts["create"])
        self.assertEqual(plan["patch"], real.counts["patch"])
        self.assertEqual(plan["publish"], real.counts["publish"])
        self.assertEqual(plan["total"], len(client.calls))
        # After the run, the plan is empty: a resumed run makes no writes.
        self.assertEqual(self.importer(client).plan_writes(self.units, publish=True)["total"], 0)

    def test_pace_for_target_hours(self):
        self.assertAlmostEqual(pace_for(8, 6000), 4.8)
        self.assertEqual(pace_for(1, 6000), 1.1)  # never faster than the write budget
        self.assertEqual(pace_for(8, 0), 1.1)

    def test_state_bound_to_api_base(self):
        State(self.state_path, "http://x/api").save()
        with self.assertRaises(SystemExit):
            State(self.state_path, "http://other/api")


if __name__ == "__main__":
    unittest.main()
