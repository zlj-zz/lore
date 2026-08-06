from pathlib import Path
from typing import List, Optional


def find_context(start: str) -> Optional[Path]:
    cur = Path(start).resolve()
    for _ in range(8):
        ctx = cur / ".pi" / "kb" / "CONTEXT.md"
        if ctx.is_file():
            return ctx
        if cur.parent == cur:
            break
        cur = cur.parent
    return None


def find_pikb(start: str) -> Optional[Path]:
    cur = Path(start).resolve()
    for _ in range(8):
        pikb = cur / ".pikb"
        if pikb.is_dir():
            return pikb
        if cur.parent == cur:
            break
        cur = cur.parent
    return None


def find_pitfalls(start: str) -> List[Path]:
    found = []
    cur = Path(start).resolve()
    seen = set()
    for _ in range(8):
        for rel in (".pikb/PITFALLS.md", ".pi/kb/PITFALLS.md"):
            p = cur / rel
            try:
                key = str(p.resolve())
            except Exception:
                continue
            if key in seen:
                continue
            if p.is_file():
                seen.add(key)
                found.append(p)
        if cur.parent == cur:
            break
        cur = cur.parent
    return found


def find_map(start: str, ctx: Optional[Path] = None) -> Optional[Path]:
    candidates = []
    start_p = Path(start).resolve()
    candidates.append(start_p / ".pikb" / "MAP.md")
    candidates.append(start_p.parent / ".pikb" / "MAP.md")
    pikb = find_pikb(start)
    if pikb:
        candidates.append(pikb / "MAP.md")
    if ctx is not None:
        if len(ctx.parents) > 2:
            candidates.append(ctx.parents[2] / ".pikb" / "MAP.md")
        if len(ctx.parents) > 3:
            candidates.append(ctx.parents[3] / ".pikb" / "MAP.md")
    seen = set()
    for c in candidates:
        try:
            key = str(c.resolve())
        except Exception:
            continue
        if key in seen:
            continue
        seen.add(key)
        if c.is_file():
            return c
    return None
