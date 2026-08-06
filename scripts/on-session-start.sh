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

ROOT="$(cd "$(dirname "$0")/.." && pwd -P)"
# shellcheck source=../adapters/common.sh
source "$ROOT/adapters/common.sh"

json="$(lore_event health --cwd "$WORKSPACE" 2>/dev/null || echo '{}')"

export WORKSPACE OUTPUT_MODE LORE_HEALTH_JSON="$json" LORE_ROOT="$ROOT"
python3 <<'PY'
import json, os, sys

workspace = os.environ["WORKSPACE"]
output_mode = os.environ.get("OUTPUT_MODE", "text")

try:
    r = json.loads(os.environ.get("LORE_HEALTH_JSON", "{}"))
except Exception:
    r = {}

status = r.get("status", "missing")
context_path = r.get("context_path")
raw_warnings = r.get("warnings") or []

has_pikb = status != "missing" or bool(context_path)
healthy = status == "healthy"

def split_item(s):
    if ": " in s:
        return s.split(": ", 1)
    return "health", s

warnings = [split_item(w) for w in raw_warnings]

sys.path.insert(0, os.path.join(os.environ["LORE_ROOT"], "runtime"))
try:
    from lore_runtime import health as health_mod
    ok_items = [split_item(x) for x in health_mod.check(workspace)["ok_items"]]
except Exception:
    ok_items = []
    if has_pikb:
        ok_items.append((".pikb/", "exists"))
    if context_path:
        ok_items.append(("CONTEXT.md", "exists"))

if output_mode == "json":
    out = {
        "workspace": workspace,
        "has_pikb": has_pikb,
        "ok": [{"item": item, "detail": detail} for item, detail in ok_items],
        "warnings": [{"item": item, "detail": detail} for item, detail in warnings],
        "healthy": healthy,
    }
    print(json.dumps(out, indent=2, ensure_ascii=False))
    sys.exit(0 if healthy else 1)

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
sys.exit(1 if (status == "missing" or warnings) else 0)
PY
