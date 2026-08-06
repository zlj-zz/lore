# lore_runtime Adapters (D3) Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Move session bootstrap, PITFALLS matching, and health checks into a shared stdlib-only Python `lore_runtime`, with Cursor/Claude/pi as thin adapters over one JSON CLI.

**Architecture:** `runtime/lore_runtime` owns discover/load/match/health/format and exposes `python3 -m lore_runtime.cli <event>`. Adapters only translate platform stdin/stdout. Existing `scripts/on-session-start.sh` and `scripts/match-trigger.sh` become facades. Spec: `docs/superpowers/specs/2026-08-06-lore-runtime-adapters-design.md`.

**Tech Stack:** Python 3.9+ stdlib only (`unittest`, `json`, `pathlib`, `argparse`, `re`); bash adapters; existing TypeScript pi extension (spawn CLI only).

## Global Constraints

- No third-party Python dependencies.
- `lore-event` / `python -m lore_runtime.cli` always exits `0`; logical failure → `ok: false` + `warnings`.
- stdout of CLI is pure JSON; debug on stderr only.
- Adapters never block agent sessions (Cursor/Claude hooks soft-fail to `{}` / no-op).
- Do not move `scan-workspace` / `graph` / `audit-kb` into runtime in this plan.
- Do not attempt to fix Cursor `additional_context` platform race; keep `env` + rules fallback.
- Invoke with `PYTHONPATH="<skill-root>/runtime"` or `bin/lore-event`.
- Wave-1 events only: `session_start`, `after_edit`, `after_shell`, `health`.

## File map

| Path | Responsibility |
|------|----------------|
| `runtime/lore_runtime/types.py` | `EventResult` dict shape helpers |
| `runtime/lore_runtime/discover.py` | Find CONTEXT.md / .pikb / PITFALLS.md walking up from cwd |
| `runtime/lore_runtime/context.py` | Load CONTEXT + MAP summary + rules blurb |
| `runtime/lore_runtime/pitfalls.py` | Parse Triggers; match path/cmd |
| `runtime/lore_runtime/health.py` | Port health logic from `on-session-start.sh` |
| `runtime/lore_runtime/events.py` | `handle(event, cwd, path=, cmd=) -> dict` |
| `runtime/lore_runtime/cli.py` | argparse CLI |
| `bin/lore-event` | Shim setting PYTHONPATH |
| `adapters/common.sh` | Resolve skill root; run lore-event |
| `runtime/tests/fixtures/mini-ws/` | Fixture workspace |
| `runtime/tests/test_events.py` | Unit tests |
| `cursor-hooks/*.sh` | Thin Cursor adapters |
| `scripts/match-trigger.sh` | Facade |
| `scripts/on-session-start.sh` | Facade (preserve text/json + exit codes) |
| `install.sh` | Claude hook command → lore-event health |
| `lore-extension/index.ts` | Spawn CLI instead of inline parse |
| `docs/adapters.md` | Capability matrix |
| `README.md` / `README.zh.md` | Note runtime |

---

### Task 1: Fixture + EventResult + failing health test

**Files:**
- Create: `runtime/lore_runtime/__init__.py`
- Create: `runtime/lore_runtime/types.py`
- Create: `runtime/tests/fixtures/mini-ws/.pikb/MAP.md`
- Create: `runtime/tests/fixtures/mini-ws/.pikb/CONVENTIONS.md`
- Create: `runtime/tests/fixtures/mini-ws/.pikb/PITFALLS.md`
- Create: `runtime/tests/fixtures/mini-ws/app/.pi/kb/CONTEXT.md`
- Create: `runtime/tests/test_events.py`
- Create: `runtime/tests/__init__.py`

**Interfaces:**
- Produces: fixture layout; test imports `lore_runtime.events.handle` (not implemented yet)

- [ ] **Step 1: Create package stubs and fixture files**

`runtime/lore_runtime/__init__.py`:
```python
"""lore shared runtime — platform-agnostic KB events."""
__version__ = "0.1.0"
```

