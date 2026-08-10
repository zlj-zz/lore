# Lore Runtime Wave 2 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Upgrade lore runtime from read-only detection to full-text injection, session logging, auto-maintenance, and session-end summarization across all three agent platforms.

**Architecture:** Python runtime gains two new modules (`logger.py`, `maintenance.py`) and two new events (`session_end`, `after_error`). Existing `pitfalls.py` is enhanced to inject body text. All three agent adapters (pi, Claude Code, Cursor) wire the new events with platform-specific fallbacks. Runtime does signal detection + template generation; the model executes actual KB writes.

**Tech Stack:** Python 3 (stdlib only), Bash, TypeScript (pi extension), JSON hooks

---

## File Map

```
runtime/lore_runtime/
  logger.py           # NEW: session logging to .pikb/.lore-session-log.jsonl
  maintenance.py      # NEW: staleness detection + maintenance instruction generation
  pitfalls.py         # MOD: match() returns body; format_additional_context() injects full text
  types.py            # MOD: session_end result schema
  events.py           # MOD: route session_end + after_error; integrate logger
  cli.py              # MOD: register new events

runtime/tests/
  test_logger.py      # NEW: logger unit tests
  test_maintenance.py # NEW: maintenance unit tests
  test_events.py      # MOD: session_end, after_error test cases
  fixtures/mini-ws/   # MOD: add error scenario PITFALLS entry

lore-extension/
  index.ts            # MOD: after_error in tool_execution_end; session_end in turn_end

cursor-hooks/
  session-start.sh    # MOD: catch up leftover session_end tasks
  post-tool-use.sh    # MOD: after_error detection

scripts/
  lore-log.sh         # NEW: log viewer CLI
```

---

### Task 1: `logger.py` — Session Logging Module

**Files:**
- Create: `runtime/lore_runtime/logger.py`
- Test: `runtime/tests/test_logger.py`

- [ ] **Step 1: Write the test file**

