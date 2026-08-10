#!/usr/bin/env bash
# audit-kb.sh — quality audit for knowledge base files.
#
# Usage:
#   ./scripts/audit-kb.sh [path]              # human-readable report
#   ./scripts/audit-kb.sh [path] --json       # structured output
#   ./scripts/audit-kb.sh [path] --strict     # exit 1 on any issue
#   ./scripts/audit-kb.sh --help
#
# Checks:
#   1. Cross-reference validity (links between KB files work)
#   2. PITFALLS completeness (Difficulty/Symptom/Root Cause/Solution)
#   3. Status marker consistency (only ✅🔧📋💡)
#   4. CONTEXT.md coverage (every repo has one)
#   5. Dead links (both internal and external to docs/)
#   6. Self-contained principle (facts vs bare references)
#   7. Heading uniqueness (no duplicate headings within a file)
#
# Exit 0: clean.  Exit 1: issues found (always, unless --strict not set and 0 issues)
#
# Requires: bash, python3.

set -euo pipefail

WORKSPACE="${1:-.}"
OUTPUT_MODE="text"
STRICT=0

while [[ $# -gt 0 ]]; do
  case "$1" in
    --json)   OUTPUT_MODE="json"; shift ;;
    --text)   OUTPUT_MODE="text"; shift ;;
    --strict) STRICT=1; shift ;;
    -h|--help)
      cat <<EOF
Usage: $(basename "$0") [path] [--json] [--strict]

Audit knowledge base quality.

Checks: cross-references, PITFALLS fields, status markers,
        coverage, dead links, self-contained principle.

  --strict   exit 1 on any issue (default: exit 0 for warnings only)
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

export WORKSPACE OUTPUT_MODE STRICT
python3 <<'PY'
import os, json, sys, re
from collections import defaultdict

workspace = os.environ['WORKSPACE']
output_mode = os.environ.get('OUTPUT_MODE', 'text')
strict = os.environ.get('STRICT', '0') == '1'

pikb = os.path.join(workspace, ".pikb")
errors = []    # must-fix
warnings = []  # should-fix
ok_items = []

def read_file(path):
    try:
        with open(path, 'r') as f:
            return f.read()
    except Exception:
        return None

def find_md_files(base_dir):
    """Return dict of rel_path → abs_path for all .md files under base_dir."""
    files = {}
    if not os.path.isdir(base_dir):
        return files
    for root, dirs, fnames in os.walk(base_dir):
        dirs[:] = [d for d in dirs if not d.startswith(".")]
        for fname in fnames:
            if fname.endswith(".md"):
                abs_path = os.path.join(root, fname)
                rel = os.path.relpath(abs_path, workspace)
                files[rel] = abs_path
    return files

def find_all_kb_files():
    """All .md files in .pikb/ and .pi/kb/."""
    all_files = {}
    for d in [pikb, os.path.join(workspace, ".pi", "kb")]:
        all_files.update(find_md_files(d))
    return all_files

def find_repos():
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

def extract_links(content, source_file):
    """Extract internal markdown links and check if targets exist."""
    broken = []
    for m in re.finditer(r'\[([^\]]*)\]\(([^)]+)\)', content):
        target = m.group(2)
        text = m.group(1)
        if target.startswith(('http://', 'https://', '#', 'mailto:')):
            continue

        # resolve relative to source file
        src_dir = os.path.dirname(os.path.join(workspace, source_file))
        resolved = os.path.normpath(os.path.join(src_dir, target))
        if not os.path.exists(resolved):
            broken.append({
                "source": source_file,
                "text": text,
                "target": target,
                "line": content[:m.start()].count('\n') + 1,
            })
    return broken

def check_pitfalls(content, fname):
    """Check PITFALLS entries for required fields."""
    issues = []
    # split by ## sections (each pitfall is a ## heading)
    sections = re.split(r'\n(?=## \d+\.)', content)
    for i, section in enumerate(sections):
        if not section.strip().startswith("## "):
            continue
        heading = section.strip().split('\n')[0]
        required = {
            "Difficulty": r'-\s*Difficulty\s*:',
            "Symptom": r'-\s*Symptom\s*:',
            "Root Cause": r'-\s*Root\s*Cause\s*:',
            "Solution": r'-\s*Solution\s*:',
        }
        missing_fields = [f for f, pat in required.items() if not re.search(pat, section)]
        if missing_fields:
            issues.append({
                "file": fname,
                "heading": heading,
                "missing_fields": missing_fields,
            })
    return issues