`runtime/lore_runtime/types.py`:
```python
"""Canonical event result keys (dict, not a class — JSON-friendly)."""

STATUS_HEALTHY = "healthy"
STATUS_DEGRADED = "degraded"
STATUS_MISSING = "missing"

REQUIRED_KEYS = (
    "ok", "event", "cwd", "status", "context_path",
    "additional_context", "warnings", "env", "matches",
)

def empty_result(event: str, cwd: str) -> dict:
    return {
        "ok": True,
        "event": event,
        "cwd": cwd,
        "status": STATUS_MISSING,
        "context_path": None,
        "additional_context": "",
        "warnings": [],
        "env": {"LORE_LOADED": "0", "LORE_CONTEXT": "", "LORE_CWD": cwd},
        "matches": [],
    }
```

Fixture `CONTEXT.md`:
```markdown
# mini-app

Test app for lore_runtime.

@workspace → ../.pikb/MAP.md
```

Fixture `MAP.md`:
```markdown
# Workspace Map

| Repo | Layer |
|------|-------|
| app | service |
```

Fixture `CONVENTIONS.md`:
```markdown
# Conventions

Use clear names.
```

Fixture `PITFALLS.md`:
```markdown
## 1. Auth middleware order

- Difficulty: ⭐⭐⭐
- Symptom: 401
- Root Cause: order
- Solution: fix order
- Triggers: `file:middleware/auth` | `cmd:migrate auth`

## 2. Unrelated trap

- Difficulty: ⭐
- Triggers: `file:unrelated`
```

- [ ] **Step 2: Write failing unit test for health on empty dir**

`runtime/tests/test_events.py`:
```python
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
```

- [ ] **Step 3: Run test — expect ImportError / fail**

Run:
```bash
cd /Users/haha/projects/lore
PYTHONPATH=runtime python3 -m unittest runtime.tests.test_events.TestHealth -v
```
Expected: FAIL (`No module named lore_runtime.events` or `cannot import handle`)

- [ ] **Step 4: Commit scaffold + failing test**

```bash
git add runtime/
git commit -m "test: scaffold lore_runtime fixture and failing health test"
```

---

### Task 2: discover + health + make health test pass

**Files:**
- Create: `runtime/lore_runtime/discover.py`
- Create: `runtime/lore_runtime/health.py`
- Create: `runtime/lore_runtime/events.py`
- Modify: `runtime/tests/test_events.py` (add fixture healthy case)

**Interfaces:**
- Produces: `discover.find_context(cwd) -> Path|None`, `discover.find_pikb(cwd) -> Path|None`, `discover.find_pitfalls(cwd) -> list[Path]`, `health.check(cwd) -> dict` partial fields, `events.handle(event, cwd, path=None, cmd=None) -> dict`

- [ ] **Step 1: Implement discover.py**

```python
from pathlib import Path
from typing import List, Optional


def find_context(start: str) -> Optional[Path]:
    cur = Path(start).resolve()
    for _ in range(8):
        ctx = cur / ".pi" / "kb" / "CONTEXT.md"
        if ctx.is_file():
            return ctx
        if cur.parent == cur:
            break
        cur = cur.parent
    return None


def find_pikb(start: str) -> Optional[Path]:
    cur = Path(start).resolve()
    for _ in range(8):
        pikb = cur / ".pikb"
        if pikb.is_dir():
            return pikb
        if cur.parent == cur:
            break
        cur = cur.parent
    return None


def find_pitfalls(start: str) -> List[Path]:
    found = []
    cur = Path(start).resolve()
    seen = set()
    for _ in range(8):
        for rel in (".pikb/PITFALLS.md", ".pi/kb/PITFALLS.md"):
            p = cur / rel
            try:
                key = str(p.resolve())
            except Exception:
                continue
            if key in seen:
                continue
            if p.is_file():
                seen.add(key)
                found.append(p)
        if cur.parent == cur:
            break
        cur = cur.parent
    return found


def find_map(start: str, ctx: Optional[Path] = None) -> Optional[Path]:
    candidates = []
    start_p = Path(start).resolve()
    candidates.append(start_p / ".pikb" / "MAP.md")
    candidates.append(start_p.parent / ".pikb" / "MAP.md")
    pikb = find_pikb(start)
    if pikb:
        candidates.append(pikb / "MAP.md")
    if ctx is not None:
        if len(ctx.parents) > 2:
            candidates.append(ctx.parents[2] / ".pikb" / "MAP.md")
        if len(ctx.parents) > 3:
            candidates.append(ctx.parents[3] / ".pikb" / "MAP.md")
    seen = set()
    for c in candidates:
        try:
            key = str(c.resolve())
        except Exception:
            continue
        if key in seen:
            continue
        seen.add(key)
        if c.is_file():
            return c
    return None
```

