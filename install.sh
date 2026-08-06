#!/usr/bin/env bash
# install.sh — install / uninstall lore knowledge-base loading rules.
#
# Usage:
#   ./install.sh install                           # all agents (default)
#   ./install.sh install --to pi,claude            # specific agents
#   ./install.sh uninstall                         # remove all
#   ./install.sh uninstall --to claude --dry-run   # preview
#   ./install.sh status                            # show what's installed
#
# Exit codes: 0=ok  1=conflict  2=usage
#
# Requires: bash, python3. macOS bash 3.2 compatible.

set -euo pipefail

ROOT="$(cd "$(dirname "$0")" && pwd -P)"
SKILL_NAME="lore"
SKILL_DIR="${HOME}/.agents/skills/$SKILL_NAME"

EXIT_OK=0
EXIT_CONFLICT=1
EXIT_USAGE=2

# --- agent definitions ---
# "id|label|agents_md_path|extra_type"
# extra_type: extension, hook, cursorrules, or none
AGENT_DEFS=(
  "pi|pi coding agent|~/.pi/agent/AGENTS.md|extension"
  "claude|Claude Code|~/.claude/AGENTS.md|hook"
  "cursor|Cursor CLI||cursorrules"
)

# --- lore rules block (with sentinel markers for clean uninstall) ---
LORE_RULES='
<!-- LORE-START -->
## Knowledge Base (lore)

On session start:
1. If `~/.agents/skills/lore/scripts/on-session-start.sh` exists, run it and note any warnings
2. Read `.pi/kb/CONTEXT.md`
3. If it references @workspace, read `../.pikb/MAP.md` (first 80 lines)

During work:
- Writing code → check `.pikb/CONVENTIONS.md`
- Multi-module changes → check `.pikb/MAP.md`
- Error encountered → check `.pikb/PITFALLS.md`
- New repo discovered → create `.pi/kb/CONTEXT.md`
- Significant change → ask: "knowledge base 需要更新吗?"

**Search KB:** Run `~/.agents/skills/lore/scripts/quick-ref.sh <keyword>` to find relevant context.

If `.pikb/` doesn'\''t exist and project looks complex (multi-repo / >5 rounds):
  → `/skill:lore 创建知识库` or ask agent to run lore
<!-- LORE-END -->
'

# --- colors ---
_use_color() {
  [[ -t 1 ]] || return 1
  [[ -z "${NO_COLOR:-}" ]] || return 1
  return 0
}

if _use_color; then
  C_RESET=$'\033[0m'
  C_BOLD=$'\033[1m'
  C_DIM=$'\033[2m'
  C_RED=$'\033[31m'
  C_GREEN=$'\033[32m'
  C_YELLOW=$'\033[33m'
  C_CYAN=$'\033[36m'
else
  C_RESET= C_BOLD= C_DIM= C_RED= C_GREEN= C_YELLOW= C_CYAN=
fi

die_usage() { printf '%s\n' "${C_RED}error:${C_RESET} $*" >&2; printf '\n' >&2; usage >&2; exit "$EXIT_USAGE"; }
die()       { printf '%s\n' "${C_RED}error:${C_RESET} $*" >&2; exit "$EXIT_CONFLICT"; }
info()      { printf '%s\n' "${C_DIM}$*${C_RESET}"; }
ok()        { printf '%s\n' "${C_GREEN}$*${C_RESET}"; }
warn()      { printf '%s\n' "${C_YELLOW}$*${C_RESET}" >&2; }

# --- helpers ---
expand_path() {
  local p="$1"
  [[ "$p" == "~" ]] && { printf '%s' "$HOME"; return; }
  [[ "$p" == "~/"* ]] && { printf '%s' "$HOME/${p:2}"; return; }
  printf '%s' "$p"
}

realpath_py() { python3 -c 'import os,sys; print(os.path.realpath(sys.argv[1]))' "$1"; }

parse_csv() {
  local raw="$1" IFS=','
  set -- $raw
  local x
  for x in "$@"; do
    x="$(printf '%s' "$x" | sed 's/^[[:space:]]*//;s/[[:space:]]*$//')"
    [[ -n "$x" ]] && printf '%s\n' "$x"
  done
}