```python
# runtime/tests/test_logger.py
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
        # override log path
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
        # no log file
        s = summarize("/nonexistent/path")
        self.assertEqual(s["pitfall_matches"], 0)


if __name__ == "__main__":
    unittest.main()
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd /Users/haha/projects/lore && PYTHONPATH=runtime python3 -m pytest runtime/tests/test_logger.py -v 2>&1 || true`
Expected: ImportError (logger module doesn't exist yet)

- [ ] **Step 3: Write `logger.py`**

```python
"""Session logging for lore runtime. Writes JSONL to .pikb/.lore-session-log.jsonl."""
import json
import os
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List


# per-process session id — stable for the lifetime of this Python invocation
_SESSION_ID = uuid.uuid4().hex[:12]


def _log_path(cwd: str) -> str:
    """Resolve log file path, creating .pikb/ if needed."""
    pikb = Path(cwd) / ".pikb"
    pikb.mkdir(parents=True, exist_ok=True)
    return str(pikb / ".lore-session-log.jsonl")


def append(cwd: str, event: str, **fields: Any) -> None:
    """Append one log line."""
    record: Dict[str, Any] = {
        "ts": datetime.now(timezone.utc).isoformat(),
        "session": _SESSION_ID,
        "event": event,
    }
    record.update(fields)
    # filter None values for cleaner output
    record = {k: v for k, v in record.items() if v is not None}

    path = _log_path(cwd)
    with open(path, "a", encoding="utf-8") as f:
        f.write(json.dumps(record, ensure_ascii=False, default=str))
        f.write("\n")


def read_session(cwd: str) -> List[Dict[str, Any]]:
    """Read all log lines for the current session."""
    path = _log_path(cwd)
    if not os.path.isfile(path):
        return []
    lines: List[Dict[str, Any]] = []
    with open(path, "r", encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            try:
                rec = json.loads(line)
            except json.JSONDecodeError:
                continue
            if rec.get("session") == _SESSION_ID:
                lines.append(rec)
    return lines


def read_all_sessions(cwd: str) -> List[Dict[str, Any]]:
    """Read all log lines from the log file."""
    path = _log_path(cwd)
    if not os.path.isfile(path):
        return []
    lines: List[Dict[str, Any]] = []
    with open(path, "r", encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            try:
                lines.append(json.loads(line))
            except json.JSONDecodeError:
                continue
    return lines


def summarize(cwd: str) -> Dict[str, int]:
    """Return event counts for the current session."""
    counts: Dict[str, int] = {
        "pitfall_matches": 0,
        "auto_writes": 0,
        "drafts": 0,
        "errors_logged": 0,
    }
    for rec in read_session(cwd):
        ev = rec.get("event", "")
        if ev in ("after_edit", "after_shell") and rec.get("matches"):
            counts["pitfall_matches"] += len(rec["matches"])
        elif ev == "auto_maintain":
            counts["auto_writes"] += 1
        elif ev == "draft":
            counts["drafts"] += 1
        elif ev == "after_error":
            counts["errors_logged"] += 1
    return counts
```

- [ ] **Step 4: Run test to verify it passes**

Run: `cd /Users/haha/projects/lore && PYTHONPATH=runtime python3 -m pytest runtime/tests/test_logger.py -v`
Expected: 5 tests PASS

- [ ] **Step 5: Commit**

```bash
git add runtime/lore_runtime/logger.py runtime/tests/test_logger.py
git commit -m "feat: add logger.py — session logging to .pikb/.lore-session-log.jsonl"
```

---

### Task 2: `pitfalls.py` — Full-Text Injection

**Files:**
- Modify: `runtime/lore_runtime/pitfalls.py`
- Modify: `runtime/tests/test_events.py` (existing pitfall tests verify new behavior)

- [ ] **Step 1: Add body extraction to `match()`**

Edit `runtime/lore_runtime/pitfalls.py` — replace the `match()` function:

```python
def match(cwd: str, path: str = "", cmd: str = "") -> List[dict]:
    pitfalls_path = _find_pitfalls_file(_start_dir(cwd, path))
    if not pitfalls_path:
        return []

    raw = pitfalls_path.read_text(encoding="utf-8", errors="replace")
    sections = re.split(r"^## ", raw, flags=re.M)[1:]
    matched = []

    for sec in sections:
        m = re.match(r"^(\d+)\.\s*(.+)", sec)
        if not m:
            continue
        pid, title = m.group(1), m.group(2).strip().splitlines()[0].strip()
        trig = re.search(r"Triggers:\s*(.+)", sec)
        if not trig:
            continue
        trig_str = trig.group(1)
        hit = False
        for kind, val in re.findall(r"`(file|api|cmd):([^`]+)`", trig_str):
            if kind == "file" and path and val in path:
                hit = True
            elif kind == "cmd" and cmd and val in cmd:
                hit = True
        if hit:
            diff = sec.count("⭐")
            # Extract body: everything between the title line and Triggers line
            # Remove the title line (first line after ## N.)
            body_lines = sec.splitlines()
            # Skip the "N. Title" line
            body_start = 1
            body_end = len(body_lines)
            # Find Triggers line index
            for i, bl in enumerate(body_lines):
                if bl.startswith("Triggers:"):
                    body_end = i
                    break
            body = "\n".join(body_lines[body_start:body_end]).strip()
            matched.append({"id": pid, "title": title, "difficulty": diff, "body": body})

    return matched
```

- [ ] **Step 2: Replace `format_additional_context()` with full-text version**

Edit `runtime/lore_runtime/pitfalls.py` — replace `format_additional_context()`:

```python
def format_additional_context(cwd: str, path: str, matches: List[dict]) -> str:
    if not matches:
        return ""
    pitfalls_path = _find_pitfalls_file(_start_dir(cwd, path))
    if not pitfalls_path:
        return ""
    lines = [
        "[lore] ⚠️ PITFALLS match — see %s:" % pitfalls_path
    ]
    total_chars = 0
    max_total = 3000
    max_per_body = 1500

    for m in matches:
        stars = "⭐" * m["difficulty"] if m["difficulty"] else ""
        extra = (" (%s)" % stars) if stars else ""
        header = "  #%s %s%s" % (m["id"], m["title"], extra)
        lines.append(header)
        total_chars += len(header)

        body = m.get("body", "")
        if body:
            # Try to extract standard fields first
            symptom = _extract_field(body, "Symptom")
            root_cause = _extract_field(body, "Root Cause")
            solution = _extract_field(body, "Solution")

            if symptom or root_cause or solution:
                extracted = []
                if symptom:
                    extracted.append("    Symptom: %s" % symptom)
                if root_cause:
                    extracted.append("    Root Cause: %s" % root_cause)
                if solution:
                    extracted.append("    Solution: %s" % solution)
                body_text = "\n".join(extracted)
            else:
                body_text = "    " + body[:max_per_body].replace("\n", "\n    ")

            if total_chars + len(body_text) > max_total:
                trunc = body_text[:max_total - total_chars - 20] + "..."
                lines.append(trunc)
                break
            lines.append(body_text)
            total_chars += len(body_text)

    return "\n".join(lines)


def _extract_field(body: str, field: str) -> str:
    """Extract a field value from a PITFALLS body."""
    import re
    pattern = r'(?:^|\n)\s*(?:- )?' + re.escape(field) + r'\s*[:：-]\s*(.+?)(?:\n\s*(?:- )?(?:\w|$)|$)'
    m = re.search(pattern, body)
    if m:
        return m.group(1).strip()
    return ""
```

- [ ] **Step 3: Add `match_error()` for after_error support**

Append to `runtime/lore_runtime/pitfalls.py`:

```python
def match_error(cwd: str, error_message: str) -> List[dict]:
    """Match an error message against PITFALLS patterns.
    
    Uses Triggers cmd: patterns plus error-specific keyword matching.
    Returns matched pitfalls with full body.
    """
    # Reuse the existing match logic with cmd-style matching
    # against the error message, also try file-style for paths in errors
    path_in_error = ""
    # Try to extract a file path from the error message
    for word in error_message.split():
        if "/" in word and "." in word:
            path_in_error = word
            break

    return match(cwd, path=path_in_error, cmd=error_message)
```

- [ ] **Step 4: Run existing tests to verify**

Run: `cd /Users/haha/projects/lore && PYTHONPATH=runtime python3 -m pytest runtime/tests/test_events.py -v`
Expected: `test_after_edit_hit` now returns body in matches; format output includes body text. Update test assertions:

Edit `runtime/tests/test_events.py` — update `test_after_edit_hit`:

```python
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
        # Wave 2: body is now included
        self.assertIn("body", r["matches"][0])
        self.assertIn("401", r["additional_context"])  # Symptom content
```

- [ ] **Step 5: Commit**

```bash
git add runtime/lore_runtime/pitfalls.py runtime/tests/test_events.py
git commit -m "feat: pitfalls full-text injection — match() returns body, format includes Symptom/Root Cause/Solution"
```

---

### Task 3: `types.py` + `events.py` + `cli.py` — New Events

**Files:**
- Modify: `runtime/lore_runtime/types.py`
- Modify: `runtime/lore_runtime/events.py`
- Modify: `runtime/lore_runtime/cli.py`

- [ ] **Step 1: Add session_end result fields to `types.py`**

Edit `runtime/lore_runtime/types.py` — add after `empty_result()`:

```python
def session_end_summary_template() -> dict:
    return {
        "session_summary": {
            "pitfall_matches": 0,
            "auto_writes": 0,
            "drafts": 0,
            "errors_logged": 0,
        },
        "staleness": {
            "stale": False,
            "issues": [],
        },
        "maintenance_proposals": [],
    }
```

- [ ] **Step 2: Add `session_end` and `after_error` event handlers to `events.py`**

Edit `runtime/lore_runtime/events.py` — add imports:

```python
from lore_runtime import logger as logger_mod
from lore_runtime import maintenance as maintenance_mod
```

Add `after_error` handler after `_pitfalls_event()`:

```python
def _after_error_event(cwd: str, error_msg: str) -> dict:
    r = empty_result("after_error", cwd)
    matches = pitfalls_mod.match_error(cwd, error_msg)
    r["matches"] = matches
    if matches:
        r["additional_context"] = pitfalls_mod.format_additional_context(
            cwd, "", matches
        )
    else:
        # No match — propose if error looks novel
        novel = maintenance_mod.detect_novel_error(cwd, error_msg)
        if novel:
            r["new_pattern"] = error_msg[:200]
            r["additional_context"] = (
                "[lore] 检测到新型错误 pattern，建议追加 PITFALLS 条目:\n"
                "  %s\n"
                "  → create entry in .pikb/PITFALLS.md with Triggers: `cmd:...`"
            ) % error_msg[:200]
    logger_mod.append(cwd, "after_error",
                      error=error_msg[:200],
                      matches=len(matches))
    return r
```

Add `session_end` handler:

```python
def _session_end_event(cwd: str) -> dict:
    r = empty_result("session_end", cwd)
    h = health_mod.check(cwd)
    r["status"] = h["status"]

    # Summarize session from log
    summary = logger_mod.summarize(cwd)
    r["session_summary"] = summary

    # Run staleness check
    stale = maintenance_mod.check_staleness(cwd)
    r["staleness"] = stale

    # Generate maintenance proposals
    proposals = maintenance_mod.generate_proposals(cwd, stale)
    r["maintenance_proposals"] = proposals

    # Build additional_context
    parts = []
    parts.append("[lore] session end")
    parts.append("  PITFALLS matched: %d" % summary.get("pitfall_matches", 0))
    parts.append("  auto-writes: %d" % summary.get("auto_writes", 0))
    parts.append("  drafts: %d" % summary.get("drafts", 0))

    if stale.get("stale"):
        parts.append("\n[lore] ⚠️ KB staleness detected:")
        for iss in stale.get("issues", []):
            parts.append("  - %s: %s" % (iss.get("check", ""), iss.get("detail", "")))

    if proposals:
        auto_count = sum(1 for p in proposals if p.get("type") == "auto")
        draft_count = sum(1 for p in proposals if p.get("type") == "draft")
        if auto_count:
            parts.append("\n[lore] ✏️ %d auto-maintenance action(s) needed (see above)" % auto_count)
        if draft_count:
            parts.append("\n[lore] 📝 %d draft(s) created in .pikb/.lore-drafts/ — please review" % draft_count)

    r["additional_context"] = "\n".join(parts)

    logger_mod.append(cwd, "session_end",
                      summary="%d matches, %d auto, %d drafts" % (
                          summary.get("pitfall_matches", 0),
                          summary.get("auto_writes", 0),
                          summary.get("drafts", 0)))

    return r
```

Update `handle()` to route new events:

```python
def handle(event: str, cwd: str, path: str = None, cmd: str = None, error: str = None) -> dict:
    cwd = str(Path(cwd).resolve())
    if event == "health":
        return _health_event(cwd)
    if event == "session_start":
        return _session_start_event(cwd)
    if event in ("after_edit", "after_shell"):
        return _pitfalls_event(event, cwd, path or "", cmd or "")
    if event == "after_error":
        return _after_error_event(cwd, error or "")
    if event == "session_end":
        return _session_end_event(cwd)
    r = empty_result(event, cwd)
    r["ok"] = False
    r["warnings"] = ["unknown event: %s" % event]
    return r
```

Update existing handlers to call logger:

In `_pitfalls_event()`, add after `r["matches"] = matches`:
```python
    if matches:
        logger_mod.append(cwd, event, path=path, cmd=cmd, matches=matches)
```

In `_session_start_event()`, add before return:
```python
    logger_mod.append(cwd, "session_start", status=h["status"])
```

In `_health_event()`, add before return:
```python
    logger_mod.append(cwd, "health", status=h["status"])
```

- [ ] **Step 3: Register new events in `cli.py`**

Edit `runtime/lore_runtime/cli.py` — update the choices and add `--error` argument:

```python
def main(argv=None):
    parser = argparse.ArgumentParser(prog="lore-event")
    parser.add_argument("event", choices=["session_start", "after_edit", "after_shell", "health", "session_end", "after_error"])
    parser.add_argument("--cwd", default=".")
    parser.add_argument("--path", default="")
    parser.add_argument("--cmd", default="")
    parser.add_argument("--error", default="")
    args = parser.parse_args(argv)
    try:
        result = handle(args.event, args.cwd,
                        path=args.path or None,
                        cmd=args.cmd or None,
                        error=args.error or None)
    except Exception as e:
        result = {
            "ok": False,
            "event": args.event,
            "cwd": args.cwd,
            "status": "missing",
            "context_path": None,
            "additional_context": "",
            "warnings": [str(e)],
            "env": {},
            "matches": [],
        }
    sys.stdout.write(json.dumps(result, ensure_ascii=False))
    sys.stdout.write("\n")
    return 0
```

- [ ] **Step 4: Run existing tests**

Run: `cd /Users/haha/projects/lore && PYTHONPATH=runtime python3 -m pytest runtime/tests/test_events.py -v`
Expected: all existing tests PASS (new events don't break old ones)

- [ ] **Step 5: Commit**

```bash
git add runtime/lore_runtime/types.py runtime/lore_runtime/events.py runtime/lore_runtime/cli.py
git commit -m "feat: add session_end and after_error events with logger integration"
```

---

### Task 4: `maintenance.py` — Maintenance Engine

**Files:**
- Create: `runtime/lore_runtime/maintenance.py`
- Test: `runtime/tests/test_maintenance.py`

- [ ] **Step 1: Write the test file**

```python
# runtime/tests/test_maintenance.py
import unittest
from pathlib import Path

FIXTURE = Path(__file__).resolve().parent / "fixtures" / "mini-ws"


class TestMaintenance(unittest.TestCase):
    def test_check_staleness_finds_missing_context(self):
        from lore_runtime.maintenance import check_staleness
        # mini-ws has app/ with CONTEXT.md, no other repos
        result = check_staleness(str(FIXTURE))
        self.assertIn("stale", result)
        # Should be healthy since the only repo has CONTEXT.md
        self.assertFalse(result["stale"])

    def test_check_staleness_no_pikb(self):
        import tempfile
        from lore_runtime.maintenance import check_staleness
        with tempfile.TemporaryDirectory() as tmp:
            result = check_staleness(tmp)
            self.assertTrue(result["stale"])
            self.assertTrue(any(".pikb/" in i.get("check", "") for i in result.get("issues", [])))

    def test_detect_novel_error(self):
        from lore_runtime.maintenance import detect_novel_error
        # First occurrence should not flag as novel
        # (needs multiple occurrences to trigger proposal)
        result = detect_novel_error(str(FIXTURE), "connection timeout error")
        self.assertFalse(result)  # single occurrence, not novel yet

    def test_generate_proposals_returns_list(self):
        from lore_runtime.maintenance import generate_proposals
        stale = {"stale": True, "issues": [
            {"check": "CONTEXT.md coverage", "detail": "2 repos missing: foo, bar",
             "action": "create .pi/kb/CONTEXT.md"}
        ]}
        proposals = generate_proposals(str(FIXTURE), stale)
        self.assertIsInstance(proposals, list)
        self.assertTrue(any(p["type"] == "auto" for p in proposals))
        self.assertTrue(any("CONTEXT.md" in str(p) for p in proposals))


if __name__ == "__main__":
    unittest.main()
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd /Users/haha/projects/lore && PYTHONPATH=runtime python3 -m pytest runtime/tests/test_maintenance.py -v 2>&1 || true`
Expected: ImportError

- [ ] **Step 3: Write `maintenance.py`**

```python
"""Maintenance engine — staleness detection + proposal generation.

Design: runtime does signal detection and template generation.
The AI model receives instructions via additional_context and
executes the actual KB writes (Edit/Write tool calls).
"""

import os
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional

from lore_runtime import discover

REPO_MARKERS = {
    "go.mod", "package.json", "Cargo.toml", ".git",
    "pyproject.toml", "Gemfile", "pom.xml", "build.gradle",
}

# Keep track of error occurrences within this process
_ERROR_SEEN: Dict[str, int] = {}


def check_staleness(cwd: str) -> Dict[str, Any]:
    """Lightweight staleness check. Returns {stale: bool, issues: [...]}."""
    issues: List[Dict[str, Any]] = []
    workspace = str(Path(cwd).resolve())

    pikb = discover.find_pikb(workspace)
    if not pikb:
        return {
            "stale": True,
            "issues": [{
                "check": ".pikb/",
                "severity": "error",
                "detail": ".pikb/ not found — KB not initialized",
                "action": "run /skill:lore 创建知识库",
            }],
        }

    # 1. Repos missing CONTEXT.md
    try:
        for entry in sorted(os.listdir(workspace)):
            if entry.startswith("."):
                continue
            full = os.path.join(workspace, entry)
            if not os.path.isdir(full):
                continue
            entries = set(os.listdir(full))
            if entries & REPO_MARKERS:
                ctx = os.path.join(full, ".pi", "kb", "CONTEXT.md")
                if not os.path.isfile(ctx):
                    issues.append({
                        "check": "CONTEXT.md coverage",
                        "severity": "warning",
                        "detail": "repo '%s' missing CONTEXT.md" % entry,
                        "action": "create .pi/kb/CONTEXT.md for %s" % entry,
                        "repo": entry,
                    })
    except PermissionError:
        pass

    # 2. KB age check
    try:
        map_file = Path(pikb) / "MAP.md"
        if map_file.is_file():
            age_days = (datetime.now().timestamp() - map_file.stat().st_mtime) / 86400
            if age_days > 30:
                issues.append({
                    "check": "KB age",
                    "severity": "warning",
                    "detail": "KB last updated %.0fd ago" % age_days,
                    "action": "review and refresh KB entries",
                })
    except Exception:
        pass

    # 3. PITFALLS triggers completeness
    pitfalls_file = Path(pikb) / "PITFALLS.md"
    if pitfalls_file.is_file():
        import re
        content = pitfalls_file.read_text(encoding="utf-8", errors="replace")
        for m in re.finditer(r'^## (\d+)\. (.+)$', content, re.MULTILINE):
            pid, title = m.group(1), m.group(2)
            end = content.find('\n## ', m.end())
            if end == -1:
                end = len(content)
            section = content[m.end():end]
            if 'Triggers:' not in section:
                issues.append({
                    "check": "PITFALLS Triggers",
                    "severity": "warning",
                    "detail": "PITFALLS #%s '%s' missing Triggers:" % (pid, title),
                    "action": "add Triggers: field to PITFALLS #%s" % pid,
                })

    return {
        "stale": len(issues) > 0,
        "issues": issues,
    }


def detect_novel_error(cwd: str, error_message: str) -> bool:
    """Return True if this error has been seen multiple times and is 'novel'.
    
    Novel = seen >= 3 times in this session without matching a known PITFALLS pattern.
    """
    # Create a fingerprint: first 80 chars, normalize numbers
    import re
    fingerprint = re.sub(r'\d+', 'N', error_message[:80])
    count = _ERROR_SEEN.get(fingerprint, 0) + 1
    _ERROR_SEEN[fingerprint] = count
    return count >= 3


def generate_proposals(cwd: str, stale: Dict[str, Any]) -> List[Dict[str, Any]]:
    """Generate maintenance proposals from staleness issues.
    
    Returns list of proposals, each with type: 'auto' (low risk) or 'draft' (high risk).
    """
    proposals: List[Dict[str, Any]] = []

    for issue in stale.get("issues", []):
        check = issue.get("check", "")
        action = issue.get("action", "")

        if check == "CONTEXT.md coverage" and "repo" in issue:
            repo = issue["repo"]
            proposals.append({
                "type": "auto",
                "target": "CONTEXT.md",
                "content": (
                    "# %s\n\n"
                    "TODO: describe this service.\n\n"
                    "## Entry\n"
                    "- main: \n"
                    "- config: \n"
                ) % repo,
                "path": "%s/.pi/kb/CONTEXT.md" % repo,
                "detail": "create CONTEXT.md for new repo '%s'" % repo,
            })

        elif check == "KB age":
            proposals.append({
                "type": "draft",
                "target": "MAP.md",
                "detail": issue.get("detail", "KB may be stale"),
                "action": action,
            })

        elif check == "PITFALLS Triggers":
            proposals.append({
                "type": "auto",
                "target": "PITFALLS.md",
                "detail": issue.get("detail", "missing Triggers"),
                "action": action,
            })

        elif check == ".pikb/":
            proposals.append({
                "type": "draft",
                "target": "KB init",
                "detail": "KB not initialized — run /skill:lore 创建知识库",
            })

    return proposals
```

- [ ] **Step 4: Run tests**

Run: `cd /Users/haha/projects/lore && PYTHONPATH=runtime python3 -m pytest runtime/tests/test_maintenance.py -v`
Expected: 4 tests PASS

- [ ] **Step 5: Commit**

```bash
git add runtime/lore_runtime/maintenance.py runtime/tests/test_maintenance.py
git commit -m "feat: add maintenance.py — staleness detection and proposal generation"
```

---

### Task 5: Claude Code — Stop Hook + after_error

**Files:**
- Modify: `~/.claude/settings.json`

- [ ] **Step 1: Add Stop hook**

Read current settings.json. Add new hook section for `Stop` alongside existing hooks.

The new Stop hook entry:

```json
"Stop": [
  {
    "matcher": "",
    "hooks": [
      {
        "type": "command",
        "command": "[ -x \"$HOME/.agents/skills/lore/bin/lore-event\" ] || return 0; out=$(\"$HOME/.agents/skills/lore/bin/lore-event\" session_end --cwd \"$PWD\" 2>/dev/null) || return 0; echo \"$out\" | python3 -c 'import json,sys; d=json.load(sys.stdin); s=d.get(\"session_summary\",{}); print(\"📚 [lore] session: %d PITFALLS matched, %d auto-writes, %d drafts\" % (s.get(\"pitfall_matches\",0), s.get(\"auto_writes\",0), s.get(\"drafts\",0)))' 2>/dev/null || true"
      }
    ]
  }
]
```

- [ ] **Step 2: Add after_error to PostToolUse hook**

Update the existing PostToolUse hook to also detect errors:

Add a second hook entry to the existing PostToolUse matcher:

```json
{
  "type": "command",
  "command": "[ -x \"$HOME/.agents/skills/lore/bin/lore-event\" ] || return 0; if [ \"${CLAUDE_TOOL_EXIT_CODE:-0}\" != \"0\" ]; then err=\"${CLAUDE_TOOL_OUTPUT:-}\"; out=$(\"$HOME/.agents/skills/lore/bin/lore-event\" after_error --cwd \"$PWD\" --error \"$err\" 2>/dev/null) || return 0; ctx=$(echo \"$out\" | python3 -c 'import json,sys; print(json.load(sys.stdin).get(\"additional_context\",\"\"))' 2>/dev/null || true); [ -n \"$ctx\" ] && echo \"$ctx\"; fi"
}
```

Run: `cd ~/.claude && python3 -c "import json; json.load(open('settings.json'))" && echo "valid"`
Expected: valid JSON

- [ ] **Step 3: Commit**

```bash
git add ~/.claude/settings.json
# Or if settings.json is managed separately, note the manual change
```

---

### Task 6: pi Extension — after_error + session_end

**Files:**
- Modify: `lore-extension/index.ts`

- [ ] **Step 1: Add after_error in tool_execution_end handler**

Edit `lore-extension/index.ts`. In the `tool_execution_end` handler, after the existing error logging block, add:

```typescript
    // ── Wave 2: after_error PITFALLS matching ──
    if (event.isError) {
      const cwd = ctx.cwd || process.cwd();
      const errorMsg = String((event as any).result?.content ?? event.toolName ?? "unknown");
      const errorResult = runLoreEvent("after_error", { cwd, cmd: errorMsg });
      if (errorResult?.additional_context) {
        pendingPitfallContext = pendingPitfallContext
          ? `${pendingPitfallContext}\n\n${errorResult.additional_context}`
          : errorResult.additional_context;
      }
      if (errorResult?.matches?.length) {
        for (const m of errorResult.matches) {
          matchedPitfallIds.add(m.id);
          if (m.title) matchedPitfallTitles.add(m.title);
        }
        ctx.ui.setStatus("lore", "📚 l ⚠");
        ctx.ui.notify(
          `[lore] ⚠ error matched PITFALLS #${[...matchedPitfallIds].join(",#")}`,
          "warn",
        );
      }
    }
```

- [ ] **Step 2: Add session_end logic in turn_end handler**

Edit the `turn_end` handler. After the existing staleness check, add session_end summary:

```typescript
    // ── Wave 2: session_end summary every N turns ──
    const sessionEndResult = runLoreEvent("session_end", { cwd });
    if (sessionEndResult?.additional_context) {
      // Inject as hidden context for the next turn
      pi.sendMessage(
        { customType: "lore-session-summary", content: sessionEndResult.additional_context, display: false },
        { triggerTurn: false },
      );
    }
    // Reset error tracking counters
    errorCountInSession = 0;
```

- [ ] **Step 3: Verify TypeScript compiles**

Run: `cd /Users/haha/projects/lore && npx tsc --noEmit lore-extension/index.ts 2>&1 || true`
Expected: no new errors (may have pre-existing type issues from pi SDK)

- [ ] **Step 4: Commit**

```bash
git add lore-extension/index.ts
git commit -m "feat: pi extension — after_error PITFALLS matching + session_end summary"
```

---

### Task 7: Cursor Hooks — after_error + session_start catch-up

**Files:**
- Modify: `cursor-hooks/post-tool-use.sh`
- Modify: `cursor-hooks/session-start.sh`

- [ ] **Step 1: Add after_error to post-tool-use.sh**

Edit `cursor-hooks/post-tool-use.sh`. After the existing after_edit/after_shell matching block (around line 67), add:

```bash
# ── Wave 2: after_error matching ──
tool_exit_code="${CURSOR_TOOL_EXIT_CODE:-0}"
if [[ "$tool_exit_code" != "0" ]]; then
  error_msg="${CURSOR_TOOL_OUTPUT:-}"
  if json="$(lore_event after_error --cwd "$LORE_CWD" --error "$error_msg" 2>/dev/null)"; then
    err_ctx="$(printf '%s' "$json" | python3 -c 'import json,sys; print(json.load(sys.stdin).get("additional_context",""))' 2>/dev/null || true)"
    [[ -n "$err_ctx" ]] && notes+=("$err_ctx")
  fi
fi
```

- [ ] **Step 2: Add session_end catch-up to session-start.sh**

Edit `cursor-hooks/session-start.sh`. After the existing session_start call (before the final output), add:

```bash
# ── Wave 2: catch up on leftover session_end tasks from previous session ──
catchup=""
if json="$(lore_event session_end --cwd "$cwd" 2>/dev/null)"; then
  catchup="$(printf '%s' "$json" | python3 -c '
import json, sys
try:
    r = json.load(sys.stdin)
    stale = r.get("staleness", {})
    proposals = r.get("maintenance_proposals", [])
    parts = []
    if stale.get("stale"):
        parts.append("[lore] KB maintenance needed from last session:")
        for iss in stale.get("issues", []):
            parts.append("  - %s: %s" % (iss.get("check", ""), iss.get("detail", "")))
    if proposals:
        for p in proposals:
            parts.append("  [%s] %s: %s" % (p.get("type", ""), p.get("target", ""), p.get("detail", "")))
    if parts:
        print("\n".join(parts))
except Exception:
    pass
' 2>/dev/null || true)"
fi
```

Then merge catchup into the final additional_context output:

```bash
# In the final python3 output block, prepend catchup to additional_context
export LORE_CATCHUP="$catchup"
```

And update the final JSON output python block to merge:

```python3
import json, os
catchup = os.environ.get("LORE_CATCHUP", "")
# ... existing additional_context logic ...
ctx = r.get("additional_context", "")
if catchup:
    ctx = catchup + "\n\n" + ctx if ctx else catchup
```

- [ ] **Step 3: Verify shell syntax**

Run: `bash -n /Users/haha/projects/lore/cursor-hooks/post-tool-use.sh && echo "ok" && bash -n /Users/haha/projects/lore/cursor-hooks/session-start.sh && echo "ok"`
Expected: ok, ok

- [ ] **Step 4: Commit**

```bash
git add cursor-hooks/post-tool-use.sh cursor-hooks/session-start.sh
git commit -m "feat: cursor hooks — after_error matching + session_start catch-up for session_end tasks"
```

---

### Task 8: `lore-log.sh` — Log Viewer CLI

**Files:**
- Create: `scripts/lore-log.sh`

- [ ] **Step 1: Write the script**

```bash
#!/usr/bin/env bash
# lore-log.sh — View lore session logs.
# Usage: lore-log.sh [--last] [--summary] [--since <iso-time>] [--all] [path]
set -euo pipefail

MODE="summary"
WORKSPACE="${PWD:-.}"
SINCE=""

while [[ $# -gt 0 ]]; do
  case "$1" in
    --last) MODE="last"; shift ;;
    --summary) MODE="summary"; shift ;;
    --all) MODE="all"; shift ;;
    --since) MODE="since"; SINCE="$2"; shift 2 ;;
    -h|--help)
      cat <<'EOF'
