#!/usr/bin/env bash
# lore-log.sh — View lore session logs.
# Usage: lore-log.sh [--last] [--summary] [--since <iso-time>] [--all] [path]
set -euo pipefail

MODE="summary"
WORKSPACE="${PWD:-.}"
SINCE=""

while [[ $# -gt 0 ]]; do
  case "$1" in
    --last) MODE="last"; shift ;;
    --summary) MODE="summary"; shift ;;
    --all) MODE="all"; shift ;;
    --since) MODE="since"; SINCE="$2"; shift 2 ;;
    -h|--help)
      cat <<'EOF'
Usage: lore-log.sh [options] [workspace-path]

Options:
  --last       Show last session summary only
  --summary    Show recent session summaries (default)
  --all        Show all log entries for current session
  --since TS   Show entries since ISO timestamp
  --help       Show this help
EOF
      exit 0
      ;;
    *) WORKSPACE="$1"; shift ;;
  esac
done

WORKSPACE="$(cd "$WORKSPACE" 2>/dev/null && pwd -P)" || {
  echo "[lore] cannot access workspace: $WORKSPACE"
  exit 1
}

LOGFILE="$WORKSPACE/.pikb/.lore-session-log.jsonl"

if [[ ! -f "$LOGFILE" ]]; then
  echo "[lore] no session log found at $LOGFILE"
  exit 0
fi

export LOGFILE MODE SINCE
python3 <<'PY'
import json, os, sys
from collections import defaultdict

logfile = os.environ.get("LOGFILE", "")
mode = os.environ.get("MODE", "summary")
since = os.environ.get("SINCE", "")

if not os.path.isfile(logfile):
    print("[lore] no log file")
    sys.exit(0)

lines = []
with open(logfile) as f:
    for line in f:
        line = line.strip()
        if not line:
            continue
        try:
            lines.append(json.loads(line))
        except json.JSONDecodeError:
            continue

if not lines:
    print("[lore] log empty")
    sys.exit(0)

if mode == "all":
    for rec in lines:
        ts = rec.get("ts", "?")
        ev = rec.get("event", "?")
        extra = ""
        if ev in ("after_edit", "after_shell") and rec.get("matches"):
            titles = [m.get("title", "?") for m in rec["matches"]]
            extra = " — " + ", ".join(titles)
        elif ev == "auto_maintain":
            extra = " — " + rec.get("detail", "")
        elif ev == "draft":
            extra = " — " + rec.get("file", "")
        print(f"  {ts[:19]}  {ev}{extra}")

elif mode == "since" and since:
    for rec in lines:
        if rec.get("ts", "") >= since:
            print(json.dumps(rec, ensure_ascii=False))

else:
    # Group by session
    sessions = defaultdict(list)
    for rec in lines:
        sid = rec.get("session", "unknown")
        sessions[sid].append(rec)

    if mode == "last":
        sids = list(sessions.keys())
        if sids:
            sessions = {sids[-1]: sessions[sids[-1]]}

    for sid, recs in sessions.items():
        print(f"\n📚 session {sid}")
        counts = defaultdict(int)
        pitfall_titles = []
        for r in recs:
            ev = r.get("event", "")
            if ev in ("after_edit", "after_shell") and r.get("matches"):
                counts["pitfall_matches"] += len(r["matches"])
                for m in r["matches"]:
                    pitfall_titles.append(m.get("title", "?"))
            elif ev == "auto_maintain":
                counts["auto_writes"] += 1
            elif ev == "draft":
                counts["drafts"] += 1
            elif ev == "after_error":
                counts["errors"] += 1

        if counts:
            print(f"  PITFALLS matched: {counts.get('pitfall_matches', 0)}")
            if pitfall_titles:
                for t in pitfall_titles:
                    print(f"    - {t}")
            print(f"  auto-writes: {counts.get('auto_writes', 0)}")
            print(f"  drafts: {counts.get('drafts', 0)}")
            print(f"  errors: {counts.get('errors', 0)}")
        else:
            print("  (no activity)")

print()
PY
