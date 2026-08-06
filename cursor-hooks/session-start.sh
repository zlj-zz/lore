#!/usr/bin/env bash
# lore Cursor hook: sessionStart — inject KB context + behavioral rules.
# stdin: Cursor hook JSON. stdout: {"additional_context": "..."}. Never blocks.
set -euo pipefail

export LORE_PAYLOAD
LORE_PAYLOAD="$(cat)"

python3 <<'PY'
import json, os, subprocess
from pathlib import Path

payload = json.loads(os.environ.get("LORE_PAYLOAD") or "{}")
roots = payload.get("workspace_roots") or []
cwd = payload.get("cwd") or (roots[0] if roots else os.getcwd())
cwd = str(Path(cwd).resolve())

RULES = """## Knowledge Base (lore)

On session start: CONTEXT.md is injected below when present. Output 📚 lore loaded.

During work:
- Writing code → check .pikb/CONVENTIONS.md
- Multi-module changes → check .pikb/MAP.md
- Error / risky edit → check .pikb/PITFALLS.md (and .pi/kb/PITFALLS.md)
- New repo → create .pi/kb/CONTEXT.md
- Significant change → ask: "knowledge base 需要更新吗?"

Search KB: `~/.agents/skills/lore/scripts/quick-ref.sh <keyword>`
Missing KB in complex workspace → `/skill:lore 创建知识库`"""


def find_context(start):
    cur = start
    for _ in range(8):
        ctx = cur / ".pi" / "kb" / "CONTEXT.md"
        if ctx.is_file():
            return ctx
        if cur.parent == cur:
            break
        cur = cur.parent
    return None


def find_map(start, ctx):
    seen = set()
    candidates = [start / ".pikb" / "MAP.md", start.parent / ".pikb" / "MAP.md"]
    if ctx is not None:
        # repo/.pi/kb/CONTEXT.md → workspace .pikb one or two levels up
        if len(ctx.parents) > 2:
            candidates.append(ctx.parents[2] / ".pikb" / "MAP.md")
        if len(ctx.parents) > 3:
            candidates.append(ctx.parents[3] / ".pikb" / "MAP.md")
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


parts = [RULES]
ctx = find_context(Path(cwd))
if ctx:
    text = ctx.read_text(encoding="utf-8", errors="replace")[:2048]
    parts.append("📚 lore loaded\n\n# CONTEXT.md (%s)\n\n%s" % (ctx, text))
    if "@workspace" in text or ".pikb" in text:
        mp = find_map(Path(cwd), ctx)
        if mp:
            lines = mp.read_text(encoding="utf-8", errors="replace").splitlines()[:80]
            parts.append("## Workspace Map (summary)\n\n" + "\n".join(lines))
else:
    parts.append(
        "[lore] No .pi/kb/CONTEXT.md under %s. "
        "Run /skill:lore 创建知识库 if this is a multi-repo workspace." % cwd
    )

health_script = Path(os.path.expanduser("~/.agents/skills/lore/scripts/on-session-start.sh"))
if health_script.is_file():
    try:
        r = subprocess.run(
            ["bash", str(health_script), cwd],
            capture_output=True, text=True, timeout=8,
        )
        out = (r.stdout or r.stderr or "").strip()
        if out and ("⚠" in out or r.returncode != 0):
            if "not found" not in out or ctx is not None:
                parts.append("[lore] health:\n" + out[:1500])
    except Exception:
        pass

print(json.dumps({"additional_context": "\n\n".join(parts)}, ensure_ascii=False))
PY
