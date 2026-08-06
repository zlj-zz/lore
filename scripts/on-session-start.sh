#!/usr/bin/env bash
# on-session-start.sh — quick KB health check for agent session startup.
#
# Usage:
#   ./scripts/on-session-start.sh [path]    # check workspace
#   ./scripts/on-session-start.sh --json    # structured output for agent consumption
#   ./scripts/on-session-start.sh --help
#
# Designed to be called from AGENTS.md or a PostToolUse hook.
# Exit 0: KB healthy. Exit 1: KB needs attention (warnings present).
#
# Requires: bash, python3.

set -euo pipefail

WORKSPACE="${1:-.}"
OUTPUT_MODE="text"

# parse flags
while [[ $# -gt 0 ]]; do
  case "$1" in
    --json) OUTPUT_MODE="json"; shift ;;
    --text) OUTPUT_MODE="text"; shift ;;
    -h|--help)
      cat <<EOF
Usage: $(basename "$0") [path] [--json|--text]

Check knowledge base health at session start.
Exit 0: all good.  Exit 1: warnings found.

Flags:
  --json   structured output for agent consumption
  --text   human-readable output (default)
EOF
      exit 0
      ;;
    *) WORKSPACE="$1"; shift ;;
  esac
done

WORKSPACE="$(cd "$WORKSPACE" 2>/dev/null && pwd -P)" || {
  echo "[lore] ✗ cannot access workspace: $WORKSPACE"
  exit 1
}

export WORKSPACE OUTPUT_MODE
python3 <<'PY'
import os, json, sys, glob
from datetime import datetime, timezone

workspace = os.environ['WORKSPACE']
output_mode = os.environ.get('OUTPUT_MODE', 'text')
warnings = []
ok_items = []

# ── 1. Check .pikb/ existence ──
pikb = os.path.join(workspace, ".pikb")
has_pikb = os.path.isdir(pikb)

if has_pikb:
    ok_items.append((".pikb/", "exists"))
else:
    warnings.append(("KB", "missing — .pikb/ not found. Run /skill:lore 创建知识库"))

# ── 2. Check current repo CONTEXT.md ──
context_md = os.path.join(workspace, ".pi", "kb", "CONTEXT.md")
if os.path.isfile(context_md):
    ok_items.append(("CONTEXT.md", "exists"))
else:
    warnings.append(("CONTEXT.md", f"missing at {workspace}/.pi/kb/CONTEXT.md"))

# ── 3. Check if .pikb/ has content ──
if has_pikb:
    kb_files = []
    for root, dirs, files in os.walk(pikb):
        for f in files:
            if f.endswith(".md"):
                kb_files.append(os.path.join(root, f))
    if kb_files:
        ok_items.append(("KB files", f"{len(kb_files)} files"))

        # ── 4. KB freshness ──
        try:
            newest = max(os.path.getmtime(f) for f in kb_files)
            oldest = min(os.path.getmtime(f) for f in kb_files)
            age_days = (datetime.now().timestamp() - oldest) / 86400
            newest_age = (datetime.now().timestamp() - newest) / 86400

            if age_days > 30:
                warnings.append(("KB age", f"oldest file modified {age_days:.0f}d ago — may be stale"))
            elif age_days > 14:
                warnings.append(("KB age", f"oldest file modified {age_days:.0f}d ago"))
            else:
                ok_items.append(("KB freshness", f"{age_days:.0f}d old, newest {newest_age:.0f}d"))
        except Exception:
            pass

        # ── 5. Check repos without CONTEXT.md ──
        # scan for repos in workspace
        repo_markers = {"go.mod", "package.json", "Cargo.toml", ".git",
                        "pyproject.toml", "Gemfile", "pom.xml", "build.gradle"}
        repos_without_context = []
        try:
            for entry in sorted(os.listdir(workspace)):
                if entry.startswith("."):
                    continue
                full = os.path.join(workspace, entry)
                if not os.path.isdir(full):
                    continue
                entries = set(os.listdir(full))
                if entries & repo_markers:
                    # it's a repo
                    if not os.path.isfile(os.path.join(full, ".pi", "kb", "CONTEXT.md")):
                        repos_without_context.append(entry)
        except PermissionError:
            pass

        if repos_without_context:
            missing = ", ".join(repos_without_context[:5])
            suffix = "..." if len(repos_without_context) > 5 else ""
            warnings.append(("CONTEXT.md coverage", f"{len(repos_without_context)} repos missing: {missing}{suffix}"))
        else:
            ok_items.append(("CONTEXT.md coverage", "all repos covered"))

    else:
        warnings.append(("KB files", "empty — no .md files in .pikb/"))

# ── Output ──
if output_mode == "json":
    out = {
        "workspace": workspace,
        "has_pikb": has_pikb,
        "ok": [{"item": item, "detail": detail} for item, detail in ok_items],
        "warnings": [{"item": item, "detail": detail} for item, detail in warnings],
        "healthy": len(warnings) == 0,
    }
    print(json.dumps(out, indent=2, ensure_ascii=False))
else:
    # text mode
    print()
    print(f"\033[2m[lore]\033[0m workspace: \033[1m{workspace}\033[0m")
    print()

    if not has_pikb:
        print("  \033[33m⚠\033[0m  \033[2m.pikb/\033[0m not found")
        print("    →  run \033[1m/skill:lore 创建知识库\033[0m to initialize")
        print()
        sys.exit(1)

    for item, detail in ok_items:
        print(f"  \033[32m✓\033[0m  {item}: \033[2m{detail}\033[0m")

    for item, detail in warnings:
        print(f"  \033[33m⚠\033[0m  {item}: {detail}")

    if warnings:
        print()
        print(f"  \033[2m{warnings[0][1]}\033[0m")
    else:
        print()
        print(f"  \033[2mall good\033[0m")

    print()
    sys.exit(1 if warnings else 0)
PY
