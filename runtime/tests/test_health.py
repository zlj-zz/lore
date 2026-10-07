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
            (root / ".pi" / "kb" / "CONTEXT.md").write_text("# repo\n", encoding="utf-8")
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
            (root / ".pi" / "kb" / "CONTEXT.md").write_text("# repo\n", encoding="utf-8")
            (pikb / "MAP.md").write_text("# map\n", encoding="utf-8")
            old = time.time() - 40 * 86400
            os.utime(pikb / "MAP.md", (old, old))
            result = check(tmp)
        self.assertTrue(any("KB age" in w for w in result["warnings"]))


if __name__ == "__main__":
    unittest.main()
