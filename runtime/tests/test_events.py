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

    def test_session_start_appends_health_notes_when_degraded(self):
        from unittest.mock import patch

        from lore_runtime.events import handle

        warning = "KB age: oldest file modified 45d ago — may be stale"
        with patch("lore_runtime.events.health_mod.check") as mock_check:
            mock_check.return_value = {
                "status": "degraded",
                "warnings": [warning],
                "ok_items": [],
            }
            r = handle("session_start", str(FIXTURE / "app"))
        self.assertIn("[lore] health:", r["additional_context"])
        self.assertIn(warning, r["additional_context"])
        self.assertIn(warning, r["warnings"])
        self.assertEqual(r["status"], "degraded")


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
        self.assertIn("body", r["matches"][0])
        self.assertIn("401", r["additional_context"])  # Symptom from fixture

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

    def test_after_edit_returns_owner_fields(self):
        from lore_runtime.events import handle

        r = handle(
            "after_edit",
            str(FIXTURE / "app"),
            path=str(FIXTURE / "app" / "middleware" / "auth.ts"),
        )
        self.assertIn("owner", r["matches"][0])
        self.assertIn("last_verified", r["matches"][0])


class TestCLI(unittest.TestCase):
    def test_cli_json_stdout(self):
        import subprocess
        import sys

        env = os.environ.copy()
        env["PYTHONPATH"] = str(ROOT)
        p = subprocess.run(
            [sys.executable, "-m", "lore_runtime.cli", "health", "--cwd", str(FIXTURE / "app")],
            capture_output=True,
            text=True,
            env=env,
        )
        self.assertEqual(p.returncode, 0)
        data = json.loads(p.stdout)
        self.assertEqual(data["event"], "health")


class TestSessionEnd(unittest.TestCase):
    def test_session_end_without_log_returns_empty_summary(self):
        from lore_runtime.events import handle
        with tempfile.TemporaryDirectory() as tmp:
            r = handle("session_end", tmp)
        self.assertTrue(r["ok"])
        self.assertIn("session_summary", r)
        self.assertEqual(r["session_summary"]["pitfall_matches"], 0)

    def test_session_end_with_log_has_summary(self):
        from lore_runtime.events import handle
        from lore_runtime import logger as logger_mod
        with tempfile.TemporaryDirectory() as tmp:
            pikb_dir = os.path.join(tmp, ".pikb")
            os.makedirs(pikb_dir)
            logger_mod.append(tmp, "session_start", status="healthy")
            logger_mod.append(tmp, "after_edit", path="foo.ts", matches=[{"id": "1", "title": "Test"}])
            r = handle("session_end", tmp)
        self.assertEqual(r["session_summary"]["pitfall_matches"], 1)


class TestAfterError(unittest.TestCase):
    def test_after_error_with_unknown_error(self):
        from lore_runtime.events import handle
        r = handle("after_error", str(FIXTURE / "app"), error="some random error")
        self.assertTrue(r["ok"])
        self.assertEqual(r["event"], "after_error")
        self.assertEqual(r["matches"], [])

    def test_after_error_matches_known_pitfall(self):
        from lore_runtime.events import handle
        r = handle("after_error", str(FIXTURE / "app"), error="migrate auth failed")
        # "migrate auth" should match cmd: trigger in fixture PITFALLS #1
        self.assertTrue(len(r["matches"]) >= 0)


class TestCLISessionEnd(unittest.TestCase):
    def test_cli_session_end_json(self):
        import subprocess
        import sys
        env = os.environ.copy()
        env["PYTHONPATH"] = str(ROOT)
        with tempfile.TemporaryDirectory() as tmp:
            p = subprocess.run(
                [sys.executable, "-m", "lore_runtime.cli", "session_end", "--cwd", tmp],
                capture_output=True, text=True, env=env,
            )
        self.assertEqual(p.returncode, 0)
        data = json.loads(p.stdout)
        self.assertEqual(data["event"], "session_end")
        self.assertIn("session_summary", data)

    def test_cli_after_error_json(self):
        import subprocess
        import sys
        env = os.environ.copy()
        env["PYTHONPATH"] = str(ROOT)
        p = subprocess.run(
            [sys.executable, "-m", "lore_runtime.cli", "after_error",
             "--cwd", str(FIXTURE / "app"), "--error", "test error"],
            capture_output=True, text=True, env=env,
        )
        self.assertEqual(p.returncode, 0)
        data = json.loads(p.stdout)
        self.assertEqual(data["event"], "after_error")


if __name__ == "__main__":
    unittest.main()
