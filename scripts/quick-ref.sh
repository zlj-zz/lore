#!/usr/bin/env bash
# quick-ref.sh — keyword search across knowledge base files.
#
# Usage:
#   ./scripts/quick-ref.sh <keyword>              # search workspace
#   ./scripts/quick-ref.sh <keyword> --json       # structured output
#   ./scripts/quick-ref.sh <keyword> --files x,y   # limit to specific KB files
#   ./scripts/quick-ref.sh --help
#
# Searches .pikb/ and .pi/kb/ for matching sections.
# Returns matching sections with context, source file, and line numbers.
#
# Requires: bash, python3.

set -euo pipefail

WORKSPACE="."
OUTPUT_MODE="text"
LIMIT_FILES=""
KEYWORD=""

usage() {
  cat <<EOF
Usage: $(basename "$0") <keyword> [--json] [--files <names>]

Search knowledge base files for a keyword.

  <keyword>   text to search for (required)
  --json      structured output for agent consumption
  --files x,y  limit to specific KB files (e.g., "MAP.md,PITFALLS.md")
  --help

Examples:
  ./scripts/quick-ref.sh "payment callback"
  ./scripts/quick-ref.sh "auth" --json
  ./scripts/quick-ref.sh "redis" --files MAP.md,PITFALLS.md
EOF
}

# parse args
while [[ $# -gt 0 ]]; do
  case "$1" in
    --json)    OUTPUT_MODE="json"; shift ;;
    --files)   LIMIT_FILES="$2"; shift 2 ;;
    --files=*) LIMIT_FILES="${1#--files=}"; shift ;;
    -h|--help) usage; exit 0 ;;
    --*)       echo "unknown flag: $1" >&2; usage; exit 2 ;;
    *)         KEYWORD="$1"; shift ;;
  esac
done

if [[ -z "$KEYWORD" ]]; then
  usage
  exit 2
fi

WORKSPACE="$(cd "$WORKSPACE" 2>/dev/null && pwd -P)"

export WORKSPACE KEYWORD OUTPUT_MODE LIMIT_FILES
python3 <<'PY'
import os, re, json, sys

workspace = os.environ['WORKSPACE']
keyword = os.environ['KEYWORD']
output_mode = os.environ.get('OUTPUT_MODE', 'text')
limit_files = os.environ.get('LIMIT_FILES', '')

# collect KB files
kb_dirs = []
pikb = os.path.join(workspace, ".pikb")
pikb_local = os.path.join(workspace, ".pi", "kb")
if os.path.isdir(pikb):
    kb_dirs.append((".pikb", pikb))
if os.path.isdir(pikb_local):
    kb_dirs.append((".pi/kb", pikb_local))

if not kb_dirs:
    if output_mode == "json":
        print(json.dumps({"results": [], "total": 0, "error": "no KB found"}))
    else:
        print("\033[2m[lore] no knowledge base found in this workspace\033[0m")
    sys.exit(0)

# resolve file filter
allowed = set()
if limit_files:
    allowed = set(f.strip() for f in limit_files.split(",") if f.strip())

# search
results = []
kw_lower = keyword.lower()
# split into terms for multi-word search (AND logic)
terms = [t.strip() for t in kw_lower.split() if t.strip()]

for label, kb_dir in kb_dirs:
    for root, dirs, files in os.walk(kb_dir):
        # skip .git
        dirs[:] = [d for d in dirs if not d.startswith(".")]
        for fname in sorted(files):
            if not fname.endswith(".md"):
                continue

            rel_path = os.path.relpath(os.path.join(root, fname), workspace)

            if allowed and fname not in allowed and rel_path not in allowed:
                continue

            try:
                with open(os.path.join(root, fname), 'r', encoding='utf-8') as f:
                    lines = f.readlines()
            except Exception:
                continue

            # find matching sections (heading + content block)
            current_heading = fname
            in_section = False
            section_lines = []
            section_start = 0

            for i, line in enumerate(lines):
                # detect heading
                if line.startswith("## "):
                    # flush previous section if matching
                    if in_section:
                        section_text = "".join(section_lines)
                        if all(t in section_text.lower() for t in terms):
                            results.append({
                                "file": rel_path,
                                "heading": current_heading.strip(),
                                "line": section_start + 1,
                                "snippet": section_text.strip()[:500],
                            })
                    # start new section
                    current_heading = line.strip()
                    section_lines = [line]
                    section_start = i
                    in_section = True
                elif line.startswith("# "):
                    if in_section:
                        section_text = "".join(section_lines)
                        if all(t in section_text.lower() for t in terms):
                            results.append({
                                "file": rel_path,
                                "heading": current_heading.strip(),
                                "line": section_start + 1,
                                "snippet": section_text.strip()[:500],
                            })
                    current_heading = line.strip()
                    section_lines = [line]
                    section_start = i
                    in_section = True
                elif in_section:
                    section_lines.append(line)

            # flush last section
            if in_section:
                section_text = "".join(section_lines)
                if all(t in section_text.lower() for t in terms):
                    results.append({
                        "file": rel_path,
                        "heading": current_heading.strip(),
                        "line": section_start + 1,
                        "snippet": section_text.strip()[:500],
                    })

# also search non-section lines (e.g., table rows, list items)
for label, kb_dir in kb_dirs:
    for root, dirs, files in os.walk(kb_dir):
        dirs[:] = [d for d in dirs if not d.startswith(".")]
        for fname in sorted(files):
            if not fname.endswith(".md"):
                continue
            rel_path = os.path.relpath(os.path.join(root, fname), workspace)
            if allowed and fname not in allowed and rel_path not in allowed:
                continue

            try:
                with open(os.path.join(root, fname), 'r', encoding='utf-8') as f:
                    lines = f.readlines()
            except Exception:
                continue

            # find matching non-section lines
            in_section = False
            for i, line in enumerate(lines):
                if line.startswith("#"):
                    in_section = True
                    continue
                if not in_section:
                    if all(t in line.lower() for t in terms):
                        # get surrounding context (±1 line)
                        start = max(0, i - 1)
                        end = min(len(lines), i + 2)
                        snippet = "".join(lines[start:end]).strip()
                        results.append({
                            "file": rel_path,
                            "heading": "(inline)",
                            "line": i + 1,
                            "snippet": snippet[:300],
                        })
                if line.strip() == "":
                    in_section = False

# deduplicate
seen = set()
unique = []
for r in results:
    key = (r["file"], r["heading"], r["snippet"][:100])
    if key not in seen:
        seen.add(key)
        unique.append(r)
results = unique

# output
if output_mode == "json":
    print(json.dumps({
        "keyword": keyword,
        "results": results,
        "total": len(results),
    }, indent=2, ensure_ascii=False))
else:
    if not results:
        print(f"\033[2m[lore] no results for: {keyword}\033[0m")
        print()
        sys.exit(0)

    print()
    print(f"\033[2m[lore] {len(results)} results for:\033[0m \033[1m{keyword}\033[0m")
    print()

    for i, r in enumerate(results):
        print(f"  \033[33m{r['file']}\033[0m:\033[2m{r['line']}\033[0m  \033[1m{r['heading']}\033[0m")
        # indent snippet
        for line in r["snippet"].split("\n")[:8]:
            print(f"  \033[2m│\033[0m {line}")
        print()
        if i >= 9:
            print(f"  \033[2m... and {len(results) - 10} more results\033[0m")
            break
    print()

PY