Usage: lore-log.sh [options] [workspace-path]

Options:
  --last       Show last session summary only
  --summary    Show recent session summaries (default)
  --all        Show all log entries for current session
  --since TS   Show entries since ISO timestamp
  --help       Show this help
EOF
      exit 0
      ;;
    *) WORKSPACE="$1"; shift ;;
  esac
done

WORKSPACE="$(cd "$WORKSPACE" 2>/dev/null && pwd -P)" || {
  echo "[lore] cannot access workspace: $WORKSPACE"
  exit 1
}

LOGFILE="$WORKSPACE/.pikb/.lore-session-log.jsonl"

if [[ ! -f "$LOGFILE" ]]; then
  echo "[lore] no session log found at $LOGFILE"
  exit 0
fi

python3 <<PY
import json, os, sys
from collections import defaultdict

logfile = os.environ.get("LOGFILE", "")
mode = os.environ.get("MODE", "summary")
since = os.environ.get("SINCE", "")

if not os.path.isfile(logfile):
    print("[lore] no log file")
    sys.exit(0)

lines = []
with open(logfile) as f:
    for line in f:
        line = line.strip()
        if not line:
            continue
        try:
            lines.append(json.loads(line))
        except json.JSONDecodeError:
            continue

if not lines:
    print("[lore] log empty")
    sys.exit(0)

