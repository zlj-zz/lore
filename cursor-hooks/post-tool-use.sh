#!/usr/bin/env bash
# lore Cursor hook: postToolUse — PITFALLS + throttled health via lore-event.
# stdin: Cursor hook JSON. stdout: {"additional_context"} or {}.
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
LORE_CWD=""
LORE_PATH=""
LORE_CMD=""
{
  IFS= read -r LORE_CWD || true
  IFS= read -r LORE_PATH || true
  IFS= read -r LORE_CMD || true
} < <(printf '%s' "$payload" | python3 -c '
import json, sys
try:
    p = json.load(sys.stdin)
except Exception:
    sys.exit(0)
cwd = p.get("cwd") or ""
tool = p.get("tool_name") or ""
tin = p.get("tool_input") or {}
if isinstance(tin, str):
    try:
        tin = json.loads(tin)
    except Exception:
        tin = {}
path = ""
for key in ("path", "file_path", "target_notebook", "file"):
    v = tin.get(key)
    if isinstance(v, str) and v:
        path = v
        break
cmd = ""
if tool in ("Shell", "Bash") or "shell" in tool.lower():
    c = tin.get("command")
    if isinstance(c, str):
        cmd = c
print(cwd)
print(path)
print(cmd)
' 2>/dev/null || true)
[[ -z "$LORE_CWD" ]] && LORE_CWD="$(pwd)"

notes=()

if [[ -n "$LORE_PATH" ]]; then
  if json="$(lore_event after_edit --cwd "$LORE_CWD" --path "$LORE_PATH" ${LORE_CMD:+--cmd "$LORE_CMD"} 2>/dev/null)"; then
    ctx="$(printf '%s' "$json" | python3 -c 'import json,sys; print(json.load(sys.stdin).get("additional_context",""))' 2>/dev/null || true)"
    [[ -n "$ctx" ]] && notes+=("$ctx")
  fi
elif [[ -n "$LORE_CMD" ]]; then
  if json="$(lore_event after_shell --cwd "$LORE_CWD" --cmd "$LORE_CMD" 2>/dev/null)"; then
    ctx="$(printf '%s' "$json" | python3 -c 'import json,sys; print(json.load(sys.stdin).get("additional_context",""))' 2>/dev/null || true)"
    [[ -n "$ctx" ]] && notes+=("$ctx")
  fi
fi

stamp="/tmp/.lore-cursor-check"
now="$(date +%s)"
last=0
[[ -f "$stamp" ]] && last="$(cat "$stamp" 2>/dev/null || echo 0)"
if (( now - last >= 300 )); then
  echo "$now" > "$stamp" 2>/dev/null || true
  if json="$(lore_event health --cwd "$LORE_CWD" 2>/dev/null)"; then
    hctx="$(printf '%s' "$json" | python3 -c '
import json, sys
try:
    r = json.load(sys.stdin)
    w = r.get("warnings") or []
    if not w:
        raise SystemExit(0)
    text = "\n".join(w)
    if "not found" in text:
        raise SystemExit(0)
    print("[lore] health:\n" + text[:1200])
except SystemExit:
    raise
except Exception:
    pass
' 2>/dev/null || true)"
    [[ -n "$hctx" ]] && notes+=("$hctx")
  fi
fi

if (( ${#notes[@]} > 0 )); then
  export LORE_NOTES
  LORE_NOTES="$(printf '%s\0' "${notes[@]}")"
  python3 -c '
import json, os
parts = [p for p in os.environ.get("LORE_NOTES", "").split("\0") if p]
print(json.dumps({"additional_context": "\n\n".join(parts)}, ensure_ascii=False))
' 2>/dev/null || echo '{}'
else
  echo '{}'
fi
