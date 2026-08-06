#!/usr/bin/env bash
# Resolve lore skill root and run lore-event.
lore_root() {
  local cands=(
    "${LORE_ROOT:-}"
    "${HOME}/.agents/skills/lore"
    "$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd -P)"
  )
  local c
  for c in "${cands[@]}"; do
    [[ -n "$c" && -x "$c/bin/lore-event" ]] && { echo "$c"; return 0; }
    [[ -n "$c" && -f "$c/runtime/lore_runtime/cli.py" ]] && { echo "$c"; return 0; }
  done
  return 1
}

lore_event() {
  local root
  root="$(lore_root)" || return 1
  if [[ -x "$root/bin/lore-event" ]]; then
    "$root/bin/lore-event" "$@"
  else
    PYTHONPATH="$root/runtime" python3 -m lore_runtime "$@"
  fi
}