resolve_agent() {
  local id="$1"
  for def in "${AGENT_DEFS[@]}"; do
    local tid="${def%%|*}"; local rest="${def#*|}"
    local label="${rest%%|*}"; rest="${rest#*|}"
    local agents_md="${rest%%|*}"; local extra="${rest##*|}"
    if [[ "$tid" == "$id" ]]; then
      printf '%s\t%s\t%s' "$label" "$(expand_path "$agents_md")" "$extra"
      return 0
    fi
  done
  return 1
}

_icon() {
  case "$1" in
    linked|installed|unlinked) printf '%s✓%s' "$C_GREEN" "$C_RESET" ;;
    skip)                      printf '%s·%s' "$C_DIM" "$C_RESET" ;;
    conflict)                  printf '%s✗%s' "$C_RED" "$C_RESET" ;;
    *)                         printf '  ?' ;;
  esac
}

_single_line() {
  local icon="$1" item="$2" detail="${3:-}"
  printf '  %s  %-22s %s\n' "$icon" "$item" "$detail"
}

# ============================================================
# Operations
# ============================================================

# --- AGENTS.md content management ---
_agents_has_lore() {
  [[ -f "$1" ]] && grep -q "<!-- LORE-START -->" "$1"
}

_agents_append() {
  local target="$1"
  mkdir -p "$(dirname "$target")"
  if [[ ! -f "$target" ]]; then
    printf '%s\n' "$LORE_RULES" > "$target"
    return 0  # created
  elif _agents_has_lore "$target"; then
    # Remove old non-sentinel lore block if present (migration from v1)
    if grep -q '^## Knowledge Base (lore)' "$target" 2>/dev/null; then
      python3 -c "
import re
with open('$target') as f:
    c = f.read()
old = re.search(r'^## Knowledge Base \(lore\).*?(?=<!-- LORE-START -->)', c, re.DOTALL | re.MULTILINE)
if old:
    c = c[:old.start()] + c[old.end():]
    with open('$target', 'w') as f:
        f.write(c.lstrip('\n') + '\n')
" 2>/dev/null || true
    fi
    return 1  # already there (sentinel-wrapped)
  else
    printf '\n%s\n' "$LORE_RULES" >> "$target"
    return 0  # appended
  fi
}

_agents_remove() {
  local target="$1"
  if [[ "$DRY_RUN" -eq 1 ]]; then return 0; fi
  [[ -f "$target" ]] || return 1
  if [[ "$(uname)" == "Darwin" ]]; then
    sed -i '' '/<!-- LORE-START -->/,/<!-- LORE-END -->/d' "$target"
  else
    sed -i '/<!-- LORE-START -->/,/<!-- LORE-END -->/d' "$target"
  fi
  # remove trailing blank lines
  if [[ "$(uname)" == "Darwin" ]]; then
    sed -i '' -e :a -e '/^\n*$/{$d;N;ba' -e '}' "$target" 2>/dev/null || true
  fi
  return 0
}

# --- settings.json hook management ---
HOOKS_FILE="${HOME}/.claude/settings.json"

_hook_has_lore() {
  [[ -f "$HOOKS_FILE" ]] || return 1
  python3 -c "
import json
with open('$HOOKS_FILE') as f:
    cfg = json.load(f)
for h in cfg.get('hooks', {}).get('PostToolUse', []):
    for inner in h.get('hooks', []):
        cmd = inner.get('command', '')
        if 'lore-loaded' in cmd or 'lore-check' in cmd:
            exit(0)
exit(1)
" 2>/dev/null
}

LORETHROTTLE=300  # seconds between checks

