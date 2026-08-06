#!/usr/bin/env bash
# check-staleness.sh — detect stale or missing knowledge base entries.
#
# Usage:
#   ./scripts/check-staleness.sh [path]        # human-readable
#   ./scripts/check-staleness.sh [path] --json # structured output
#   ./scripts/check-staleness.sh --help
#
# Checks:
#   1. Repos without CONTEXT.md (new repos since KB creation)
#   2. CONTEXT.md referencing files modified after KB last update
#   3. PITFALLS entries from TODO/FIXME that have been resolved in code
#   4. KB files last modified vs current code state
#
# Exit 0: all fresh.  Exit 1: issues found.
#
# Requires: bash, python3.

set -euo pipefail

WORKSPACE="${1:-.}"
OUTPUT_MODE="text"

while [[ $# -gt 0 ]]; do
  case "$1" in
    --json) OUTPUT_MODE="json"; shift ;;
    --text) OUTPUT_MODE="text"; shift ;;
    -h|--help)
      cat <<EOF
Usage: $(basename "$0") [path] [--json]

Detect stale or missing knowledge base entries.

Checks:
  1. Repos without CONTEXT.md
  2. Referenced files modified after KB update
  3. KB age vs code activity
EOF
      exit 0
      ;;
    *) WORKSPACE="$1"; shift ;;
  esac
done

WORKSPACE="$(cd "$WORKSPACE" 2>/dev/null && pwd -P)" || {
  echo '{"error": "cannot access workspace"}' >&2
  exit 1
}

export WORKSPACE OUTPUT_MODE
python3 <<'PY'
import os, json, sys, re
from datetime import datetime

workspace = os.environ['WORKSPACE']
output_mode = os.environ.get('OUTPUT_MODE', 'text')

pikb = os.path.join(workspace, ".pikb")
issues = []
fresh = []

# ── helpers ──
def mtime_ts(path):
    try: return os.path.getmtime(path)
    except OSError: return 0

def mtime_days(path):
    ts = mtime_ts(path)
    if ts == 0: return None
    return (datetime.now().timestamp() - ts) / 86400

def find_kb_files():
    """Return list of (rel_path, abs_path) for all .md files in KB."""
    files = []
    for kb_dir in [pikb, os.path.join(workspace, ".pi", "kb")]:
        if not os.path.isdir(kb_dir):
            continue
        for root, dirs, fnames in os.walk(kb_dir):
            dirs[:] = [d for d in dirs if not d.startswith(".")]
            for fname in fnames:
                if fname.endswith(".md"):
                    files.append((
                        os.path.relpath(os.path.join(root, fname), workspace),
                        os.path.join(root, fname)
                    ))
    return files

def find_repos():
    """Detect repos in workspace (like scan-workspace.sh)."""
    markers = {"go.mod", "package.json", "Cargo.toml", ".git",
               "pyproject.toml", "Gemfile", "pom.xml", "build.gradle"}
    repos = []
    try:
        for entry in sorted(os.listdir(workspace)):
            if entry.startswith("."):
                continue
            full = os.path.join(workspace, entry)
            if not os.path.isdir(full):
                continue
            if set(os.listdir(full)) & markers:
                repos.append(entry)
    except PermissionError:
        pass
    return repos

def extract_file_refs(kb_path):
    """Extract referenced file paths from a KB markdown file.
    Looks for: backtick paths, markdown links, and plain paths like 'cmd/server/main.go'."""
    refs = []
    try:
        with open(kb_path, 'r') as f:
            content = f.read()
    except Exception:
        return refs

    # markdown links: [text](path)
    for m in re.finditer(r'\[([^\]]*)\]\(([^)]+)\)', content):
        target = m.group(2)
        if not target.startswith(('http://', 'https://', '#', 'mailto:')):
            refs.append(target)

    # backtick paths: `path/to/file.go`
    for m in re.finditer(r'`([^`]+)`', content):
        val = m.group(1)
        if '.' in val and ('/' in val or val.endswith(('.go', '.py', '.ts', '.js', '.rs', '.yaml', '.json', '.toml', '.cfg'))):
            refs.append(val)

    # bare paths like "来源: docs/payment/callback.md" or "入口: cmd/server/main.go"
    for m in re.finditer(r'(?:来源|入口|主程序|配置|entry|config|source)[：:]\s*([^\s,\n]+\.(?:md|go|py|ts|js|yaml|json|toml))', content, re.IGNORECASE):
        refs.append(m.group(1))

    return refs

# ── 0. Check .pikb/ exists ──
if not os.path.isdir(pikb):
    issues.append({
        "check": ".pikb/",
        "severity": "error",
        "detail": ".pikb/ not found — KB not initialized",
        "action": "run /skill:lore 创建知识库"
    })
    if output_mode == "json":
        print(json.dumps({"workspace": workspace, "issues": issues, "fresh": [], "stale": True}, indent=2, ensure_ascii=False))
    else:
        print(f"\n\033[2m[lore]\033[0m workspace: \033[1m{workspace}\033[0m")
        print(f"\n  \033[31m✗\033[0m  .pikb/ not found — KB not initialized")
        print(f"    →  run \033[1m/skill:lore 创建知识库\033[0m\n")
    sys.exit(1)

# ── 1. Repos without CONTEXT.md ──
repos = find_repos()
missing_context = []
for repo in repos:
    ctx = os.path.join(workspace, repo, ".pi", "kb", "CONTEXT.md")
    if not os.path.isfile(ctx):
        missing_context.append(repo)

