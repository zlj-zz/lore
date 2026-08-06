#!/usr/bin/env bash
# match-trigger.sh — Check if a file path or command matches PITFALLS triggers.
# Usage: match-trigger.sh <file_path> [command]
# Prints matched pitfall warnings to stdout; always exits 0 (never blocks).
set -euo pipefail

input="${1:-}"
cmd="${2:-}"

ROOT="$(cd "$(dirname "$0")/.." && pwd -P)"
# shellcheck source=../adapters/common.sh
source "$ROOT/adapters/common.sh"

cwd="$(pwd)"
[[ -n "$input" && "$input" == /* ]] && cwd="$(dirname "$input")"

json=""
if [[ -n "$input" ]]; then
  json="$(lore_event after_edit --cwd "$cwd" --path "$input" ${cmd:+--cmd "$cmd"} 2>/dev/null || true)"
elif [[ -n "$cmd" ]]; then
  json="$(lore_event after_shell --cwd "$cwd" --cmd "$cmd" 2>/dev/null || true)"
else
  exit 0
fi

if [[ -n "$json" ]]; then
  printf '%s' "$json" | python3 -c '
import json, sys
try:
    ctx = json.load(sys.stdin).get("additional_context", "")
    if ctx:
        print(ctx)
except Exception:
    pass
' 2>/dev/null || true
fi

exit 0