_hook_add() {
  [[ -f "$HOOKS_FILE" ]] || return 1
  python3 -c "
import json
with open('$HOOKS_FILE') as f:
    cfg = json.load(f)
hooks = cfg.setdefault('hooks', {})
ptu = hooks.setdefault('PostToolUse', [])
# remove any old lore hooks (both v1 one-shot and v2 periodic patterns)
new_ptu = []
for h in ptu:
    new_inner = []
    for inner in h.get('hooks', []):
        cmd = inner.get('command', '')
        if 'lore-loaded' not in cmd and 'lore-check' not in cmd:
            new_inner.append(inner)
    if new_inner:
        h['hooks'] = new_inner
        new_ptu.append(h)
    elif h.get('matcher', '') != '':
        new_ptu.append(h)
ptu = new_ptu
hooks['PostToolUse'] = ptu
# add new periodic-check hook
ptu.append({'matcher': '', 'hooks': [{'type': 'command', 'command': '[ -f \"$HOME/.agents/skills/lore/scripts/on-session-start.sh\" ] || return 0; STAMP=/tmp/.lore-check; NOW=$(date +%s); LAST=$(cat $STAMP 2>/dev/null || echo 0); [ $((NOW - LAST)) -lt 300 ] && return 0; echo $NOW > $STAMP; output=$(bash \"$HOME/.agents/skills/lore/scripts/on-session-start.sh\" 2>&1) || { echo \"$output\" | grep -q \"not found\" && return 0; echo \"[lore] $output\"; }'}]})
with open('$HOOKS_FILE', 'w') as f:
    json.dump(cfg, f, indent=2)
    f.write('\n')
print('added lore periodic-check hook (every 300s)')
" 2>/dev/null
}

_hook_remove() {
  [[ "$DRY_RUN" -eq 1 ]] && return 0
  [[ -f "$HOOKS_FILE" ]] || return 1
  python3 -c "
import json
with open('$HOOKS_FILE') as f:
    cfg = json.load(f)
hooks = cfg.get('hooks', {})
ptu = hooks.get('PostToolUse', [])
new_ptu = []
for h in ptu:
    new_inner = []
    for inner in h.get('hooks', []):
        if 'lore-loaded' not in inner.get('command', ''):
            new_inner.append(inner)
    if new_inner:
        h['hooks'] = new_inner
        new_ptu.append(h)
    elif h.get('matcher', '') != '':
        new_ptu.append(h)
if new_ptu:
    hooks['PostToolUse'] = new_ptu
else:
    hooks.pop('PostToolUse', None)
if not hooks:
    cfg.pop('hooks', None)
with open('$HOOKS_FILE', 'w') as f:
    json.dump(cfg, f, indent=2)
    f.write('\n')
" 2>/dev/null
}

# --- .cursorrules ---
CURSORRULES="${HOME}/.cursorrules"

_cursorrules_has_lore() {
  [[ -f "$CURSORRULES" ]] && grep -q "<!-- LORE-START -->" "$CURSORRULES"
}

# ============================================================
# Install
# ============================================================

do_install() {
  local tid="$1"
  local info agent_label agents_md extra
  info="$(resolve_agent "$tid")"
  agent_label="${info%%$'\t'*}"; info="${info#*$'\t'}"
  agents_md="${info%%$'\t'*}"; extra="${info##*$'\t'}"

  printf '\n%s● install lore  →  %s%s%s\n\n' "$C_CYAN" "$C_DIM" "$agent_label" "$C_RESET"

  # 1. Skill symlink
  mkdir -p "$(dirname "$SKILL_DIR")"
  if [[ -L "$SKILL_DIR" ]]; then
    local target
    target="$(realpath_py "$SKILL_DIR")"
    if [[ "$target" == "$(realpath_py "$ROOT")" ]]; then
      _single_line "$(_icon skip)" "skill symlink" "${C_DIM}already linked${C_RESET}"
    else
      _single_line "$(_icon conflict)" "skill symlink" "${C_YELLOW}points to $target${C_RESET}"
    fi
  elif [[ -e "$SKILL_DIR" ]]; then
    _single_line "$(_icon conflict)" "skill symlink" "${C_YELLOW}real path exists${C_RESET}"
  else
    ln -s "$ROOT" "$SKILL_DIR"
    _single_line "$(_icon linked)" "skill symlink" "${C_DIM}$SKILL_DIR → $ROOT${C_RESET}"
  fi

  # 2. AGENTS.md rules (for agents that have them)
  if [[ -n "$agents_md" ]]; then
    if _agents_append "$agents_md"; then
      _single_line "$(_icon linked)" "AGENTS.md rules" "${C_DIM}$agents_md${C_RESET}"
    else
      _single_line "$(_icon skip)" "AGENTS.md rules" "${C_DIM}already present${C_RESET}"
    fi
  fi

  # 3. Agent-specific extras
  case "$extra" in
    extension)
      local ext_src="$ROOT/lore-extension"
      local ext_dst="${HOME}/.pi/agent/extensions/lore"
      if [[ -d "$ext_src" ]]; then
        mkdir -p "$(dirname "$ext_dst")"
        if [[ ! -e "$ext_dst" ]]; then
          ln -sfn "$ext_src" "$ext_dst"
          _single_line "$(_icon linked)" "pi extension" "${C_DIM}$ext_dst${C_RESET}"
        else
          _single_line "$(_icon skip)" "pi extension" "${C_DIM}already installed${C_RESET}"
        fi
      else
        _single_line "$(_icon skip)" "pi extension" "${C_DIM}not built yet${C_RESET}"
      fi
      ;;
    hook)
      if [[ -f "$HOOKS_FILE" ]]; then
        if _hook_has_lore; then
          _single_line "$(_icon skip)" "PostToolUse hook" "${C_DIM}already in settings.json${C_RESET}"
        else
          _hook_add && _single_line "$(_icon linked)" "PostToolUse hook" "${C_DIM}added to settings.json${C_RESET}" \
            || _single_line "$(_icon skip)" "PostToolUse hook" "${C_DIM}skipped (format unknown)${C_RESET}"
        fi
      else
        _single_line "$(_icon skip)" "PostToolUse hook" "${C_DIM}no settings.json${C_RESET}"
      fi
      ;;
    cursorrules)
      if _cursorrules_has_lore; then
        _single_line "$(_icon skip)" ".cursorrules" "${C_DIM}already present${C_RESET}"
      else
        printf '%s\n' "$LORE_RULES" >> "$CURSORRULES"
        _single_line "$(_icon linked)" ".cursorrules" "${C_DIM}appended${C_RESET}"
      fi
      ;;
  esac
  echo
}

