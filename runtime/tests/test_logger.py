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

    def tearDown(self):
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
        self.assertEqual(len(lines), 3)

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

    def test_summarize_counts_each_match_not_just_events(self):
        from lore_runtime.logger import append, summarize

        # One after_edit with multiple matches counts each match individually.
        append(
            self.tmp.name,
            event="after_edit",
            matches=[{"id": "1"}, {"id": "2"}, {"id": "3"}],
        )
        s = summarize(self.tmp.name)
        self.assertEqual(s["pitfall_matches"], 3)

    def test_summarize_empty_log(self):
        from lore_runtime.logger import summarize

        s = summarize("/nonexistent/path")
        self.assertEqual(s["pitfall_matches"], 0)

    def test_read_all_sessions_includes_other_sessions(self):
        from lore_runtime.logger import append, read_all_sessions, read_session

        append(self.tmp.name, event="session_start")
        # Simulate a record written by a different session/process.
        with open(self._log_path(), "a", encoding="utf-8") as f:
            f.write(
                json.dumps(
                    {
                        "ts": "2026-01-01T00:00:00+00:00",
                        "session": "other-session",
                        "event": "session_start",
                    }
                )
                + "\n"
            )
        self.assertEqual(len(read_all_sessions(self.tmp.name)), 2)
        self.assertEqual(len(read_session(self.tmp.name)), 1)

    def test_append_trims_log_when_over_cap(self):
        import lore_runtime.logger as lg

        old_bytes = lg._MAX_LOG_BYTES
        lg._MAX_LOG_BYTES = 500
        try:
            for i in range(50):
                lg.append(self.tmp.name, event="after_edit", path=f"f{i}.ts")
            size = os.path.getsize(self._log_path())
            with open(self._log_path()) as f:
                lines = f.readlines()
        finally:
            lg._MAX_LOG_BYTES = old_bytes
        # 50 lines are ~4.5 KB; the cap holds the file near the threshold.
        self.assertLess(size, 1000)
        self.assertEqual(json.loads(lines[-1])["path"], "f49.ts")

    def test_append_filters_none_values(self):
        from lore_runtime.logger import append

        append(self.tmp.name, event="after_edit", path=None, notes=None, matches=[])
        with open(self._log_path()) as f:
            record = json.loads(f.readline())
        self.assertNotIn("path", record)
        self.assertNotIn("notes", record)
        self.assertEqual(record["matches"], [])


if __name__ == "__main__":
    unittest.main()
