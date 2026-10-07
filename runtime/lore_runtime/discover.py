import re
from pathlib import Path
from typing import List, Optional

WIKILINK_RE = re.compile(r"\[\[([^\]]+)\]\]")


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


def resolve_wikilink(link: str, cwd: str) -> dict:
    """Resolve a wikilink like [[PITFALLS#3]] or [[CONVENTIONS#并发安全]].

    Returns:
      {resolved: Path|None, anchor: str|None, error: str|None}

    File extension is optional: [[PITFALLS]] and [[PITFALLS.md]] both work.
    Anchor syntax: #N (number for PITFALLS entries) or #text (header text).
    """
    raw = link.strip()
    # Strip surrounding [[...]] if present; bare text is also accepted here.
    m = re.fullmatch(r"\[\[(.+)\]\]", raw)
    if m:
        raw = m.group(1).strip()
    if not raw:
        return {"resolved": None, "anchor": None, "error": "empty wikilink"}

    target, _, anchor = raw.partition("#")
    target = target.strip()
    anchor = anchor.strip() or None
    if not target:
        return {"resolved": None, "anchor": None, "error": "empty target"}

    if not target.lower().endswith(".md"):
        target += ".md"

    path = _resolve_kb_file(target, cwd)
    if path is None:
        return {"resolved": None, "anchor": None, "error": "file not found: %s" % target}

    if anchor is None:
        return {"resolved": path, "anchor": None, "error": None}

    matched_header = _match_anchor(path, anchor)
    if matched_header is None:
        return {"resolved": path, "anchor": None, "error": "anchor not found: %s" % anchor}

    return {"resolved": path, "anchor": matched_header, "error": None}


def _resolve_kb_file(target: str, cwd: str) -> Optional[Path]:
    """Locate a KB file for ``target`` (with .md) under ``cwd``.

    Looks in ``.pikb/`` first, then the workspace root, walking upward from
    ``cwd`` (bounded, mirroring the other discover helpers).
    """
    target_path = Path(target)
    if target_path.is_absolute():
        return target_path if target_path.is_file() else None

    cur = Path(cwd).resolve()
    for _ in range(8):
        pikb = cur / ".pikb"
        if pikb.is_dir():
            cand = pikb / target_path
            try:
                if cand.is_file():
                    return cand.resolve()
            except OSError:
                pass
        cand = cur / target_path
        try:
            if cand.is_file():
                return cand.resolve()
        except OSError:
            pass
        if cur.parent == cur:
            break
        cur = cur.parent
    return None


def _match_anchor(path: Path, anchor: str) -> Optional[str]:
    """Find the header text in ``path`` matching ``anchor``.

    PITFALLS.md: a numeric anchor matches ``## N. Title``.
    Other .md: anchor matches a heading's text (case-insensitive,
    whitespace-normalized).
    """
    is_pitfalls = path.name.lower() == "pitfalls.md"
    try:
        lines = path.read_text(encoding="utf-8", errors="replace").splitlines()
    except OSError:
        return None

    if is_pitfalls and anchor.isdigit():
        for line in lines:
            if not line.startswith("## "):
                continue
            header = line[3:].strip()
            m = re.match(r"^(\d+)\s*[.)]?\s*(.*)$", header)
            if m and m.group(1) == anchor:
                return header
        return None

    norm_anchor = re.sub(r"\s+", " ", anchor).strip().lower()
    for line in lines:
        heading = re.sub(r"^#+\s*", "", line).strip()
        if not heading:
            continue
        norm_heading = re.sub(r"\s+", " ", heading).lower()
        if norm_heading == norm_anchor:
            return heading
    return None


def check_crossrefs(cwd: str) -> list:
    """Scan all KB .md files for [[wikilinks]], verify each resolves.

    Returns list of dicts:
      {source_file, line, wikilink, status: ok|broken_file|broken_anchor, detail}
    """
    results = []
    root = Path(cwd).resolve()
    if not root.is_dir():
        return results

    md_files = []
    try:
        for path in root.rglob("*.md"):
            parts = path.relative_to(root).parts
            if ".pikb" in parts or (".pi" in parts and "kb" in parts):
                md_files.append(path)
    except OSError:
        return results

    for path in sorted(md_files):
        try:
            lines = path.read_text(encoding="utf-8", errors="replace").splitlines()
        except OSError:
            continue
        for lineno, line in enumerate(lines, start=1):
            for match in WIKILINK_RE.finditer(line):
                wikilink = match.group(1).strip()
                if not wikilink:
                    continue
                # Resolve from the containing file, not the scan root: a KB
                # file's wikilink points at its own workspace's .pikb/, which
                # may not be an ancestor of cwd (e.g. nested workspaces).
                resolved = resolve_wikilink(wikilink, str(path.parent))
                if resolved["error"] is None:
                    status = "ok"
                    detail = str(resolved["resolved"])
                    if resolved["anchor"]:
                        detail += " #%s" % resolved["anchor"]
                elif resolved["error"].startswith("file not found"):
                    status = "broken_file"
                    detail = resolved["error"]
                elif "anchor" in resolved["error"]:
                    status = "broken_anchor"
                    detail = resolved["error"]
                else:
                    status = "broken_file"
                    detail = resolved["error"]
                results.append({
                    "source_file": str(path),
                    "line": lineno,
                    "wikilink": wikilink,
                    "status": status,
                    "detail": detail,
                })
    return results
