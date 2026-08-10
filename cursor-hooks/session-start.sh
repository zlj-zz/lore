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

# ── Wave 2: catch up on leftover session_end tasks from previous session ──
catchup=""
if json2="$(lore_event session_end --cwd "$cwd" 2>/dev/null)"; then
  catchup="$(printf '%s' "$json2" | python3 -c '
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

LORE_CATCHUP="$catchup"

printf '%s' "$json" | python3 -c "
import json, sys, os
try:
    r = json.load(sys.stdin)
    ctx = r.get('additional_context', '')
    catchup = os.environ.get('LORE_CATCHUP', '')
    if catchup:
        ctx = catchup + '\n\n' + ctx if ctx else catchup
    print(json.dumps({
        'additional_context': ctx,
        'env': r.get('env') or {},
    }, ensure_ascii=False))
except Exception:
    print('{}')
" 2>/dev/null || echo '{}'