- [ ] **Step 2: Implement health.py (port core checks from on-session-start.sh)**

Port: `.pikb` exists, has md files, CONTEXT at cwd or note coverage lightly (v1: check `find_context` and pikb non-empty; skip full repo scan OR port repo scan as in script — **port repo scan** for parity with existing script).

Return dict: `{"status": "...", "warnings": [str, ...], "ok_items": [str, ...]}`.

- [ ] **Step 3: Implement events.handle for health only**

```python
from lore_runtime.types import empty_result, STATUS_HEALTHY, STATUS_DEGRADED, STATUS_MISSING
from lore_runtime import health as health_mod
from lore_runtime import discover

def handle(event: str, cwd: str, path: str = None, cmd: str = None) -> dict:
    cwd = str(Path(cwd).resolve())
    if event == "health":
        return _health_event(cwd)
    r = empty_result(event, cwd)
    r["ok"] = False
    r["warnings"] = ["unknown event: %s" % event]
    return r

def _health_event(cwd: str) -> dict:
    r = empty_result("health", cwd)
    h = health_mod.check(cwd)
    r["status"] = h["status"]
    r["warnings"] = h["warnings"]
    ctx = discover.find_context(cwd)
    r["context_path"] = str(ctx) if ctx else None
    r["env"] = {
        "LORE_LOADED": "1" if ctx else "0",
        "LORE_CONTEXT": str(ctx) if ctx else "",
        "LORE_CWD": cwd,
    }
    return r
```

- [ ] **Step 4: Add fixture health test; run all health tests**

Add to `test_events.py`:
```python
    def test_health_fixture_not_missing(self):
        from lore_runtime.events import handle
        r = handle("health", str(FIXTURE / "app"))
        self.assertIn(r["status"], ("healthy", "degraded"))
        self.assertIsNotNone(r["context_path"])
```

Run:
```bash
PYTHONPATH=runtime python3 -m unittest runtime.tests.test_events.TestHealth -v
```
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add runtime/lore_runtime/
git commit -m "feat: lore_runtime discover + health event"
```

---

### Task 3: session_start (context + MAP + rules)

**Files:**
- Create: `runtime/lore_runtime/context.py`
- Modify: `runtime/lore_runtime/events.py`
- Modify: `runtime/tests/test_events.py`

**Interfaces:**
- Produces: `context.build_session_additional_context(cwd) -> (text, context_path, warnings)`
- Extends: `handle("session_start", cwd)`

- [ ] **Step 1: Write failing session_start tests**

```python
class TestSessionStart(unittest.TestCase):
    def test_session_start_includes_context_and_marker(self):
        from lore_runtime.events import handle
        r = handle("session_start", str(FIXTURE / "app"))
        self.assertTrue(r["ok"])
        self.assertIn("📚 lore loaded", r["additional_context"])
        self.assertIn("mini-app", r["additional_context"])
        self.assertEqual(r["env"]["LORE_LOADED"], "1")
        self.assertIn("Workspace Map", r["additional_context"])  # MAP pulled via @workspace
