#!/usr/bin/env bash
# match-trigger.sh — Check if a file path or command matches PITFALLS triggers.
# Usage: match-trigger.sh <file_path> [command]
# Prints matched pitfall warnings to stdout; always exits 0 (never blocks).
set -euo pipefail

input="${1:-}"
cmd="${2:-}"

find_pitfalls() {
  local dir="$1"
  while [[ "$dir" != "/" && -n "$dir" ]]; do
    for kb in "$dir/.pikb/PITFALLS.md" "$dir/.pi/kb/PITFALLS.md"; do
      [[ -f "$kb" ]] && { echo "$kb"; return 0; }
    done
    dir="$(dirname "$dir")"
  done
  return 1
}

start_dir="$(pwd)"
if [[ -n "$input" && "$input" == /* ]]; then
  start_dir="$(dirname "$input")"
fi

PITFALLS="$(find_pitfalls "$start_dir" 2>/dev/null || true)"
if [[ -z "${PITFALLS:-}" ]]; then
  exit 0
fi

export MATCH_INPUT="$input"
export MATCH_CMD="$cmd"
export MATCH_PITFALLS="$PITFALLS"

python3 <<'PY'
import os, re

path = os.environ.get("MATCH_INPUT") or ""
cmd = os.environ.get("MATCH_CMD") or ""
pitfalls_path = os.environ["MATCH_PITFALLS"]

raw = open(pitfalls_path, encoding="utf-8", errors="replace").read()
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
    for t in re.findall(r"`(file|api|cmd):([^`]+)`", trig_str):
        kind, val = t
        if kind == "file" and path and val in path:
            hit = True
        elif kind == "cmd" and cmd and val in cmd:
            hit = True
    if hit:
        diff = sec.count("⭐")
        stars = "⭐" * diff if diff else ""
        matched.append((pid, title, stars))

if matched:
    lines = ["[lore] ⚠️ PITFALLS match — read %s before continuing:" % pitfalls_path]
    for pid, title, stars in matched:
        extra = (" (%s)" % stars) if stars else ""
        lines.append("  #%s %s%s" % (pid, title, extra))
    print("\n".join(lines))
PY

exit 0
