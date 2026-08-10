import json
import os
import tempfile
import unittest
from pathlib import Path


class TestLogger(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.pikb = Path(self.tmp.name) / ".pikb"
        self.pikb.mkdir()
        import lore_runtime.logger as logger_mod
        self._orig_log_path = logger_mod._log_path
        logger_mod._log_path = staticmethod(lambda cwd: str(Path(cwd) / ".pikb" / ".lore-session-log.jsonl"))

    def tearDown(self):
        import lore_runtime.logger as logger_mod
        logger_mod._log_path = self._orig_log_path
        self.tmp.cleanup()

    def _log_path(self):
        return str(self.pikb / ".lore-session-log.jsonl")

    def test_append_writes_jsonl(self):
        from lore_runtime.logger import append
        append(self.tmp.name, event="after_edit", path="foo.ts", matches=[{"id": "1"}])
        with open(self._log_path()) as f:
            lines = f.readlines()
        self.assertEqual(len(lines), 1)
        record = json.loads(lines[0])
        self.assertEqual(record["event"], "after_edit")
        self.assertEqual(record["path"], "foo.ts")
        self.assertIn("ts", record)

    def test_append_creates_pikb_if_missing(self):
        import shutil
        shutil.rmtree(self.pikb)
        from lore_runtime.logger import append
        append(self.tmp.name, event="session_start", status="healthy")
        self.assertTrue(os.path.exists(self._log_path()))

    def test_read_session_returns_current_session_lines(self):
        from lore_runtime.logger import append, read_session
        append(self.tmp.name, event="session_start")
        append(self.tmp.name, event="after_edit", path="a.ts")
        append(self.tmp.name, event="session_end")
        lines = read_session(self.tmp.name)
        self.assertGreaterEqual(len(lines), 1)

    def test_summarize_counts_events(self):
        from lore_runtime.logger import append, summarize
        append(self.tmp.name, event="session_start")
        append(self.tmp.name, event="after_edit", matches=[{"id": "1"}])
        append(self.tmp.name, event="after_edit", matches=[{"id": "2"}])
        append(self.tmp.name, event="auto_maintain", action="pitfall_appended")
        s = summarize(self.tmp.name)
        self.assertIn("pitfall_matches", s)
        self.assertEqual(s["pitfall_matches"], 2)
        self.assertEqual(s["auto_writes"], 1)

    def test_summarize_empty_log(self):
        from lore_runtime.logger import summarize
        s = summarize("/nonexistent/path")
        self.assertEqual(s["pitfall_matches"], 0)


if __name__ == "__main__":
    unittest.main()