```

Run — expect FAIL until implemented.

- [ ] **Step 2: Implement context.py**

- Rules blurb (same content as current `cursor-hooks/session-start.sh` RULES string)
- Read CONTEXT ≤2048 chars
- If `@workspace` or `.pikb` in text, append MAP first 80 lines
- If no CONTEXT, additional_context still includes RULES + missing note

- [ ] **Step 3: Wire `session_start` in events.handle; merge health warnings into warnings / status**

`status`: use health.check; if missing CONTEXT but pikb exists → degraded; etc.

- [ ] **Step 4: Run tests — PASS**

```bash
PYTHONPATH=runtime python3 -m unittest runtime.tests.test_events.TestSessionStart -v
```

- [ ] **Step 5: Commit**

```bash
git commit -am "feat: lore_runtime session_start context injection"
```

---

### Task 4: pitfalls after_edit / after_shell

**Files:**
- Create: `runtime/lore_runtime/pitfalls.py`
- Modify: `runtime/lore_runtime/events.py`
- Modify: `runtime/tests/test_events.py`

**Interfaces:**
- Produces: `pitfalls.match(cwd, path="", cmd="") -> list[{"id","title","difficulty"}]`
- Extends: `handle("after_edit"|"after_shell", ...)`

- [ ] **Step 1: Write failing match tests**

```python
class TestPitfalls(unittest.TestCase):
    def test_after_edit_hit(self):
        from lore_runtime.events import handle
        r = handle("after_edit", str(FIXTURE / "app"), path=str(FIXTURE / "app" / "middleware" / "auth.ts"))
        self.assertEqual(len(r["matches"]), 1)
        self.assertEqual(r["matches"][0]["id"], "1")
        self.assertIn("Auth middleware", r["additional_context"])

    def test_after_edit_miss(self):
        from lore_runtime.events import handle
        r = handle("after_edit", str(FIXTURE / "app"), path=str(FIXTURE / "app" / "other.ts"))
        self.assertEqual(r["matches"], [])
        self.assertEqual(r["additional_context"], "")

    def test_after_shell_hit(self):
        from lore_runtime.events import handle
        r = handle("after_shell", str(FIXTURE / "app"), cmd="npm run migrate auth")
        self.assertEqual(r["matches"][0]["id"], "1")
```

- [ ] **Step 2: Implement pitfalls.py** (port logic from current `scripts/match-trigger.sh` Python block)

- [ ] **Step 3: Wire events; format `additional_context` like match-trigger human lines when matches non-empty**

- [ ] **Step 4: Run tests — PASS**

```bash
PYTHONPATH=runtime python3 -m unittest runtime.tests.test_events.TestPitfalls -v
```

- [ ] **Step 5: Commit**

```bash
git commit -am "feat: lore_runtime pitfalls after_edit/after_shell"
```

---

### Task 5: CLI + bin/lore-event

**Files:**
- Create: `runtime/lore_runtime/cli.py`
- Create: `bin/lore-event`
- Modify: `runtime/tests/test_events.py` (CLI subprocess test)

**Interfaces:**
- Produces: `python3 -m lore_runtime.cli <event> [--cwd DIR] [--path FILE] [--cmd STR]`

- [ ] **Step 1: Write failing CLI test**

```python
class TestCLI(unittest.TestCase):
    def test_cli_json_stdout(self):
        import subprocess, sys
        env = os.environ.copy()
        env["PYTHONPATH"] = str(ROOT)
        p = subprocess.run(
            [sys.executable, "-m", "lore_runtime.cli", "health", "--cwd", str(FIXTURE / "app")],
            capture_output=True, text=True, env=env,
        )
        self.assertEqual(p.returncode, 0)
        data = json.loads(p.stdout)
        self.assertEqual(data["event"], "health")
```

- [ ] **Step 2: Implement cli.py**

```python
import argparse, json, sys
from lore_runtime.events import handle

def main(argv=None):
    parser = argparse.ArgumentParser(prog="lore-event")
    parser.add_argument("event", choices=["session_start", "after_edit", "after_shell", "health"])
    parser.add_argument("--cwd", default=".")
    parser.add_argument("--path", default="")
    parser.add_argument("--cmd", default="")
    args = parser.parse_args(argv)
    try:
        result = handle(args.event, args.cwd, path=args.path or None, cmd=args.cmd or None)
    except Exception as e:
        result = {
            "ok": False, "event": args.event, "cwd": args.cwd, "status": "missing",
            "context_path": None, "additional_context": "", "warnings": [str(e)],
            "env": {}, "matches": [],
        }
    sys.stdout.write(json.dumps(result, ensure_ascii=False))
    sys.stdout.write("\n")
    return 0

if __name__ == "__main__":
    raise SystemExit(main())
