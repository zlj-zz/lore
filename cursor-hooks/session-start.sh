#!/usr/bin/env bash
# lore Cursor hook: sessionStart — inject KB context via lore-event.
# stdin: Cursor hook JSON. stdout: {"additional_context", "env"} or {}.
set -uo pipefail

SOURCE="${BASH_SOURCE[0]}"
while [[ -h "$SOURCE" ]]; do
  DIR="$(cd -P "$(dirname "$SOURCE")" && pwd)"
  SOURCE="$(readlink "$SOURCE")"
  [[ "$SOURCE" != /* ]] && SOURCE="$DIR/$SOURCE"
done
ROOT="$(cd -P "$(dirname "$SOURCE")/.." && pwd)"
# shellcheck source=../adapters/common.sh
source "$ROOT/adapters/common.sh"

payload="$(cat || true)"
cwd="$(printf '%s' "$payload" | python3 -c '
import json, sys
from pathlib import Path
try:
    p = json.load(sys.stdin)
except Exception:
    sys.exit(1)
roots = p.get("workspace_roots") or []
cwd = p.get("cwd") or (roots[0] if roots else "")
if cwd:
    print(str(Path(cwd).resolve()))
' 2>/dev/null)" || true

if [[ -z "${cwd:-}" ]]; then
  echo '{}'
  exit 0
fi

if ! json="$(lore_event session_start --cwd "$cwd" 2>/dev/null)"; then
  echo '{}'
  exit 0
fi

printf '%s' "$json" | python3 -c '
import json, sys
try:
    r = json.load(sys.stdin)
    print(json.dumps({
        "additional_context": r.get("additional_context", ""),
        "env": r.get("env") or {},
    }, ensure_ascii=False))
except Exception:
    print("{}")
' 2>/dev/null || echo '{}'
