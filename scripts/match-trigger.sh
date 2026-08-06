#!/usr/bin/env bash
# match-trigger.sh — Check if a file path or command matches PITFALLS triggers
# Usage: match-trigger.sh <file_path> [command]
# Returns: exit 0 + echo warning if matched; exit 1 if no match
set -euo pipefail

input="${1:-}"
cmd="${2:-}"

find_kb() {
  local dir="$1"
  # Walk up to find .pikb/ or .pi/kb/
  while [[ "$dir" != "/" && "$dir" != "." ]]; do
    for kb in "$dir/.pikb/PITFALLS.md" "$dir/.pi/kb/PITFALLS.md"; do
      [[ -f "$kb" ]] && { echo "$kb"; return 0; }
    done
    dir="$(dirname "$dir")"
  done
  return 1
}

PITFALLS=$(find_kb "$(pwd)" 2>/dev/null || true)
if [[ -z "${PITFALLS:-}" ]]; then
  exit 0  # no KB, nothing to match
fi

# Extract filename from path for matching file: triggers
filename=$(basename "$input" 2>/dev/null || echo "")

# Check if input or command matches any trigger line
matched=false
while IFS= read -r line; do
  # Parse triggers line: Triggers: `file:x` | `api:y` | `cmd:z`
  # Match file: triggers against the input path/filename
  if [[ -n "$input" ]]; then
    file_triggers=$(echo "$line" | grep -o '`file:[^`]*`' | sed 's/`file://g;s/`//g' || true)
    for t in $file_triggers; do
      if [[ "$input" == *"$t"* ]]; then
        matched=true
        break 2
      fi
    done
  fi
  # Match cmd: triggers against the command
  if [[ -n "$cmd" ]]; then
    cmd_triggers=$(echo "$line" | grep -o '`cmd:[^`]*`' | sed 's/`cmd://g;s/`//g' || true)
    for t in $cmd_triggers; do
      if [[ "$cmd" == *"$t"* ]]; then
        matched=true
        break 2
      fi
    done
  fi
done < <(grep 'Triggers:' "$PITFALLS" 2>/dev/null || true)

if $matched; then
  echo "[lore] ⚠️  PITFALLS match — check ${PITFALLS}"
  exit 0
fi
exit 0  # don't block execution, just warn
