# lore

<p align="center">
  <em>Structured, self-updating knowledge base for multi-repo projects.</em>
</p>

<p align="center">
  <img src="https://img.shields.io/badge/license-MIT-blue" alt="License">
  <img src="https://img.shields.io/badge/agents-pi%20%7C%20Claude%20%7C%20Cursor-6e56cf" alt="Agents">
</p>

---

**Problem:** Every time you open a multi-repo workspace, your agent starts blind — it doesn't know which services exist, how they connect, what conventions to follow, or what pitfalls to avoid.

**Lore gives your agent a memory.** One command to install, one command to initialize, then autopilot.

```
$ ./scripts/on-session-start.sh

[lore] workspace: ~/projects
  ✓  .pikb/: exists
  ✓  KB files: 7 files
  ✓  KB freshness: 3d old, newest 1d
  ✓  CONTEXT.md: all 8 repos covered
```

---

## Install

```bash
git clone https://github.com/zlj-zz/lore.git ~/projects/lore
cd ~/projects/lore
./install.sh              # pi + Claude + Cursor
```

## Usage

```bash
/skill:lore 创建知识库     # initialize for current workspace
./scripts/quick-ref.sh auth   # search KB for "auth"
./scripts/check-staleness.sh  # is KB up to date?
./scripts/audit-kb.sh         # quality check
```

The agent explores your codebase, asks clarifying questions, then generates:

```
workspace/
  .pikb/
  ├── MAP.md              ← service map, data flow, module relations
  ├── CONVENTIONS.md      ← code conventions, patterns, naming rules
  └── PITFALLS.md         ← known pitfalls with difficulty, symptoms, solutions
  each-repo/
    .pi/kb/
    └── CONTEXT.md         ← quick start: entry points, config, key files
```

After that, every session starts with context already loaded.

---

## How it works

| Session phase | What happens |
|---------------|--------------|
| **Start** | `on-session-start.sh` checks KB health → agent reads CONTEXT.md + MAP.md |
| **Writing code** | Agent checks CONVENTIONS.md before writing |
| **Cross-module** | Agent consults MAP.md for service relationships |
| **Error** | Agent searches PITFALLS.md before guessing |
| **End** | Agent detects new repos, patterns, pitfalls → auto-updates KB |

---

## Scripts

| Script | Purpose |
|--------|---------|
| `scan-workspace.sh` | Detect repos, types, agent files — structured JSON |
| `on-session-start.sh` | KB health check at session start |
| `quick-ref.sh <keyword>` | Section-aware keyword search across KB |
| `check-staleness.sh` | Detect stale entries (new repos, modified references) |
| `audit-kb.sh` | Quality audit (cross-refs, PITFALLS fields, dead links, markers) |

---

## Agents

| Agent | Install target |
|-------|---------------|
| pi | `AGENTS.md` rules + extension |
| Claude Code | `AGENTS.md` rules + PostToolUse hook |
| Cursor | `.cursorrules` |

```bash
./install.sh --to pi,claude    # specific
./install.sh status --all       # see what's installed
```

---

## Principles

- **Self-contained** — facts are inlined, external docs are source annotations only
- **Code is authority** — when docs and code disagree, code wins
- **Silent maintenance** — agent updates KB without asking for new repos, patterns, or pitfalls
- **Progressive disclosure** — CONTEXT.md on session start, others on demand

## License

MIT