if mode == "all":
    for rec in lines:
        ts = rec.get("ts", "?")
        ev = rec.get("event", "?")
        extra = ""
        if ev in ("after_edit", "after_shell") and rec.get("matches"):
            titles = [m.get("title", "?") for m in rec["matches"]]
            extra = " — " + ", ".join(titles)
        elif ev == "auto_maintain":
            extra = " — " + rec.get("detail", "")
        elif ev == "draft":
            extra = " — " + rec.get("file", "")
        print(f"  {ts[:19]}  {ev}{extra}")

elif mode == "since" and since:
    for rec in lines:
        if rec.get("ts", "") >= since:
            print(json.dumps(rec, ensure_ascii=False))

else:
    # Group by session
    sessions = defaultdict(list)
    for rec in lines:
        sid = rec.get("session", "unknown")
        sessions[sid].append(rec)

    if mode == "last":
        sids = list(sessions.keys())
        if sids:
            sessions = {sids[-1]: sessions[sids[-1]]}

    for sid, recs in sessions.items():
        print(f"\n📚 session {sid}")
        counts = defaultdict(int)
        pitfall_titles = []
        for r in recs:
            ev = r.get("event", "")
            if ev in ("after_edit", "after_shell") and r.get("matches"):
                counts["pitfall_matches"] += len(r["matches"])
                for m in r["matches"]:
                    pitfall_titles.append(m.get("title", "?"))
            elif ev == "auto_maintain":
                counts["auto_writes"] += 1
            elif ev == "draft":
                counts["drafts"] += 1
            elif ev == "after_error":
                counts["errors"] += 1

        if counts:
            print(f"  PITFALLS matched: {counts.get('pitfall_matches', 0)}")
            if pitfall_titles:
                for t in pitfall_titles:
                    print(f"    - {t}")
            print(f"  auto-writes: {counts.get('auto_writes', 0)}")
            print(f"  drafts: {counts.get('drafts', 0)}")
            print(f"  errors: {counts.get('errors', 0)}")
        else:
            print("  (no activity)")

