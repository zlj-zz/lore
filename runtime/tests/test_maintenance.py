import os
import tempfile
import time
import unittest
from pathlib import Path

FIXTURE = Path(__file__).resolve().parent / "fixtures" / "mini-ws"


class TestMaintenance(unittest.TestCase):
    def test_check_staleness_fixture_is_fresh(self):
        from lore_runtime.maintenance import check_staleness
        # The KB-age check reads file mtimes; a long-lived checkout makes the
        # static fixture look old. Refresh mtimes so this tests structure.
        now = time.time()
        for rel in (".pikb/MAP.md", ".pikb/PITFALLS.md", ".pikb/CONVENTIONS.md"):
            os.utime(FIXTURE / rel, (now, now))
        result = check_staleness(str(FIXTURE))
        self.assertIn("stale", result)
        # mini-ws has one repo with CONTEXT.md and PITFALLS with Triggers
        self.assertFalse(result["stale"])

    def test_repo_level_pitfalls_missing_triggers_flagged(self):
        from lore_runtime.maintenance import check_staleness
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root / ".pikb").mkdir()
            (root / ".pikb" / "MAP.md").write_text("# map\n", encoding="utf-8")
            repo = root / "svc"
            (repo / ".pi" / "kb").mkdir(parents=True)
            (repo / ".pi" / "kb" / "PITFALLS.md").write_text(
                "## 1. Trap\n\n- Symptom: x\n", encoding="utf-8"
            )
            result = check_staleness(tmp)
        self.assertTrue(
            any(i.get("check") == "PITFALLS Triggers" for i in result["issues"]),
            result["issues"],
        )

    def test_check_staleness_no_pikb(self):
        from lore_runtime.maintenance import check_staleness
        with tempfile.TemporaryDirectory() as tmp:
            result = check_staleness(tmp)
            self.assertTrue(result["stale"])
            self.assertTrue(any(".pikb/" in i.get("check", "") for i in result.get("issues", [])))

    def test_detect_novel_error_false_on_first_occurrence(self):
        from lore_runtime.maintenance import detect_novel_error
        result = detect_novel_error(str(FIXTURE), "connection timeout error")
        self.assertFalse(result)

    def test_detect_novel_error_true_after_three(self):
        from lore_runtime.maintenance import detect_novel_error
        msg = "unique test error pattern 42"
        detect_novel_error(str(FIXTURE), msg)
        detect_novel_error(str(FIXTURE), msg)
        result = detect_novel_error(str(FIXTURE), msg)
        self.assertTrue(result)

    def test_generate_proposals_returns_list(self):
        from lore_runtime.maintenance import generate_proposals
        stale = {"stale": True, "issues": [
            {"check": "CONTEXT.md coverage", "detail": "2 repos missing: foo, bar",
             "action": "create .pi/kb/CONTEXT.md", "repo": "foo"},
        ]}
        proposals = generate_proposals(str(FIXTURE), stale)
        self.assertIsInstance(proposals, list)
        self.assertTrue(any(p["type"] == "auto" for p in proposals))
        self.assertTrue(any("CONTEXT.md" in str(p) for p in proposals))

    def test_generate_proposals_empty_for_fresh(self):
        from lore_runtime.maintenance import generate_proposals
        stale = {"stale": False, "issues": []}
        proposals = generate_proposals(str(FIXTURE), stale)
        self.assertEqual(proposals, [])


if __name__ == "__main__":
    unittest.main()
