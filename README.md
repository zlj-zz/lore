# lore

Project knowledge base for large / multi-repo projects.
Cross-agent compatible (pi / Claude Code / Cursor CLI).

## Install

```bash
# pi
mkdir -p ~/.agents/skills
git clone https://github.com/zlj-zz/lore.git ~/.agents/skills/lore

# Claude Code / Cursor — add to AGENTS.md:
```

See [SKILL.md](SKILL.md) for the full methodology.

## Structure

```
lore/
├── SKILL.md                 # skill definition
├── templates/               # document templates
│   ├── MAP.md
│   ├── CONVENTIONS.md
│   ├── PITFALLS.md
│   └── CONTEXT.md
└── README.md
```

## Templates

Copy templates to initialize a knowledge base:

```bash
mkdir -p .pikb/
cp ~/.agents/skills/lore/templates/{MAP,CONVENTIONS,PITFALLS}.md .pikb/
# per-repo:
mkdir -p .pi/kb/
cp ~/.agents/skills/lore/templates/CONTEXT.md .pi/kb/
```

## License

MIT
