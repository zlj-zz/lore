#!/usr/bin/env bash
# graph.sh — generate a Mermaid dependency graph for a multi-repo workspace.
#
# Usage:
#   ./scripts/graph.sh [path]                # Mermaid to stdout
#   ./scripts/graph.sh [path] --embed        # wrap in ```mermaid for MAP.md
#   ./scripts/graph.sh [path] --json         # structured dependency data
#   ./scripts/graph.sh --help
#
# Output: Mermaid graph TD showing inter-repo dependencies.
# Paste directly into .pikb/MAP.md.
#
# Requires: bash, python3. macOS bash 3.2 compatible.

set -euo pipefail

OUTPUT_MODE="mermaid"
LAYERED=0

# collect flags first, remaining arg is workspace path
ARGS=()
while [[ $# -gt 0 ]]; do
  case "$1" in
    --embed)   OUTPUT_MODE="embed"; shift ;;
    --json)    OUTPUT_MODE="json"; shift ;;
    --mermaid) OUTPUT_MODE="mermaid"; shift ;;
    --layered) LAYERED=1; shift ;;
    -h|--help)
      cat <<EOF
Usage: $(basename "$0") [path] [--embed] [--json] [--layered]

Generate a Mermaid dependency graph for a multi-repo workspace.
Default output: raw Mermaid to stdout.

  --embed     wrap in \`\`\`mermaid for pasting into MAP.md
  --json      structured dependency data
  --layered   group nodes by detected layer (API/Service/Infra)
  --help
EOF
      exit 0
      ;;
    *) ARGS+=("$1"); shift ;;
  esac
done

WORKSPACE="${ARGS[0]:-.}"

WORKSPACE="$(cd "$WORKSPACE" 2>/dev/null && pwd -P)" || {
  echo '{"error": "cannot access workspace"}' >&2
  exit 1
}

export WORKSPACE OUTPUT_MODE LAYERED
python3 <<'PY'
import os, json, sys, re

workspace = os.environ['WORKSPACE']
output_mode = os.environ.get('OUTPUT_MODE', 'mermaid')
layered = os.environ.get('LAYERED', '0') == '1'

# ── Detect repos ──
def detect_repos():
    markers = {"go.mod", "package.json", "Cargo.toml", ".git",
               "pyproject.toml", "Gemfile", "pom.xml", "build.gradle"}
    repos = {}
    try:
        for entry in sorted(os.listdir(workspace)):
            if entry.startswith("."):
                continue
            full = os.path.join(workspace, entry)
            if not os.path.isdir(full):
                continue
            entries = set(os.listdir(full))
            if entries & markers:
                ptype = "unknown"
                if "go.mod" in entries:
                    ptype = "go"
                elif "package.json" in entries:
                    ptype = "node"
                elif "Cargo.toml" in entries:
                    ptype = "rust"
                elif "pyproject.toml" in entries:
                    ptype = "python"
                repos[entry] = {"path": full, "type": ptype, "module_name": None, "deps": []}
    except PermissionError:
        pass
    return repos

# ── Extract module identity + dependencies ──
def extract_go(repo_path):
    """Parse go.mod for module name and internal requires."""
    mod_file = os.path.join(repo_path, "go.mod")
    if not os.path.isfile(mod_file):
        return None, []
    module_name = None
    deps = []
    try:
        with open(mod_file) as f:
            for line in f:
                line = line.strip()
                if line.startswith("module "):
                    module_name = line.split("module ", 1)[1].strip()
                elif line.startswith("require ") and not line.startswith("require ("):
                    parts = line.split()
                    if len(parts) >= 2:
                        dep = parts[1]
                        # only keep likely-internal deps (not public packages)
                        if "/" in dep and not dep.startswith(("github.com/", "golang.org/", "google.golang.org/", "go.opentelemetry.io/")):
                            deps.append(dep.split("/")[-1])
                elif line.startswith("\t") and ("require" not in line.lower()):
                    # inside require (...) block
                    parts = line.split()
                    if len(parts) >= 1:
                        dep = parts[0]
                        if "/" in dep and not dep.startswith(("github.com/", "golang.org/", "google.golang.org/", "go.opentelemetry.io/")):
                            deps.append(dep.split("/")[-1])
                elif line == ")":
                    break  # end of require block
    except Exception:
        pass
    return module_name, deps

def extract_node(repo_path):
    """Parse package.json for name and dependencies."""
    pkg_file = os.path.join(repo_path, "package.json")
    if not os.path.isfile(pkg_file):
        return None, []
    try:
        with open(pkg_file) as f:
            data = json.load(f)
    except Exception:
        return None, []
    name = data.get("name", os.path.basename(repo_path))
    # strip scope: @org/pkg → pkg
    if name and name.startswith("@"):
        name = name.split("/")[-1] if "/" in name else name
    deps = []
    for field in ("dependencies", "devDependencies"):
        for dep in data.get(field, {}):
            # strip scope
            dname = dep
            if dep.startswith("@"):
                dname = dep.split("/")[-1] if "/" in dep else dep
            deps.append(dname)
    return name, deps

def extract_python(repo_path):
    """Parse pyproject.toml or setup.py for name and deps."""
    # try pyproject.toml first
    pyproj = os.path.join(repo_path, "pyproject.toml")
    name = None
    deps = []
    if os.path.isfile(pyproj):
        try:
            with open(pyproj) as f:
                content = f.read()
            # extract name from [project]
            nm = re.search(r'name\s*=\s*"([^"]+)"', content)
            if nm:
                name = nm.group(1)
            # extract dependencies
            in_deps = False
            for line in content.split('\n'):
                if re.match(r'^dependencies\s*=\s*\[', line):
                    in_deps = True
                    continue
                if in_deps and line.strip() == ']':
                    in_deps = False
                    continue
                if in_deps:
                    m = re.search(r'"([^"]+)"', line)
                    if m:
                        dep = m.group(1)
                        if not dep.startswith(("http", "git+", "file:")):
                            deps.append(dep)
        except Exception:
            pass
    return name, deps

def extract_rust(repo_path):
    """Parse Cargo.toml for package name and dependencies."""
    cargo = os.path.join(repo_path, "Cargo.toml")
    if not os.path.isfile(cargo):
        return None, []
    name = None
    deps = []
    try:
        with open(cargo) as f:
            content = f.read()
        nm = re.search(r'name\s*=\s*"([^"]+)"', content)
        if nm:
            name = nm.group(1)
        in_deps = False
        for line in content.split('\n'):
            if re.match(r'^\[dependencies\]', line):
                in_deps = True
                continue
            if in_deps and line.startswith('['):
                in_deps = False
                continue
            if in_deps:
                m = re.match(r'(\S+)\s*=', line)
                if m:
                    dep = m.group(1)
                    if dep != "workspace":
                        deps.append(dep)
    except Exception:
        pass
    return name, deps

EXTRACTORS = {
    "go": extract_go,
    "node": extract_node,
    "python": extract_python,
    "rust": extract_rust,
}

# ── Main ──
repos = detect_repos()
if not repos:
    print("graph TD\n  %% no repos found")
    sys.exit(0)

# extract module names and deps
repo_names = set(repos.keys())
for name, info in repos.items():
    extractor = EXTRACTORS.get(info["type"])
    if extractor:
        module_name, deps = extractor(info["path"])
        info["module_name"] = module_name or name
        # only keep deps that match a workspace repo
        info["deps"] = [d for d in deps if d in repo_names and d != name]

# collect edges
edges = []
for name, info in repos.items():
    for dep in info["deps"]:
        edges.append((name, dep))

# ── Layer detection ──
def detect_layer(name, info):
    """Guess layer based on name and module."""
    n = name.lower()
    mn = (info.get("module_name") or "").lower()
    combined = n + " " + mn
    if any(kw in combined for kw in ("gateway", "proxy", "api", "router", "bff", "frontend", "web", "ui")):
        return "API"
    if any(kw in combined for kw in ("auth", "notification", "queue", "worker", "cron", "scheduler", "event", "message", "log", "monitor", "cache", "redis")):
        return "Infra"
    return "Service"

layers = {}
for name, info in repos.items():
    layers[name] = detect_layer(name, info)

# order: API → Service → Infra
layer_order = {"API": 0, "Service": 1, "Infra": 2}

# ── Output ──
if output_mode == "json":
    out = {
        "repos": {n: {"type": i["type"], "module": i["module_name"], "layer": layers[n]} for n, i in repos.items()},
        "edges": [{"from": f, "to": t} for f, t in edges],
    }
    print(json.dumps(out, indent=2, ensure_ascii=False))

elif output_mode == "embed":
    print("```mermaid")
    print("graph TD")
    # group by layer
    for layer in ["API", "Service", "Infra"]:
        nodes = [n for n, l in layers.items() if l == layer]
        if nodes:
            print(f"  subgraph {layer}")
            for n in sorted(nodes):
                print(f"    {re.sub(r'[^a-zA-Z0-9]', '_', n)}[\"{n}\"]")
            print("  end")
    for src, dst in sorted(edges):
        s = re.sub(r'[^a-zA-Z0-9]', '_', src)
        d = re.sub(r'[^a-zA-Z0-9]', '_', dst)
        print(f"  {s} --> {d}")
    print("```")

else:  # raw mermaid
    print("graph TD")
    if layered:
        for layer in ["API", "Service", "Infra"]:
            nodes = [n for n, l in layers.items() if l == layer]
            if nodes:
                print(f"  subgraph {layer}")
                for n in sorted(nodes):
                    print(f"    {re.sub(r'[^a-zA-Z0-9]', '_', n)}[\"{n}\"]")
                print("  end")
    else:
        for name in sorted(repos):
            safe = re.sub(r'[^a-zA-Z0-9]', '_', name)
            print(f"  {safe}[\"{name}\"]")
    for src, dst in sorted(edges):
        s = re.sub(r'[^a-zA-Z0-9]', '_', src)
        d = re.sub(r'[^a-zA-Z0-9]', '_', dst)
        print(f"  {s} --> {d}")
PY