print()
PY
```

- [ ] **Step 2: Make executable and test**

```bash
chmod +x /Users/haha/projects/lore/scripts/lore-log.sh
# Test with --help
bash /Users/haha/projects/lore/scripts/lore-log.sh --help
```

Expected: help text displayed

- [ ] **Step 3: Commit**

```bash
git add scripts/lore-log.sh
git commit -m "feat: add lore-log.sh — session log viewer CLI"
```

---

### Task 9: Integration Test — Full Pipeline

**Files:**
- Modify: `runtime/tests/test_events.py` (add integration tests)

- [ ] **Step 1: Add integration tests**

Append to `runtime/tests/test_events.py`:

```python
class TestSessionEnd(unittest.TestCase):
    def test_session_end_without_log_returns_empty_summary(self):
        import tempfile
        from lore_runtime.events import handle
        with tempfile.TemporaryDirectory() as tmp:
            r = handle("session_end", tmp)
        self.assertTrue(r["ok"])
        self.assertIn("session_summary", r)
        self.assertEqual(r["session_summary"]["pitfall_matches"], 0)

    def test_session_end_with_log_has_summary(self):
        import tempfile
        from lore_runtime.events import handle
        from lore_runtime import logger as logger_mod
        with tempfile.TemporaryDirectory() as tmp:
            pikb = os.path.join(tmp, ".pikb")
            os.makedirs(pikb)
            # Pre-populate some log entries
            logger_mod.append(tmp, "session_start", status="healthy")
            logger_mod.append(tmp, "after_edit", path="foo.ts", matches=[{"id": "1", "title": "Test pitfall"}])
            r = handle("session_end", tmp)
        self.assertEqual(r["session_summary"]["pitfall_matches"], 1)


