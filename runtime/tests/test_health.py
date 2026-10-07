import os
import tempfile
import time
import unittest
from pathlib import Path


class TestHealthKBage(unittest.TestCase):
    def test_static_readme_does_not_flag_kb_stale(self):
        # README.md is a static index; its old mtime must not mark the KB
        # stale while the real index (MAP.md) is fresh.
        from lore_runtime.health import check

        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            pikb = root / ".pikb"
            pikb.mkdir()
            (root / ".pi" / "kb").mkdir(parents=True)
            (root / ".pi" / "kb" / "CONTEXT.md").write_text(
                "# repo\n", encoding="utf-8"
            )
            (pikb / "MAP.md").write_text("# map\n", encoding="utf-8")
            (pikb / "README.md").write_text("# index\n", encoding="utf-8")
            old = time.time() - 64 * 86400
            os.utime(pikb / "README.md", (old, old))
            result = check(tmp)
        self.assertFalse(
            any("KB age" in w for w in result["warnings"]),
            result["warnings"],
        )

    def test_stale_map_md_flags_kb(self):
        from lore_runtime.health import check

        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            pikb = root / ".pikb"
            pikb.mkdir()
            (root / ".pi" / "kb").mkdir(parents=True)
            (root / ".pi" / "kb" / "CONTEXT.md").write_text(
                "# repo\n", encoding="utf-8"
            )
            (pikb / "MAP.md").write_text("# map\n", encoding="utf-8")
            old = time.time() - 40 * 86400
            os.utime(pikb / "MAP.md", (old, old))
            result = check(tmp)
        self.assertTrue(any("KB age" in w for w in result["warnings"]))


class TestRepoLevelPitfalls(unittest.TestCase):
    def test_repo_pitfalls_missing_triggers_flagged(self):
        from lore_runtime.health import check

        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root / ".pikb").mkdir()
            (root / ".pikb" / "MAP.md").write_text("# map\n", encoding="utf-8")
            (root / ".pi" / "kb").mkdir(parents=True)
            (root / ".pi" / "kb" / "CONTEXT.md").write_text("# ws\n", encoding="utf-8")
            repo = root / "svc"
            (repo / ".pi" / "kb").mkdir(parents=True)
            (repo / ".pi" / "kb" / "CONTEXT.md").write_text("# svc\n", encoding="utf-8")
            (repo / ".pi" / "kb" / "PITFALLS.md").write_text(
                "# svc pits\n\n## 1. Trap\n\n- Difficulty: \u2b50\u2b50\n- Symptom: x\n",
                encoding="utf-8",
            )
            result = check(tmp)
        self.assertTrue(
            any("missing Triggers" in w for w in result["warnings"]),
            result["warnings"],
        )


if __name__ == "__main__":
    unittest.main()