# ============================================================
# Uninstall
# ============================================================

do_uninstall() {
  local tid="$1"
  local info agent_label agents_md extra
  info="$(resolve_agent "$tid")"
  agent_label="${info%%$'\t'*}"; info="${info#*$'\t'}"
  agents_md="${info%%$'\t'*}"; extra="${info##*$'\t'}"

  local label="uninstall"
  [[ "$DRY_RUN" -eq 1 ]] && label="uninstall (dry-run)"
  printf '\n%s● %s lore  →  %s%s%s\n\n' "$C_CYAN" "$label" "$C_DIM" "$agent_label" "$C_RESET"

  # 1. Skill symlink
  if [[ -L "$SKILL_DIR" ]]; then
    local target
    target="$(realpath_py "$SKILL_DIR")"
    if [[ "$target" == "$(realpath_py "$ROOT")" ]]; then
      [[ "$DRY_RUN" -eq 1 ]] || rm "$SKILL_DIR"
      _single_line "$(_icon unlinked)" "skill symlink" "${C_DIM}removed${C_RESET}"
    else
      _single_line "$(_icon skip)" "skill symlink" "${C_DIM}not our link ($target)${C_RESET}"
    fi
  elif [[ -e "$SKILL_DIR" ]]; then
    _single_line "$(_icon skip)" "skill symlink" "${C_DIM}real path, not removing${C_RESET}"
  else
    _single_line "$(_icon skip)" "skill symlink" "${C_DIM}not installed${C_RESET}"
  fi

  # 2. AGENTS.md rules
  if [[ -n "$agents_md" ]]; then
    if _agents_has_lore "$agents_md"; then
      _agents_remove "$agents_md"
      _single_line "$(_icon unlinked)" "AGENTS.md rules" "${C_DIM}removed from $agents_md${C_RESET}"
    else
      _single_line "$(_icon skip)" "AGENTS.md rules" "${C_DIM}not present${C_RESET}"
    fi
  fi

  # 3. Agent-specific extras
  case "$extra" in
    extension)
      local ext_dst="${HOME}/.pi/agent/extensions/lore"
      if [[ -L "$ext_dst" ]]; then
        [[ "$DRY_RUN" -eq 1 ]] || rm "$ext_dst"
        _single_line "$(_icon unlinked)" "pi extension" "${C_DIM}removed${C_RESET}"
      elif [[ -e "$ext_dst" ]]; then
        _single_line "$(_icon skip)" "pi extension" "${C_DIM}real path, not removing${C_RESET}"
      else
        _single_line "$(_icon skip)" "pi extension" "${C_DIM}not installed${C_RESET}"
      fi
      ;;
    hook)
      if _hook_has_lore; then
        _hook_remove
        _single_line "$(_icon unlinked)" "PostToolUse hook" "${C_DIM}removed from settings.json${C_RESET}"
      else
        _single_line "$(_icon skip)" "PostToolUse hook" "${C_DIM}not present${C_RESET}"
      fi
      ;;
    cursorrules)
      if _cursorrules_has_lore; then
        _agents_remove "$CURSORRULES"
        _single_line "$(_icon unlinked)" ".cursorrules" "${C_DIM}removed${C_RESET}"
      else
        _single_line "$(_icon skip)" ".cursorrules" "${C_DIM}not present${C_RESET}"
      fi
      ;;
  esac
  echo
}

