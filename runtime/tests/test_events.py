import json
import os
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]  # runtime/
FIXTURE = Path(__file__).resolve().parent / "fixtures" / "mini-ws"


class TestHealth(unittest.TestCase):
    def test_health_missing_pikb(self):
        from lore_runtime.events import handle

        with tempfile.TemporaryDirectory() as tmp:
            r = handle("health", tmp)
        self.assertTrue(r["ok"])
        self.assertEqual(r["event"], "health")
        self.assertEqual(r["status"], "missing")
        self.assertTrue(any("pikb" in w.lower() or "missing" in w.lower() for w in r["warnings"]) or r["status"] == "missing")

    def test_health_fixture_not_missing(self):
        from lore_runtime.events import handle
        r = handle("health", str(FIXTURE / "app"))
        self.assertIn(r["status"], ("healthy", "degraded"))
        self.assertIsNotNone(r["context_path"])


class TestSessionStart(unittest.TestCase):
    def test_session_start_includes_context_and_marker(self):
        from lore_runtime.events import handle

        r = handle("session_start", str(FIXTURE / "app"))
        self.assertTrue(r["ok"])
        self.assertIn("📚 lore loaded", r["additional_context"])
        self.assertIn("mini-app", r["additional_context"])
        self.assertEqual(r["env"]["LORE_LOADED"], "1")
        self.assertIn("Workspace Map", r["additional_context"])


class TestPitfalls(unittest.TestCase):
    def test_after_edit_hit(self):
        from lore_runtime.events import handle

        r = handle(
            "after_edit",
            str(FIXTURE / "app"),
            path=str(FIXTURE / "app" / "middleware" / "auth.ts"),
        )
        self.assertEqual(len(r["matches"]), 1)
        self.assertEqual(r["matches"][0]["id"], "1")
        self.assertIn("Auth middleware", r["additional_context"])

    def test_after_edit_miss(self):
        from lore_runtime.events import handle

        r = handle(
            "after_edit",
            str(FIXTURE / "app"),
            path=str(FIXTURE / "app" / "other.ts"),
        )
        self.assertEqual(r["matches"], [])
        self.assertEqual(r["additional_context"], "")

    def test_after_shell_hit(self):
        from lore_runtime.events import handle

        r = handle("after_shell", str(FIXTURE / "app"), cmd="npm run migrate auth")
        self.assertEqual(r["matches"][0]["id"], "1")


if __name__ == "__main__":
    unittest.main()
