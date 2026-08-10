import os
import tempfile
import unittest
from pathlib import Path

FIXTURE = Path(__file__).resolve().parent / "fixtures" / "mini-ws"


class TestResolveWikilink(unittest.TestCase):
    def test_resolve_pitfalls_with_anchor(self):
        from lore_runtime.discover import resolve_wikilink
        result = resolve_wikilink("[[PITFALLS#1]]", str(FIXTURE))
        self.assertIsNotNone(result["resolved"])
        self.assertEqual(result["error"], None)

    def test_resolve_missing_file(self):
        from lore_runtime.discover import resolve_wikilink
        result = resolve_wikilink("[[NONEXISTENT#1]]", str(FIXTURE))
        self.assertIsNone(result["resolved"])
        self.assertIsNotNone(result["error"])
        self.assertIn("not found", result["error"])

    def test_resolve_missing_anchor(self):
        from lore_runtime.discover import resolve_wikilink
        result = resolve_wikilink("[[PITFALLS#999]]", str(FIXTURE))
        self.assertIsNotNone(result["resolved"])
        self.assertIsNotNone(result["error"])
        self.assertIn("anchor", result["error"])

    def test_resolve_without_extension(self):
        from lore_runtime.discover import resolve_wikilink
        result = resolve_wikilink("[[PITFALLS#1]]", str(FIXTURE))
        self.assertIsNotNone(result["resolved"])

    def test_resolve_no_anchor_resolves_file(self):
        from lore_runtime.discover import resolve_wikilink
        result = resolve_wikilink("[[PITFALLS]]", str(FIXTURE))
        self.assertIsNotNone(result["resolved"])
        self.assertIsNone(result["anchor"])
        self.assertIsNone(result["error"])

    def test_resolve_with_extension(self):
        from lore_runtime.discover import resolve_wikilink
        result = resolve_wikilink("[[PITFALLS.md#1]]", str(FIXTURE))
        self.assertIsNotNone(result["resolved"])
        self.assertEqual(result["error"], None)
        self.assertEqual(result["anchor"], "1. Auth middleware order")

    def test_resolve_header_anchor_case_insensitive(self):
        from lore_runtime.discover import resolve_wikilink
        result = resolve_wikilink("[[CONVENTIONS#conventions]]", str(FIXTURE))
        self.assertIsNotNone(result["resolved"])
        self.assertEqual(result["error"], None)
        self.assertEqual(result["anchor"], "Conventions")

    def test_resolve_from_nested_cwd_upward(self):
        from lore_runtime.discover import resolve_wikilink
        # cwd nested under the workspace still finds the root .pikb
        result = resolve_wikilink("[[PITFALLS#2]]", str(FIXTURE / "app"))
        self.assertIsNotNone(result["resolved"])
        self.assertEqual(result["error"], None)
        self.assertEqual(result["anchor"], "2. Unrelated trap")

    def test_resolve_bare_text_accepted(self):
        from lore_runtime.discover import resolve_wikilink
        result = resolve_wikilink("PITFALLS#1", str(FIXTURE))
        self.assertIsNotNone(result["resolved"])
        self.assertEqual(result["error"], None)


class TestCheckCrossrefs(unittest.TestCase):
    def test_check_crossrefs_returns_list(self):
        from lore_runtime.discover import check_crossrefs
        results = check_crossrefs(str(FIXTURE))
        self.assertIsInstance(results, list)
        # There should be at least one wikilink in the fixture
        # (the hotspot in CONTEXT.md has [[PITFALLS#1]])
        self.assertTrue(len(results) > 0)
        self.assertTrue(any(r["status"] == "ok" for r in results))

    def test_check_crossrefs_missing_dir_returns_empty(self):
        from lore_runtime.discover import check_crossrefs
        with tempfile.TemporaryDirectory() as tmp:
            results = check_crossrefs(os.path.join(tmp, "does-not-exist"))
        self.assertEqual(results, [])

    def test_check_crossrefs_ignores_bare_text(self):
        from lore_runtime.discover import check_crossrefs
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root / ".pikb").mkdir()
            (root / ".pikb" / "PITFALLS.md").write_text("## 1. Trap\n", encoding="utf-8")
            (root / ".pikb" / "NOTES.md").write_text(
                "bare PITFALLS#1 has no brackets and must be ignored\n",
                encoding="utf-8",
            )
            results = check_crossrefs(tmp)
        self.assertEqual(results, [])

    def test_check_crossrefs_reports_broken_anchor(self):
        from lore_runtime.discover import check_crossrefs
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root / ".pikb").mkdir()
            (root / ".pikb" / "PITFALLS.md").write_text("## 1. Trap\n", encoding="utf-8")
            (root / ".pikb" / "NOTES.md").write_text(
                "see [[PITFALLS#999]]\n", encoding="utf-8"
            )
            results = check_crossrefs(tmp)
        self.assertEqual(len(results), 1)
        self.assertEqual(results[0]["status"], "broken_anchor")
        self.assertEqual(results[0]["line"], 1)
        self.assertEqual(results[0]["wikilink"], "PITFALLS#999")

    def test_check_crossrefs_reports_broken_file(self):
        from lore_runtime.discover import check_crossrefs
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root / ".pikb").mkdir()
            (root / ".pikb" / "NOTES.md").write_text(
                "see [[MISSING#1]]\n", encoding="utf-8"
            )
            results = check_crossrefs(tmp)
        self.assertEqual(len(results), 1)
        self.assertEqual(results[0]["status"], "broken_file")


if __name__ == "__main__":
    unittest.main()