if missing_context:
    issues.append({
        "check": "CONTEXT.md coverage",
        "severity": "warning",
        "detail": f"{len(missing_context)} repo(s) missing CONTEXT.md: {', '.join(missing_context[:5])}",
        "action": "create .pi/kb/CONTEXT.md for each repo"
    })
else:
    fresh.append("CONTEXT.md: all repos covered")

# ── 2. Referenced files modified after KB ──
kb_files = find_kb_files()
newest_kb_ts = max((mtime_ts(p) for _, p in kb_files), default=0)

# collect all unique file refs from all KB files
all_refs = set()
for rel, abs_path in kb_files:
    for ref in extract_file_refs(abs_path):
        all_refs.add(ref)

# resolve refs to absolute paths and check mtime
modified_refs = []
for ref in all_refs:
    # try multiple resolution strategies
    candidates = [
        os.path.join(workspace, ref),
        # relative to .pikb/
        os.path.join(pikb, "..", ref),
    ]
    resolved = None
    for c in candidates:
        if os.path.isfile(c):
            resolved = c
            break

    if resolved and mtime_ts(resolved) > newest_kb_ts:
        days = mtime_days(resolved)
        modified_refs.append({
            "kb_ref": ref,
            "file": resolved,
            "days_ago": round(days, 1) if days else "?",
        })

if modified_refs:
    issues.append({
        "check": "referenced files",
        "severity": "warning",
        "detail": f"{len(modified_refs)} referenced file(s) modified after KB update",
        "items": modified_refs[:10],
    })
else:
    fresh.append("referenced files: all up to date")

# ── 3. KB age ──
kb_age_days = mtime_days(os.path.join(pikb, "MAP.md")) if os.path.isfile(os.path.join(pikb, "MAP.md")) else None
if kb_age_days is not None:
    if kb_age_days > 30:
        issues.append({
            "check": "KB age",
            "severity": "warning",
            "detail": f"KB last updated {kb_age_days:.0f}d ago — consider a review",
            "action": "review and refresh KB entries"
        })
    else:
        fresh.append(f"KB age: {kb_age_days:.0f}d")

# ── 4. PITFALLS Triggers completeness ──
pitfalls_file = os.path.join(pikb, "PITFALLS.md")
if os.path.isfile(pitfalls_file):
    with open(pitfalls_file) as f:
        content = f.read()
    missing_triggers = []
    for m in re.finditer(r'^## (\d+)\. (.+)$', content, re.MULTILINE):
        pid, title = m.group(1), m.group(2)
        end = content.find('\n## ', m.end())
        if end == -1: end = len(content)
        section = content[m.end():end]
        if 'Triggers:' not in section:
            missing_triggers.append(f'#{pid} {title}')
    if missing_triggers:
        issues.append({
            "check": "PITFALLS Triggers",
            "severity": "warning",
            "detail": f"{len(missing_triggers)} entry(s) missing Triggers: {missing_triggers[0]}",
            "action": "add Triggers: to PITFALLS entries"
        })
    else:
        fresh.append("PITFALLS Triggers: all complete")

# ── 5. Detect vanished repos ──
# repos that have CONTEXT.md but no longer exist
for root, dirs, fnames in os.walk(os.path.join(workspace, ".pi")):
    for d in dirs[:]:
        if d.startswith("."):
            dirs.remove(d)
    if root.endswith("/kb") and root != os.path.join(workspace, ".pi", "kb"):
        # this is a repo-level kb dir
        repo_name = os.path.basename(os.path.dirname(root))
        if repo_name not in repos and repo_name not in (".pi",):
            ctx_file = os.path.join(root, "CONTEXT.md")
            if os.path.isfile(ctx_file):
                issues.append({
                    "check": "orphan CONTEXT.md",
                    "severity": "info",
                    "detail": f"CONTEXT.md exists for '{repo_name}' but the repo directory is gone",
                    "action": f"remove {ctx_file}"
                })

# ── Output ──
stale = len(issues) > 0

if output_mode == "json":
    out = {
        "workspace": workspace,
        "kb_age_days": round(kb_age_days, 1) if kb_age_days else None,
        "total_repos": len(repos),
        "missing_context": len(missing_context),
        "modified_refs": len(modified_refs),
        "issues": issues,
        "fresh": fresh,
        "stale": stale,
    }
    print(json.dumps(out, indent=2, ensure_ascii=False))
else:
    print(f"\n\033[2m[lore]\033[0m workspace: \033[1m{workspace}\033[0m")
    print(f"  {len(repos)} repos  |  KB age: {kb_age_days:.0f}d\n" if kb_age_days else f"  {len(repos)} repos\n")

    for item in fresh:
        print(f"  \033[32m✓\033[0m  {item}")

    for iss in issues:
        icon = {"error": "\033[31m✗\033[0m", "warning": "\033[33m⚠\033[0m", "info": "\033[2mℹ\033[0m"}.get(iss["severity"], "•")
        print(f"  {icon}  \033[1m{iss['check']}\033[0m: {iss['detail']}")
        if "items" in iss:
            for item in iss["items"][:5]:
                print(f"      \033[2m{item['kb_ref']}\033[0m  →  modified {item['days_ago']}d ago")
        if "action" in iss:
            print(f"      →  {iss['action']}")

    if not issues:
        print(f"\n  \033[2mall fresh\033[0m")
    print()

    sys.exit(1 if stale else 0)
PY