```

Ensure `lore_runtime` is a package runnable as `-m lore_runtime.cli` (add `runtime/lore_runtime/__main__.py` optional that calls cli.main, **or** document `-m lore_runtime.cli` only — prefer `__main__.py` forwarding to cli for `python -m lore_runtime`).

Add `runtime/lore_runtime/__main__.py`:
```python
from lore_runtime.cli import main
raise SystemExit(main())
```

- [ ] **Step 3: Create `bin/lore-event`**

```bash
#!/usr/bin/env bash
set -euo pipefail
ROOT="$(cd "$(dirname "$0")/.." && pwd -P)"
export PYTHONPATH="${ROOT}/runtime${PYTHONPATH:+:$PYTHONPATH}"
exec python3 -m lore_runtime "$@"
```

`chmod +x bin/lore-event`

- [ ] **Step 4: Run CLI test — PASS**

```bash
PYTHONPATH=runtime python3 -m unittest runtime.tests.test_events.TestCLI -v
./bin/lore-event health --cwd runtime/tests/fixtures/mini-ws/app | python3 -m json.tool >/dev/null
```

- [ ] **Step 5: Commit**

```bash
git add bin/lore-event runtime/lore_runtime/cli.py runtime/lore_runtime/__main__.py runtime/tests/test_events.py
git commit -m "feat: lore-event CLI for runtime events"
```

---

### Task 6: adapters/common.sh + thin Cursor hooks

**Files:**
- Create: `adapters/common.sh`
- Modify: `cursor-hooks/session-start.sh` (replace body)
- Modify: `cursor-hooks/post-tool-use.sh` (replace body)

**Interfaces:**
- Consumes: `bin/lore-event` JSON
- Produces: Cursor `{additional_context, env?}` / `{}`

- [ ] **Step 1: Write `adapters/common.sh`**

```bash
#!/usr/bin/env bash
# Resolve lore skill root and run lore-event.
lore_root() {
  local cands=(
    "${LORE_ROOT:-}"
    "${HOME}/.agents/skills/lore"
    "$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd -P)"
  )
  local c
  for c in "${cands[@]}"; do
    [[ -n "$c" && -x "$c/bin/lore-event" ]] && { echo "$c"; return 0; }
    [[ -n "$c" && -f "$c/runtime/lore_runtime/cli.py" ]] && { echo "$c"; return 0; }
  done
  return 1
}

lore_event() {
  local root
  root="$(lore_root)" || return 1
  if [[ -x "$root/bin/lore-event" ]]; then
    "$root/bin/lore-event" "$@"
  else
    PYTHONPATH="$root/runtime" python3 -m lore_runtime "$@"
  fi
}
```

- [ ] **Step 2: Rewrite `cursor-hooks/session-start.sh`**

Read stdin JSON → extract cwd → `lore_event session_start --cwd …` → map to Cursor output:
```json
{"additional_context": "<from result>", "env": <from result.env>}
```
On failure: `echo '{}'`

- [ ] **Step 3: Rewrite `cursor-hooks/post-tool-use.sh`**

Parse tool_name / tool_input / cwd; call `after_edit` or `after_shell` or throttled `health` (keep 300s stamp `/tmp/.lore-cursor-check`); combine `additional_context` from matches + health warnings; else `{}`.

- [ ] **Step 4: Smoke**

```bash
./install.sh install --to cursor
echo '{"cwd":"'"$PWD"'/runtime/tests/fixtures/mini-ws/app","workspace_roots":["'"$PWD"'/runtime/tests/fixtures/mini-ws/app"]}' \
  | bash ~/.cursor/hooks/lore-session-start.sh | python3 -c 'import json,sys; d=json.load(sys.stdin); assert "additional_context" in d and d.get("env",{}).get("LORE_LOADED")=="1"'
