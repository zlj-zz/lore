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
            (root / ".pikb" / "PITFALLS.md").write_text(
                "## 1. Trap\n", encoding="utf-8"
            )
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
            (root / ".pikb" / "PITFALLS.md").write_text(
                "## 1. Trap\n", encoding="utf-8"
            )
            (root / ".pikb" / "NOTES.md").write_text(
                "see [[PITFALLS#999]]\n", encoding="utf-8"
            )
            results = check_crossrefs(tmp)
        self.assertEqual(len(results), 1)
        self.assertEqual(results[0]["status"], "broken_anchor")
        self.assertEqual(results[0]["line"], 1)
        self.assertEqual(results[0]["wikilink"], "PITFALLS#999")

    def test_check_crossrefs_resolves_from_source_not_cwd(self):
        # A nested workspace's KB file must resolve against its own .pikb/,
        # even when the scan root (cwd) sits outside that workspace.
        from lore_runtime.discover import check_crossrefs

        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            outer = root / "outer"
            inner = outer / "inner"
            (inner / ".pikb").mkdir(parents=True)
            (inner / ".pikb" / "PITFALLS.md").write_text(
                "## 1. Trap\n", encoding="utf-8"
            )
            ctx_dir = inner / "app" / ".pi" / "kb"
            ctx_dir.mkdir(parents=True)
            (ctx_dir / "CONTEXT.md").write_text(
                "see [[PITFALLS#1]]\n", encoding="utf-8"
            )
            results = check_crossrefs(str(outer))
        self.assertEqual(len(results), 1)
        self.assertEqual(results[0]["status"], "ok")

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


class TestMarkdownLinks(unittest.TestCase):
    def test_resolve_relative_md_ok(self):
        from lore_runtime.discover import resolve_markdown_link

        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root / "PITFALLS.md").write_text("## 1. Trap\n", encoding="utf-8")
            r = resolve_markdown_link("./PITFALLS.md#1-trap", root)
        self.assertFalse(r["skip"])
        self.assertIsNone(r["error"])

    def test_resolve_relative_md_missing_file(self):
        from lore_runtime.discover import resolve_markdown_link

        r = resolve_markdown_link("./NOPE.md", Path("/tmp"))
        self.assertFalse(r["skip"])
        self.assertIn("not found", r["error"])

    def test_resolve_relative_md_broken_anchor(self):
        from lore_runtime.discover import resolve_markdown_link

        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root / "MAP.md").write_text("## 5. Menu\n", encoding="utf-8")
            r = resolve_markdown_link("./MAP.md#4-menu", root)
        self.assertIsNotNone(r["resolved"])
        self.assertIn("anchor", r["error"])

    def test_trailing_hyphen_anchor_tolerated(self):
        # Emoji headings generate a trailing hyphen in the anchor; accept both.
        from lore_runtime.discover import resolve_markdown_link

        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root / "MAP.md").write_text(
                "### 5. 菜单 CUD 与管理查询 ✅\n", encoding="utf-8"
            )
            r = resolve_markdown_link("./MAP.md#5-菜单-cud-与管理查询-", root)
        self.assertIsNone(r["error"])

    def test_skip_external_and_non_md(self):
        from lore_runtime.discover import resolve_markdown_link

        for url in (
            "https://x.com/a.md",
            "/abs/a.md",
            "#anchor",
            "./img.png",
            "mailto:a@b",
        ):
            self.assertTrue(resolve_markdown_link(url, Path("/tmp"))["skip"], url)

    def test_github_slug_keeps_cjk_drops_punct(self):
        from lore_runtime.discover import github_slug

        # Comparisons strip surrounding hyphens, so the trailing one is fine.
        self.assertEqual(
            github_slug("5. 菜单 CUD 与管理查询 ✅").strip("-"),
            "5-菜单-cud-与管理查询",
        )

    def test_github_slug_keeps_consecutive_hyphens(self):
        from lore_runtime.discover import github_slug

        # GitHub does not collapse spaces: 'IDL / proto' -> 'idl--proto'.
        self.assertEqual(github_slug("9. IDL / proto 同步习惯"), "9-idl--proto-同步习惯")

    def test_check_crossrefs_includes_markdown_links(self):
        from lore_runtime.discover import check_crossrefs

        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root / ".pikb").mkdir()
            (root / ".pikb" / "MAP.md").write_text("## 1. A\n", encoding="utf-8")
            (root / ".pikb" / "NOTES.md").write_text(
                "see [x](./MAP.md#1-a)\n", encoding="utf-8"
            )
            results = check_crossrefs(tmp)
        self.assertEqual(len(results), 1)
        self.assertEqual(results[0]["status"], "ok")

    def test_check_crossrefs_ignores_image_links(self):
        from lore_runtime.discover import check_crossrefs

        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root / ".pikb").mkdir()
            (root / ".pikb" / "NOTES.md").write_text(
                "![alt](./missing.md)\n", encoding="utf-8"
            )
            results = check_crossrefs(tmp)
        self.assertEqual(results, [])


if __name__ == "__main__":
    unittest.main()
