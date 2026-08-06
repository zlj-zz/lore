#!/usr/bin/env bash
# lore Cursor hook: postToolUse — PITFALLS triggers + throttled KB health check.
# stdin: Cursor hook JSON. stdout: {"additional_context": "..."} or {}. Never blocks.
set -euo pipefail

export LORE_PAYLOAD
LORE_PAYLOAD="$(cat)"

python3 <<'PY'
import json, os, subprocess, time
from pathlib import Path

payload = json.loads(os.environ.get("LORE_PAYLOAD") or "{}")
cwd = payload.get("cwd") or os.getcwd()
tool = payload.get("tool_name") or ""
tin = payload.get("tool_input") or {}
if isinstance(tin, str):
    try:
        tin = json.loads(tin)
    except Exception:
        tin = {}

path = ""
cmd = ""
for key in ("path", "file_path", "target_notebook", "file"):
    v = tin.get(key)
    if isinstance(v, str) and v:
        path = v
        break
if tool in ("Shell", "Bash") or "shell" in tool.lower():
    c = tin.get("command")
    if isinstance(c, str):
        cmd = c

notes = []

match = os.path.expanduser("~/.agents/skills/lore/scripts/match-trigger.sh")
if os.path.isfile(match) and (path or cmd):
    try:
        r = subprocess.run(
            ["bash", match, path or "", cmd or ""],
            capture_output=True, text=True, timeout=5, cwd=cwd,
        )
        out = (r.stdout or "").strip()
        if out:
            notes.append(out)
    except Exception:
        pass

stamp = Path("/tmp/.lore-cursor-check")
now = int(time.time())
last = 0
try:
    last = int(stamp.read_text().strip() or "0")
except Exception:
    pass
if now - last >= 300:
    try:
        stamp.write_text(str(now))
    except Exception:
        pass
    health = os.path.expanduser("~/.agents/skills/lore/scripts/on-session-start.sh")
    if os.path.isfile(health):
        try:
            r = subprocess.run(
                ["bash", health, cwd],
                capture_output=True, text=True, timeout=8,
            )
            out = (r.stdout or r.stderr or "").strip()
            if out and "⚠" in out and "not found" not in out:
                notes.append("[lore] health:\n" + out[:1200])
        except Exception:
            pass

if notes:
    print(json.dumps({"additional_context": "\n\n".join(notes)}, ensure_ascii=False))
else:
    print("{}")
PY
