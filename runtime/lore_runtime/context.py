import re
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

CONTEXT_MAX_CHARS = 500
MAP_MAX_LINES = 80


def parse_context(raw: str) -> dict:
    """Parse CONTEXT.md content.

    Returns dict with keys:
      - desc: first paragraph (before ## Entry or ## Hotspots)
      - entry_points: lines from ## Entry section
      - hotspots: list of {pattern, why, refs} from ## Hotspots table
    """
    desc_lines: List[str] = []
    entry_points: List[str] = []
    hotspots: List[dict] = []

    lines = raw.splitlines()
    i = 0
    # Preamble: everything before the first ## heading is the desc.
    while i < len(lines) and not lines[i].startswith("## "):
        desc_lines.append(lines[i])
        i += 1

    # Remaining ## sections.
    while i < len(lines):
        if not lines[i].startswith("## "):
            i += 1
            continue
        heading = lines[i][3:].strip().lower()
        i += 1
        body: List[str] = []
        while i < len(lines) and not lines[i].startswith("## "):
            body.append(lines[i])
            i += 1
        if heading == "entry":
            for bl in body:
                bl = bl.strip()
                if bl.startswith("- "):
                    entry_points.append(bl[2:].strip())
        elif heading == "hotspots":
            hotspots = _parse_hotspots_table(body)

    return {
        "desc": "\n".join(desc_lines).strip(),
        "entry_points": entry_points,
        "hotspots": hotspots,
    }


def _parse_hotspots_table(body: List[str]) -> List[dict]:
    """Parse the '| File pattern | Why | Refs |' table body into hotspot dicts.

    Skips the header row and the '|---|---|' separator row.
    refs are wikilinks extracted from the Refs column.
    """
    rows: List[dict] = []
    for line in body:
        line = line.strip()
        if not line.startswith("|"):
            continue
        cells = [c.strip() for c in line.strip("|").split("|")]
        if len(cells) < 3:
            continue
        # Separator row (e.g. |---|---|).
        if all(re.fullmatch(r":?-{2,}:?", c) for c in cells if c):
            continue
        # Header row.
        if cells[0].lower() in ("file pattern", "pattern"):
            continue
        refs = re.findall(r"\[\[([^\]]+)\]\]", cells[2])
        rows.append({"pattern": cells[0], "why": cells[1], "refs": refs})
    return rows


def match_hotspots(cwd: str, file_path: str) -> list:
    """Match a file path against CONTEXT.md Hotspots table.

    Returns list of {pattern, why, refs} for matching rows.
    Uses simple substring match: file_path contains pattern.
    Returns empty list when no CONTEXT.md is found.
    """
    ctx = discover.find_context(cwd)
    if ctx is None:
        return []
    raw = ctx.read_text(encoding="utf-8", errors="replace")
    parsed = parse_context(raw)
    return [h for h in parsed["hotspots"] if h["pattern"] and h["pattern"] in file_path]


def build_session_additional_context(cwd: str) -> Tuple[str, Optional[str], List[str]]:
    cwd = str(Path(cwd).resolve())
    warnings: List[str] = []
    parts = [RULES]

    ctx = discover.find_context(cwd)
    if ctx is not None:
        text = ctx.read_text(encoding="utf-8", errors="replace")[:CONTEXT_MAX_CHARS]
        parsed = parse_context(text)
        marker = "📚 lore loaded"
        if parsed["desc"]:
            first = parsed["desc"].splitlines()[0].lstrip("# ").strip()
            if first:
                marker += " (%s)" % first
        parts.append("%s\n\n# CONTEXT.md (%s)\n\n%s" % (marker, ctx, text))
        if "@workspace" in text or ".pikb" in text:
            mp = discover.find_map(cwd, ctx)
            if mp is not None:
                lines = mp.read_text(encoding="utf-8", errors="replace").splitlines()[
                    :MAP_MAX_LINES
                ]
                parts.append("## Workspace Map (summary)\n\n" + "\n".join(lines))
    else:
        parts.append(
            "[lore] No .pi/kb/CONTEXT.md under %s. "
            "Run /skill:lore 创建知识库 if this is a multi-repo workspace." % cwd
        )

    return "\n\n".join(parts), (str(ctx) if ctx else None), warnings