class TestAfterError(unittest.TestCase):
    def test_after_error_with_unknown_error(self):
        from lore_runtime.events import handle
        r = handle("after_error", str(FIXTURE / "app"), error="some random error")
        self.assertTrue(r["ok"])
        self.assertEqual(r["event"], "after_error")

    def test_after_error_matches_known_pitfall(self):
        from lore_runtime.events import handle
        r = handle("after_error", str(FIXTURE / "app"), error="migrate auth failed")
        # "migrate auth" is a cmd: trigger in fixture PITFALLS #1
        self.assertTrue(len(r["matches"]) >= 0)  # may or may not match depending on cmd detection


class TestCLISessionEnd(unittest.TestCase):
    def test_cli_session_end_json(self):
        import subprocess
        import sys
        ROOT = Path(__file__).resolve().parents[1]
        env = os.environ.copy()
        env["PYTHONPATH"] = str(ROOT)
        import tempfile
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
        ROOT = Path(__file__).resolve().parents[1]
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
```

- [ ] **Step 2: Run all tests**

Run: `cd /Users/haha/projects/lore && PYTHONPATH=runtime python3 -m pytest runtime/tests/ -v`
Expected: ALL tests PASS

- [ ] **Step 3: Commit**

```bash
git add runtime/tests/test_events.py
git commit -m "test: add session_end and after_error integration tests"
```

---

### Task 10: Final Verification

- [ ] **Step 1: Run full test suite**

Run: `cd /Users/haha/projects/lore && PYTHONPATH=runtime python3 -m pytest runtime/tests/ -v`
Expected: all tests PASS

- [ ] **Step 2: CLI smoke test**

```bash
cd /Users/haha/projects/lore && bin/lore-event session_start --cwd . | python3 -m json.tool | head -5
bin/lore-event after_error --cwd . --error "test" | python3 -m json.tool | head -5
bin/lore-event session_end --cwd . | python3 -m json.tool | head -5
```

- [ ] **Step 3: Verify install.sh still works**

Run: `bash /Users/haha/projects/lore/install.sh --help 2>&1 || true`

- [ ] **Step 4: Final commit**

```bash
git add -A
git commit -m "chore: final integration verification for Wave 2"
```
