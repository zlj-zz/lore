from pathlib import Path
from typing import List, Optional, Tuple

from lore_runtime import discover

RULES = """## Knowledge Base (lore)

On session start: CONTEXT.md is injected below when present. Output 📚 lore loaded.

During work:
- Writing code → check .pikb/CONVENTIONS.md
- Multi-module changes → check .pikb/MAP.md
- Error / risky edit → check .pikb/PITFALLS.md (and .pi/kb/PITFALLS.md)
- New repo → create .pi/kb/CONTEXT.md
- Significant change → ask: "knowledge base 需要更新吗?"

Search KB: `~/.agents/skills/lore/scripts/quick-ref.sh <keyword>`
Missing KB in complex workspace → `/skill:lore 创建知识库`"""

CONTEXT_MAX_CHARS = 2048
MAP_MAX_LINES = 80


def build_session_additional_context(cwd: str) -> Tuple[str, Optional[str], List[str]]:
    cwd = str(Path(cwd).resolve())
    warnings: List[str] = []
    parts = [RULES]

    ctx = discover.find_context(cwd)
    if ctx is not None:
        text = ctx.read_text(encoding="utf-8", errors="replace")[:CONTEXT_MAX_CHARS]
        parts.append("📚 lore loaded\n\n# CONTEXT.md (%s)\n\n%s" % (ctx, text))
        if "@workspace" in text or ".pikb" in text:
            mp = discover.find_map(cwd, ctx)
            if mp is not None:
                lines = mp.read_text(encoding="utf-8", errors="replace").splitlines()[:MAP_MAX_LINES]
                parts.append("## Workspace Map (summary)\n\n" + "\n".join(lines))
    else:
        parts.append(
            "[lore] No .pi/kb/CONTEXT.md under %s. "
            "Run /skill:lore 创建知识库 if this is a multi-repo workspace." % cwd
        )

    return "\n\n".join(parts), (str(ctx) if ctx else None), warnings