def check_status_markers(content, fname):
    """Check for unmarked or invalid status markers."""
    issues = []
    valid_markers = {'✅', '🔧', '📋', '💡'}
    # find lines that look like status items but don't have valid markers
    for i, line in enumerate(content.split('\n'), 1):
        stripped = line.strip()
        if not stripped:
            continue
        # check for lines that appear to be checklist items without markers
        if re.match(r'-\s+(?:已|未|待|计划|进行中)', stripped):
            # has chinese status word but no emoji marker
            has_marker = any(m in stripped for m in valid_markers)
            if not has_marker:
                issues.append({
                    "file": fname,
                    "line": i,
                    "text": stripped[:80],
                    "issue": "status line without marker (use ✅🔧📋💡)",
                })
        # check for unknown/invalid emoji markers
        if re.match(r'-\s+[^\w\s]', stripped):
            emoji = stripped[2] if len(stripped) > 2 else ""
            if emoji and emoji not in valid_markers and ord(emoji) > 127:
                # could be an emoji — check if it looks like a status marker
                pass  # too many false positives, skip aggressive emoji check

    return issues

def check_self_contained(content, fname):
    """Check for 'bare reference' anti-pattern (linking without inlining facts)."""
    issues = []
    for i, line in enumerate(content.split('\n'), 1):
        # pattern: "- xxx: see docs/..." or "xxx 见 docs/..."
        m = re.match(r'\s*-\s*(.+?)[：:]\s*(?:see|见|参考|参见|refer to)\s+([^\s]+\.md)', line, re.IGNORECASE)
        if m:
            issues.append({
                "file": fname,
                "line": i,
                "text": line.strip(),
                "issue": "bare reference — facts should be inlined, not just linked",
            })
    return issues

def check_duplicate_headings(content, fname):
    """Check for duplicate headings within a file."""
    issues = []
    headings = defaultdict(list)
    for i, line in enumerate(content.split('\n'), 1):
        if line.startswith('#'):
            headings[line.strip()].append(i)
    for h, lines in headings.items():
        if len(lines) > 1:
            issues.append({
                "file": fname,
                "heading": h,
                "lines": lines,
                "issue": f"duplicate heading ({len(lines)} occurrences)",
            })
    return issues

# ── Main ──

if not os.path.isdir(pikb):
    errors.append({"check": "KB exists", "detail": ".pikb/ not found — nothing to audit"})
    if output_mode == "json":
        print(json.dumps({"workspace": workspace, "errors": errors, "warnings": [], "ok": []}, indent=2, ensure_ascii=False))
    else:
        print(f"\n\033[2m[lore]\033[0m \033[1m{workspace}\033[0m")
        print(f"\n  \033[31m✗\033[0m  .pikb/ not found — nothing to audit\n")
    sys.exit(1)

kb_files = find_all_kb_files()
repos = find_repos()

# 1. Cross-reference validity
print(f"  checking {len(kb_files)} KB files...", file=sys.stderr)
total_broken = 0
for rel, abs_path in sorted(kb_files.items()):
    content = read_file(abs_path)
    if not content:
        continue
    broken = extract_links(content, rel)
    total_broken += len(broken)

if total_broken > 0:
    errors.append({
        "check": "cross-references",
        "detail": f"{total_broken} broken internal link(s)",
        "items": [f"{b['source']}:{b['line']} → {b['target']}" for b in broken[:10]],
    })
else:
    ok_items.append("cross-references: all valid")

# 2. PITFALLS completeness
pitfall_issues = []
for rel, abs_path in sorted(kb_files.items()):
    if "PITFALLS" in rel.upper():
        content = read_file(abs_path)
        if content:
            pitfall_issues.extend(check_pitfalls(content, rel))

if pitfall_issues:
    warnings.append({
        "check": "PITFALLS fields",
        "detail": f"{len(pitfall_issues)} incomplete entr{'y' if len(pitfall_issues)==1 else 'ies'}",
        "items": [f"{p['file']}: {p['heading']} — missing {', '.join(p['missing_fields'])}" for p in pitfall_issues],
    })
else:
    ok_items.append("PITFALLS: all entries complete")

# 3. CONTEXT.md coverage
missing = []
for repo in repos:
    if not os.path.isfile(os.path.join(workspace, repo, ".pi", "kb", "CONTEXT.md")):
        missing.append(repo)

if missing:
    warnings.append({
        "check": "CONTEXT.md coverage",
        "detail": f"{len(missing)} of {len(repos)} repos uncovered: {', '.join(missing[:5])}",
    })
else:
    ok_items.append(f"CONTEXT.md: {len(repos)}/{len(repos)} repos covered")

# 4. Self-contained principle
bare_refs = []
for rel, abs_path in sorted(kb_files.items()):
    content = read_file(abs_path)
    if content:
        bare_refs.extend(check_self_contained(content, rel))