```
Expected: assertion passes

- [ ] **Step 5: Commit**

```bash
git add adapters/common.sh cursor-hooks/
git commit -m "refactor: Cursor hooks call lore-event only"
```

---

### Task 7: Script facades (match-trigger + on-session-start)

**Files:**
- Modify: `scripts/match-trigger.sh`
- Modify: `scripts/on-session-start.sh`

**Interfaces:**
- Preserve: match-trigger human stdout + exit 0; on-session-start text/json and exit 1 when unhealthy / missing pikb (legacy)

- [ ] **Step 1: Rewrite match-trigger.sh as facade**

```bash
#!/usr/bin/env bash
set -euo pipefail
input="${1:-}"; cmd="${2:-}"
ROOT="$(cd "$(dirname "$0")/.." && pwd -P)"
# shellcheck source=adapters/common.sh
source "$ROOT/adapters/common.sh"
cwd="$(pwd)"
[[ -n "$input" && "$input" == /* ]] && cwd="$(dirname "$input")"
out="$(lore_event after_edit --cwd "$cwd" --path "$input" --cmd "$cmd" 2>/dev/null || true)"
# If only cmd provided without path semantics, also try after_shell when path empty:
# Prefer: if path set use after_edit; elif cmd use after_shell
```

Actually: if `input` non-empty → `after_edit`; elif `cmd` → `after_shell`; if both, call once with both path and cmd on `after_edit` then merge — simpler: always call a small python one-liner OR extend CLI to accept both (already does on after_edit). Spec: `after_edit` uses path; `after_shell` uses cmd. Facade:

```bash
if [[ -n "$input" ]]; then
  json="$(lore_event after_edit --cwd "$cwd" --path "$input")"
elif [[ -n "$cmd" ]]; then
  json="$(lore_event after_shell --cwd "$cwd" --cmd "$cmd")"
else
  exit 0
fi
# print additional_context if non-empty
```

- [ ] **Step 2: Verify facade against fixture**

```bash
cd runtime/tests/fixtures/mini-ws/app
bash ../../../../scripts/match-trigger.sh "$(pwd)/middleware/auth.ts" ""
```
Expected: stdout contains `Auth middleware order`

- [ ] **Step 3: Rewrite on-session-start.sh**

Keep flag parsing (`--json` / path). Call `lore_event health --cwd "$WORKSPACE"`.  
- `--json`: map runtime result to **legacy** shape `{workspace, has_pikb, ok, warnings, healthy}` for pi extension compatibility (extension parses this). Implement mapping in a few lines of python in the script.
- text mode: print lore-styled lines from warnings/status; `exit 1` if status is `missing` or warnings non-empty (preserve old behavior: exit 1 when not healthy).

Read current extension expectations: `on-session-start.sh --json` → `healthy`, `warnings`, `has_pikb`. Map:
- `has_pikb` = status != missing OR context/pikb found
- `healthy` = status == healthy
- `warnings` = `[{"item":"health","detail": w} for w in warnings]`

- [ ] **Step 4: Smoke old CLIs**

```bash
bash scripts/on-session-start.sh runtime/tests/fixtures/mini-ws; echo exit:$?
bash scripts/on-session-start.sh --json runtime/tests/fixtures/mini-ws/app | python3 -m json.tool
```

- [ ] **Step 5: Commit**

```bash
git commit -am "refactor: on-session-start and match-trigger facade lore-event"
```

---

### Task 8: Claude hook via install.sh

**Files:**
- Modify: `install.sh` (`_hook_add` command string ~line 227)

**Interfaces:**
- Claude PostToolUse runs throttled `lore-event health` instead of bash `on-session-start.sh` (facade still OK — either is fine; prefer `bin/lore-event` for directness)

- [ ] **Step 1: Replace lore hook command in `_hook_add`**

New command (conceptually):
```bash
[ -x "$HOME/.agents/skills/lore/bin/lore-event" ] || return 0
STAMP=/tmp/.lore-check; NOW=$(date +%s); LAST=$(cat $STAMP 2>/dev/null || echo 0)
[ $((NOW - LAST)) -lt 300 ] && return 0; echo $NOW > $STAMP
out=$("$HOME/.agents/skills/lore/bin/lore-event" health --cwd "$PWD" 2>/dev/null) || return 0
echo "$out" | python3 -c 'import json,sys; d=json.load(sys.stdin); ws=d.get("warnings") or [];
import sys
(sys.exit(0) if d.get("status")=="healthy" and not ws else print("[lore] "+"; ".join(ws[:3]) if ws else "[lore] status="+d.get("status","")))'
```

Keep matcher `lore-check` / `lore-event` detection in `_hook_has_lore` / remove — update string match to `lore-event` or `lore-check`.

- [ ] **Step 2: Update `_hook_has_lore` / `_hook_remove` to recognize `lore-event`**

- [ ] **Step 3: Dry-run logic by extracting command to a test snippet OR run `install.sh install --to claude` on machine with settings.json**

```bash
./install.sh install --to claude
./install.sh status --to claude
```
Expected: PostToolUse hook installed

- [ ] **Step 4: Commit**

```bash
git commit -am "refactor: Claude PostToolUse hook calls lore-event health"
```

---

### Task 9: pi extension uses lore-event

**Files:**
- Modify: `lore-extension/index.ts`

**Interfaces:**
- Replace inline CONTEXT read / PITFALLS parse with `runScript` equivalent spawning `bin/lore-event`
- Keep notify / sendMessage / status UI

- [ ] **Step 1: Add helper `runLoreEvent(event, args)` in index.ts**

Use `execSync` with `PYTHONPATH` or `bin/lore-event`, parse JSON, timeout 5s, return object or null.

- [ ] **Step 2: session_start handler**

Call `session_start`; if `additional_context`, `pi.sendMessage` with that content (or keep slice); notify `📚 lore loaded` when `env.LORE_LOADED==="1"`.

- [ ] **Step 3: tool_call pitfalls**

On path/cmd, call `after_edit` or `after_shell`; if matches length, notify + queue inject before_agent_start from `additional_context` / matches titles.

Remove `loadPitfalls` / `matchPitfall` local parsers.

- [ ] **Step 4: turn_end health**

Call `health` instead of `on-session-start.sh` text parse where possible; keep fallback to script if CLI missing.

- [ ] **Step 5: Manual sanity** — if pi available, open fixture workspace; else rely on `tsc`/syntax check:

```bash
# if project has no tsc build, skip; at least ensure no leftover references to loadPitfalls
grep -n 'loadPitfalls\|matchPitfall' lore-extension/index.ts && exit 1 || true
```

- [ ] **Step 6: Commit**

```bash
git commit -am "refactor: pi extension delegates KB events to lore-event"
```

---

### Task 10: Docs (adapters matrix + README)

**Files:**
- Create: `docs/adapters.md`
- Modify: `README.md`
- Modify: `README.zh.md`
- Modify: `SKILL.md` (mention runtime briefly under scripts/cross-agent)

- [ ] **Step 1: Write `docs/adapters.md`**

Table: capability → runtime event → pi / Claude / Cursor adapter mechanism → status ✅.

- [ ] **Step 2: README Agents section — note shared `lore_runtime` + `bin/lore-event`**

- [ ] **Step 3: Run full unit suite**

```bash
PYTHONPATH=runtime python3 -m unittest discover -s runtime/tests -v
```
Expected: all PASS

- [ ] **Step 4: Commit**

```bash
git add docs/adapters.md README.md README.zh.md SKILL.md
git commit -m "docs: adapter matrix for lore_runtime D3"
```

---

## Spec coverage check

| Spec item | Task |
|-----------|------|
| Python runtime layout | 1–5 |
| Events + JSON contract | 2–5 |
| Cursor thin hooks | 6 |
| Script facades | 7 |
| Claude hook | 8 |
| pi extension | 9 |
| docs/adapters.md + README | 10 |
| unittest + fixture | 1–5 |
| Non-goals (no scan/graph/audit move) | omitted by design |
| Soft-fail adapters | 6–8 |

## Placeholder / consistency review

- Event names: `session_start` | `after_edit` | `after_shell` | `health` throughout.
- CLI module: `lore_runtime.cli` + `__main__.py` → `python -m lore_runtime`.
- Legacy on-session-start exit codes preserved in Task 7 (explicitly different from CLI always-0).

---

## Execution handoff

Plan complete and saved to `docs/superpowers/plans/2026-08-06-lore-runtime-adapters.md`.

**Two execution options:**

1. **Subagent-Driven (recommended)** — fresh subagent per task, review between tasks  
2. **Inline Execution** — execute tasks in this session with executing-plans checkpoints  

Which approach?
