import os
import tempfile
import unittest
from pathlib import Path

FIXTURE = Path(__file__).resolve().parent / "fixtures" / "mini-ws"


class TestMaintenance(unittest.TestCase):
    def test_check_staleness_fixture_is_fresh(self):
        from lore_runtime.maintenance import check_staleness
        result = check_staleness(str(FIXTURE))
        self.assertIn("stale", result)
        # mini-ws has one repo with CONTEXT.md and PITFALLS with Triggers
        self.assertFalse(result["stale"])

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