# ============================================================
# Status
# ============================================================

do_status() {
  local tid="$1"
  local info agent_label agents_md extra
  info="$(resolve_agent "$tid")"
  agent_label="${info%%$'\t'*}"; info="${info#*$'\t'}"
  agents_md="${info%%$'\t'*}"; extra="${info##*$'\t'}"

  printf '\n%s● lore status  →  %s%s%s\n\n' "$C_CYAN" "$C_DIM" "$agent_label" "$C_RESET"

  # 1. Skill symlink
  if [[ -L "$SKILL_DIR" ]]; then
    local target
    target="$(realpath_py "$SKILL_DIR")"
    if [[ "$target" == "$(realpath_py "$ROOT")" ]]; then
      _single_line "$(_icon linked)" "skill symlink" "${C_DIM}linked${C_RESET}"
    else
      _single_line "$(_icon conflict)" "skill symlink" "${C_YELLOW}points to $target${C_RESET}"
    fi
  elif [[ -e "$SKILL_DIR" ]]; then
    _single_line "$(_icon conflict)" "skill symlink" "${C_YELLOW}real path (not symlink)${C_RESET}"
  else
    _single_line "$(_icon skip)" "skill symlink" "${C_DIM}not installed${C_RESET}"
  fi

  # 2. AGENTS.md rules
  if [[ -n "$agents_md" ]]; then
    if _agents_has_lore "$agents_md"; then
      _single_line "$(_icon linked)" "AGENTS.md rules" "${C_DIM}$agents_md${C_RESET}"
    else
      _single_line "$(_icon skip)" "AGENTS.md rules" "${C_DIM}not present${C_RESET}"
    fi
  fi

  # 3. Extras
  case "$extra" in
    extension)
      local ext_dst="${HOME}/.pi/agent/extensions/lore"
      if [[ -L "$ext_dst" ]]; then
        _single_line "$(_icon linked)" "pi extension" "${C_DIM}installed${C_RESET}"
      elif [[ -e "$ext_dst" ]]; then
        _single_line "$(_icon conflict)" "pi extension" "${C_YELLOW}real path${C_RESET}"
      else
        _single_line "$(_icon skip)" "pi extension" "${C_DIM}not installed${C_RESET}"
      fi
      ;;
    hook)
      if _hook_has_lore; then
        _single_line "$(_icon linked)" "PostToolUse hook" "${C_DIM}installed${C_RESET}"
      else
        _single_line "$(_icon skip)" "PostToolUse hook" "${C_DIM}not in settings.json${C_RESET}"
      fi
      ;;
    cursorrules)
      if _cursorrules_has_lore; then
        _single_line "$(_icon linked)" ".cursorrules" "${C_DIM}present${C_RESET}"
      else
        _single_line "$(_icon skip)" ".cursorrules" "${C_DIM}not present${C_RESET}"
      fi
      ;;
  esac
  echo
}

# ============================================================
# CLI
# ============================================================

