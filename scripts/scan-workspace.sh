#!/usr/bin/env bash
# scan-workspace.sh — detect repos, docs, and structure in a workspace.
#
# Usage:
#   ./scripts/scan-workspace.sh [path]        # JSON to stdout
#   ./scripts/scan-workspace.sh --help
#
# Output: JSON with repos (type, agent files), docs, and other items.
# Used by lore Step 1 (侦查) to bootstrap knowledge base creation.
#
# Requires: bash, python3. macOS bash 3.2 compatible.

set -euo pipefail

WORKSPACE="${1:-.}"

if [[ "$WORKSPACE" == "-h" || "$WORKSPACE" == "--help" ]]; then
  cat <<EOF
Usage: $(basename "$0") [path]

Scan a workspace directory and output structured JSON:
  repos:   detected repositories with type and agent files
  docs:    documentation files/directories
  other:   non-repo, non-doc items

Default path: current directory.
EOF
  exit 0
fi

# resolve to absolute
WORKSPACE="$(cd "$WORKSPACE" 2>/dev/null && pwd -P)" || {
  echo '{"error": "cannot access workspace path"}' >&2
  exit 1
}

export WORKSPACE
python3 <<'PY'
import os, json, sys

workspace = os.environ['WORKSPACE']
result = {
    "workspace": workspace,
    "repos": [],
    "docs": [],
    "other": []
}

# project type markers (ordered by priority — first match wins)
TYPE_MARKERS = [
    ("go",       ["go.mod"]),
    ("rust",     ["Cargo.toml"]),
    ("node",     ["package.json"]),
    ("python",   ["pyproject.toml", "setup.py", "setup.cfg", "requirements.txt"]),
    ("java",     ["pom.xml", "build.gradle", "build.gradle.kts"]),
    ("ruby",     ["Gemfile"]),
    ("elixir",   ["mix.exs"]),
    ("dotnet",   ["*.csproj", "*.fsproj"]),
    ("php",      ["composer.json"]),
    ("zig",      ["build.zig"]),
    ("c/cpp",    ["CMakeLists.txt", "Makefile"]),
]

# key files to note beyond type markers
KEY_FILES = [
    "Dockerfile", "docker-compose.yml", "docker-compose.yaml",
    ".env.example", ".env.template",
    "main.go", "main.py", "index.js", "index.ts",
    "README.md", "README",
    "Makefile", "Justfile",
]

AGENT_FILES = [
    "AGENTS.md", "CLAUDE.md", "AGENTS.txt",
    ".cursorrules", ".cursor/rules",
    ".github/copilot-instructions.md",
]

DOC_PATTERNS = {"docs", "doc", "documentation", "wiki", "spec", "specs", "design"}

def detect_type(path):
    """Detect project type from marker files."""
    entries = set(os.listdir(path))
    for ptype, markers in TYPE_MARKERS:
        for m in markers:
            if m.startswith("*."):
                # glob pattern (e.g., *.csproj)
                ext = m[1:]
                if any(e.endswith(ext) for e in entries):
                    return ptype
            elif m in entries:
                return ptype
    # fallback: has .git but no type markers
    if ".git" in entries:
        return "unknown"
    return None

def find_agent_files(path):
    """Find agent instruction files in repo root."""
    found = []
    entries = set(os.listdir(path))
    for f in AGENT_FILES:
        if f in entries:
            found.append(f)
    # also check .cursor/rules/ directory
    cursor_rules = os.path.join(path, ".cursor", "rules")
    if os.path.isdir(cursor_rules):
        for f in os.listdir(cursor_rules):
            found.append(f".cursor/rules/{f}")
    return found

def find_key_files(path):
    """Find notable files beyond type markers."""
    found = []
    entries = set(os.listdir(path))
    for f in KEY_FILES:
        if f in entries:
            found.append(f)
    # also check for nested entry points
    for sub in ["cmd", "src", "internal", "pkg"]:
        subpath = os.path.join(path, sub)
        if os.path.isdir(subpath):
            for f in os.listdir(subpath):
                if f.endswith((".go", ".py", ".ts", ".js", ".rs", ".java")):
                    found.append(f"{sub}/{f}")
                    if len(found) >= 3:  # limit
                        break
            if len(found) >= 3:
                break
    return found

try:
    entries = sorted(os.listdir(workspace))
except PermissionError:
    print(json.dumps({"error": "permission denied", "workspace": workspace}))
    sys.exit(1)

for name in entries:
    # Skip hidden (except .pikb)
    if name.startswith(".") and name != ".pikb":
        continue

    full = os.path.join(workspace, name)
    if not os.path.isdir(full):
        continue

    ptype = detect_type(full)

    if ptype is not None:
        # It's a repository
        repo = {
            "name": name,
            "type": ptype,
            "agent_files": find_agent_files(full),
            "key_files": find_key_files(full),
        }
        if os.path.exists(os.path.join(full, ".pi", "kb", "CONTEXT.md")):
            repo["has_context_md"] = True
        # check if .pikb/ exists at workspace level
        if os.path.exists(os.path.join(workspace, ".pikb")):
            repo["workspace_has_pikb"] = True
        result["repos"].append(repo)

    elif name.lower() in DOC_PATTERNS or name.lower().startswith("doc"):
        # It's a documentation directory
        sub_items = []
        try:
            for f in sorted(os.listdir(full)):
                if f.endswith(".md") or f.endswith(".rst") or f.endswith(".txt"):
                    sub_items.append(f)
        except PermissionError:
            pass
        result["docs"].append({
            "name": name,
            "files": sub_items[:10]  # limit
        })

    else:
        # Other directory — check if it contains scripts, tools, etc.
        result["other"].append(name)

# also check workspace-level doc files
workspace_docs = []
for f in sorted(os.listdir(workspace)):
    if not os.path.isfile(os.path.join(workspace, f)):
        continue
    if f.endswith(".md") or f.endswith(".rst") or f == "README":
        workspace_docs.append(f)
if workspace_docs:
    result["docs"].insert(0, {"name": "(root)", "files": workspace_docs})

# summary
result["summary"] = {
    "total_repos": len(result["repos"]),
    "repo_types": list(set(r["type"] for r in result["repos"])),
    "repos_with_agent_files": sum(1 for r in result["repos"] if r["agent_files"]),
    "repos_with_context_md": sum(1 for r in result["repos"] if r.get("has_context_md")),
    "doc_sources": len(result["docs"]),
    "has_pikb": os.path.exists(os.path.join(workspace, ".pikb")),
}

print(json.dumps(result, indent=2, ensure_ascii=False))
PY