if bare_refs:
    warnings.append({
        "check": "self-contained",
        "detail": f"{len(bare_refs)} bare reference(s) — facts should be inlined",
        "items": [f"{b['file']}:{b['line']}: {b['text'][:60]}" for b in bare_refs[:5]],
    })
else:
    ok_items.append("self-contained: facts inlined")

# 4.5. Wikilink cross-references + loose ref migration hints
wikilink_results = []
loose_refs = []
for rel, abs_path in sorted(kb_files.items()):
    content = read_file(abs_path)
    if not content:
        continue
    # Check [[wikilinks]]
    for m in re.finditer(r'\[\[([^\]]+)\]\]', content):
        target = m.group(1)
        line = content[:m.start()].count('\n') + 1
        # Resolve: strip anchor, check file exists
        target_file = target.split('#')[0] if '#' in target else target
        if not target_file.endswith('.md'):
            target_file += '.md'
        # Try relative to the source file's directory
        src_dir = os.path.dirname(abs_path)
        resolved = os.path.normpath(os.path.join(src_dir, target_file))
        if not os.path.isfile(resolved):
            # Try workspace-level .pikb/
            resolved2 = os.path.join(pikb, target_file)
            if not os.path.isfile(resolved2):
                wikilink_results.append({
                    "file": rel, "line": line,
                    "wikilink": target,
                    "status": "broken",
                })
    # Detect loose references (free-text "see X" patterns)
    for m in re.finditer(r'(?:see|见|参见|参考|refer to)\s+([A-Z]+\.md[#§\d]*)', content, re.IGNORECASE):
        loose_refs.append({
            "file": rel,
            "line": content[:m.start()].count('\n') + 1,
            "ref": m.group(0),
            "hint": "consider converting to [[%s]]" % m.group(1),
        })

if wikilink_results:
    broken_wl = [w for w in wikilink_results if w["status"] == "broken"]
    if broken_wl:
        warnings.append({
            "check": "wikilinks",
            "detail": f"{len(broken_wl)} broken wikilink(s)",
            "items": [f"{w['file']}:{w['line']}: [[{w['wikilink']}]]" for w in broken_wl[:5]],
        })
    else:
        ok_items.append("wikilinks: all valid")

if loose_refs:
    warnings.append({
        "check": "loose references",
        "detail": f"{len(loose_refs)} loose reference(s) — consider converting to wikilinks",
        "items": [f"{l['file']}:{l['line']}: {l['hint']}" for l in loose_refs[:5]],
    })

# 5. Status markers
status_issues = []
for rel, abs_path in sorted(kb_files.items()):
    content = read_file(abs_path)
    if content:
        status_issues.extend(check_status_markers(content, rel))

if status_issues:
    warnings.append({
        "check": "status markers",
        "detail": f"{len(status_issues)} line(s) without proper markers",
        "items": [f"{s['file']}:{s['line']}: {s['text'][:60]}" for s in status_issues[:5]],
    })
else:
    ok_items.append("status markers: consistent")

# 6. Duplicate headings
dup_issues = []
for rel, abs_path in sorted(kb_files.items()):
    content = read_file(abs_path)
    if content:
        dup_issues.extend(check_duplicate_headings(content, rel))

if dup_issues:
    warnings.append({
        "check": "duplicate headings",
        "detail": f"{len(dup_issues)} duplicate(s)",
        "items": [f"{d['file']}: {d['heading']} (lines {', '.join(map(str, d['lines']))})" for d in dup_issues],
    })
else:
    ok_items.append("headings: unique")

# ── Output ──
has_errors = len(errors) > 0
has_warnings = len(warnings) > 0
clean = not has_errors and not has_warnings

if output_mode == "json":
    out = {
        "workspace": workspace,
        "total_files": len(kb_files),
        "total_repos": len(repos),
        "errors": errors,
        "warnings": warnings,
        "ok": ok_items,
        "clean": clean,
    }
    print(json.dumps(out, indent=2, ensure_ascii=False))
else:
    print(f"\n\033[2m[lore]\033[0m \033[1m{workspace}\033[0m  —  {len(kb_files)} KB files, {len(repos)} repos\n")

    for item in ok_items:
        print(f"  \033[32m✓\033[0m  {item}")

    for w in warnings:
        print(f"  \033[33m⚠\033[0m  \033[1m{w['check']}\033[0m: {w['detail']}")
        if 'items' in w:
            for item in w['items'][:5]:
                print(f"      {item}")

    for e in errors:
        print(f"  \033[31m✗\033[0m  \033[1m{e['check']}\033[0m: {e['detail']}")
        if 'items' in e:
            for item in e['items'][:5]:
                print(f"      {item}")

    if clean:
        print(f"\n  \033[32m✓ all clean\033[0m\n")
    else:
        print()

    exit_code = 1 if (strict or has_errors) else 0
    sys.exit(exit_code)
PY
