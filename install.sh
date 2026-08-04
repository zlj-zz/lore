#!/usr/bin/env bash
# lore install — setup knowledge base loading for pi / Claude Code / Cursor
set -euo pipefail

LORE_DIR="${HOME}/.agents/skills/lore"

usage() {
  cat <<EOF
Usage: ./install.sh [--pi] [--claude] [--cursor] [--all]

Install lore loading rules for your agents.

  --pi       pi coding agent (AGENTS.md + Extension)
  --claude   Claude Code (AGENTS.md + PostToolUse hook)
  --cursor   Cursor CLI (.cursorrules)
  --all      All three (default)

EOF
}

DO_PI=0; DO_CLAUDE=0; DO_CURSOR=0; HAVE=0
while [[ $# -gt 0 ]]; do
  case "$1" in
    --pi) DO_PI=1; HAVE=1; shift ;;
    --claude) DO_CLAUDE=1; HAVE=1; shift ;;
    --cursor) DO_CURSOR=1; HAVE=1; shift ;;
    --all) DO_PI=1; DO_CLAUDE=1; DO_CURSOR=1; HAVE=1; shift ;;
    -h|--help) usage; exit 0 ;;
    *) echo "Unknown: $1"; usage; exit 1 ;;
  esac
done
[[ $HAVE -eq 0 ]] && DO_PI=1 && DO_CLAUDE=1 && DO_CURSOR=1

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

# ─── Step 1: Install skill itself ──────────────────────────────────────

mkdir -p "$(dirname "$LORE_DIR")"
if [[ ! -d "$LORE_DIR" ]]; then
  ln -sfn "$ROOT" "$LORE_DIR"
  echo "linked $LORE_DIR → $ROOT"
else
  echo "lore already installed at $LORE_DIR"
fi

# ─── Helper: append AGENTS.md rules ─────────────────────────────────────

LORE_RULES='
## Knowledge Base (lore)

On session start:
1. Read `.pi/kb/CONTEXT.md`
2. If it references @workspace, read `../.pikb/MAP.md` (first 80 lines)

During work:
- Writing code → check `.pikb/CONVENTIONS.md`
- Multi-module changes → check `.pikb/MAP.md`
- Error encountered → check `.pikb/PITFALLS.md`
- New repo discovered → create `.pi/kb/CONTEXT.md`
- Significant change → ask: "knowledge base 需要更新吗?"

If `.pikb/` doesn'\''t exist and project is complex:
  → `/skill:lore 创建知识库` or ask agent to run lore
'

append_agents_rules() {
  local target="$1"
  if [[ ! -f "$target" ]]; then
    echo "$LORE_RULES" > "$target"
    echo "created $target"
  elif grep -q "Knowledge Base (lore)" "$target"; then
    echo "lore rules already in $target"
  else
    echo "$LORE_RULES" >> "$target"
    echo "appended lore rules to $target"
  fi
}

# ─── pi ─────────────────────────────────────────────────────────────────

if [[ $DO_PI -eq 1 ]]; then
  echo ""
  echo "=== pi ==="

  # AGENTS.md (~/.pi/agent/AGENTS.md and project-level)
  append_agents_rules "${HOME}/.pi/agent/AGENTS.md"

  # Extension: symlink if exists
  EXT_SRC="$ROOT/lore-extension"
  EXT_DST="${HOME}/.pi/agent/extensions/lore"
  if [[ -d "$EXT_SRC" ]]; then
    mkdir -p "$(dirname "$EXT_DST")"
    if [[ ! -e "$EXT_DST" ]]; then
      ln -sfn "$EXT_SRC" "$EXT_DST"
      echo "linked pi extension: $EXT_DST → $EXT_SRC"
    else
      echo "pi extension already at $EXT_DST"
    fi
  else
    echo "(pi extension not yet built — AGENTS.md rules will work for now)"
  fi

  echo "  → /reload in pi to apply"
fi

# ─── Claude Code ────────────────────────────────────────────────────────

if [[ $DO_CLAUDE -eq 1 ]]; then
  echo ""
  echo "=== Claude Code ==="

  # AGENTS.md
  append_agents_rules "${HOME}/.claude/AGENTS.md"

  # PostToolUse hook
  HOOKS_FILE="${HOME}/.claude/settings.json"
  LORE_HOOK=$(cat <<'HOOK'
{
  "hooks": {
    "PostToolUse": [
      {
        "matcher": "",
        "hooks": [
          {
            "type": "command",
            "command": "if [ ! -f /tmp/.lore-loaded ] && [ -f .pi/kb/CONTEXT.md ]; then echo '[lore] KB available — read .pi/kb/CONTEXT.md'; touch /tmp/.lore-loaded; fi"
          }
        ]
      }
    ]
  }
}
HOOK
)

  if [[ -f "$HOOKS_FILE" ]]; then
    python3 -c "
import json, sys
with open('$HOOKS_FILE') as f:
    cfg = json.load(f)
hooks = cfg.setdefault('hooks', {})
ptu = hooks.setdefault('PostToolUse', [])
# Check if lore hook already exists
for h in ptu:
    for inner in h.get('hooks', []):
        if 'lore-loaded' in inner.get('command', ''):
            print('lore hook already in settings.json')
            sys.exit(0)
# Add lore hook
ptu.append({'matcher': '', 'hooks': [{'type': 'command', 'command': \"if [ ! -f /tmp/.lore-loaded ] && [ -f .pi/kb/CONTEXT.md ]; then echo '[lore] KB available — read .pi/kb/CONTEXT.md'; touch /tmp/.lore-loaded; fi\"}]})
with open('$HOOKS_FILE', 'w') as f:
    json.dump(cfg, f, indent=2)
    f.write('\n')
print('added lore hook to settings.json')
" 2>/dev/null || echo "(skipped hook — python3 not available or settings.json format unknown)"
  fi
  echo "  → restart Claude Code session"
fi

# ─── Cursor ─────────────────────────────────────────────────────────────

if [[ $DO_CURSOR -eq 1 ]]; then
  echo ""
  echo "=== Cursor CLI ==="

  # .cursorrules
  append_agents_rules "${HOME}/.cursorrules"
  echo "  → restart Cursor CLI session"
fi

# ─── Done ───────────────────────────────────────────────────────────────

echo ""
echo "Done."
echo ""
echo "Initialize a knowledge base in your project:"
echo "  /skill:lore 创建知识库"
echo ""
echo "Or manually:"
echo "  mkdir -p .pikb/"
echo "  cp ~/.agents/skills/lore/templates/{MAP,CONVENTIONS,PITFALLS}.md .pikb/"