usage() {
  cat <<EOF
${C_BOLD}Usage:${C_RESET}
  $(basename "$0") install   [--to <ids> | --all] [--force]
  $(basename "$0") uninstall [--to <ids> | --all] [--yes] [--dry-run]
  $(basename "$0") status    [--to <ids> | --all]
  $(basename "$0") --help

${C_BOLD}Targets:${C_RESET}
  pi, claude, cursor
  Default: all

${C_BOLD}Flags:${C_RESET}
  --force     overwrite conflicting symlinks (install only)
  --yes       auto-confirm (uninstall only, currently always non-interactive)
  --dry-run   preview uninstall without making changes

${C_BOLD}What gets installed per agent:${C_RESET}
  pi       AGENTS.md rules + pi extension symlink + skill symlink
  claude   AGENTS.md rules + PostToolUse hook in settings.json + skill symlink
  cursor   .cursorrules + skill symlink

${C_BOLD}Examples:${C_RESET}
  ./install.sh install
  ./install.sh install --to pi,claude
  ./install.sh uninstall --dry-run
  ./install.sh status --to claude
EOF
}

CMD=""
TO_SPEC=""
USE_ALL=0
FORCE=0
AUTO_YES=0
DRY_RUN=0
TARGET_IDS=()

ALL_TARGET_IDS=()
for def in "${AGENT_DEFS[@]}"; do ALL_TARGET_IDS+=("${def%%|*}"); done

parse_args() {
  if [[ $# -eq 0 ]]; then
    die_usage "missing command (install | uninstall | status)"
  fi

  case "$1" in
    -h|--help|help) usage; exit "$EXIT_OK" ;;
    install|uninstall|status) CMD="$1"; shift ;;
    *) die_usage "unknown command: $1" ;;
  esac

  while [[ $# -gt 0 ]]; do
    case "$1" in
      --to)       [[ $# -ge 2 ]] || die_usage "--to needs a value"; TO_SPEC="$2"; shift 2 ;;
      --to=*)     TO_SPEC="${1#--to=}"; shift ;;
      --all)      USE_ALL=1; shift ;;
      --force)    FORCE=1; shift ;;
      --yes)      AUTO_YES=1; shift ;;
      --dry-run)  DRY_RUN=1; shift ;;
      -h|--help)  usage; exit "$EXIT_OK" ;;
      *)          die_usage "unknown option: $1" ;;
    esac
  done

  if [[ "$USE_ALL" -eq 1 && -n "$TO_SPEC" ]]; then
    die_usage "use either --to or --all, not both"
  fi
  if [[ "$FORCE" -eq 1 && "$CMD" != "install" ]]; then
    die_usage "--force only applies to install"
  fi
  if [[ "$AUTO_YES" -eq 1 || "$DRY_RUN" -eq 1 ]]; then
    [[ "$CMD" == "uninstall" ]] || die_usage "--yes/--dry-run only apply to uninstall"
  fi

  # Default: all
  if [[ "$USE_ALL" -eq 0 && -z "$TO_SPEC" ]]; then
    USE_ALL=1
  fi

  TARGET_IDS=()
  if [[ "$USE_ALL" -eq 1 ]]; then
    TARGET_IDS=("${ALL_TARGET_IDS[@]}")
  else
    while IFS= read -r id; do
      TARGET_IDS+=("$id")
    done < <(parse_csv "$TO_SPEC")
  fi

  for tid in "${TARGET_IDS[@]}"; do
    if ! resolve_agent "$tid" >/dev/null 2>&1; then
      die_usage "unknown target '$tid' (valid: ${ALL_TARGET_IDS[*]})"
    fi
  done

  # Require python3
  command -v python3 >/dev/null 2>&1 || die "python3 is required"
}

main() {
  parse_args "$@"

  for tid in "${TARGET_IDS[@]}"; do
    case "$CMD" in
      install)   do_install "$tid" ;;
      uninstall) do_uninstall "$tid" ;;
      status)    do_status "$tid" ;;
    esac
  done

  if [[ "$CMD" == "install" ]]; then
    echo "Done. Initialize a knowledge base in your project:"
    echo "  /skill:lore 创建知识库"
    echo "  (or manually: mkdir -p .pikb/ && cp ~/.agents/skills/lore/templates/*.md .pikb/)"
    echo
  elif [[ "$CMD" == "uninstall" && "$DRY_RUN" -eq 1 ]]; then
    echo "${C_DIM}Dry-run complete. Run without --dry-run to actually uninstall.${C_RESET}"
    echo
  fi
}

main "$@"
