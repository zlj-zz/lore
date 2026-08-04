# lore

Project knowledge base for large / multi-repo projects.
Cross-agent: pi / Claude Code / Cursor CLI.

## Install

```bash
git clone https://github.com/zlj-zz/lore.git ~/projects/lore
cd ~/projects/lore
./install.sh          # all agents
# ./install.sh --pi --claude  # specific
```

| Agent | What it sets up |
|------|-----------------|
| pi | `~/.pi/agent/AGENTS.md` + Extension (auto-inject on session start) |
| Claude Code | `~/.claude/AGENTS.md` + PostToolUse hook (reminds on first tool call) |
| Cursor | `~/.cursorrules` |

## Usage

```
/skill:lore create a knowledge base for this project
```

Agent will explore the codebase, ask clarifying questions, and generate:
- `.pikb/` — workspace-level: MAP, CONVENTIONS, PITFALLS
- `.pi/kb/` — per-repo: CONTEXT (quick start)

## Structure

```
lore/
├── SKILL.md              # skill definition + methodology
├── install.sh            # one-command agent setup
├── AGENTS.md             # loading rules for any agent
├── templates/            # document templates
│   ├── MAP.md            # service map
│   ├── CONVENTIONS.md    # code conventions
│   ├── PITFALLS.md       # known pitfalls
│   └── CONTEXT.md        # per-repo quick start
└── README.md
```

## License

MIT
