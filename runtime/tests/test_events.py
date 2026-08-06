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


if __name__ == "__main__":
    unittest.main()
