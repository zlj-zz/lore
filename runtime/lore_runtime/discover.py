import re
from pathlib import Path
from typing import List, Optional

WIKILINK_RE = re.compile(r"\[\[([^\]]+)\]\]")
# Markdown inline link, excluding images (![alt](url)).
MARKDOWN_LINK_RE = re.compile(r"(?<!!)\[([^\]]*)\]\(([^)\s]+)\)")
# Characters GitHub strips when building a heading anchor.
_SLUG_STRIP_RE = re.compile(r"[^\w\u4e00-\u9fff \-]")


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


def find_all_pitfalls(workspace: str) -> List[Path]:
    """PITFALLS files relevant to a workspace: the workspace-level
    ``.pikb/PITFALLS.md`` plus every repo's ``.pi/kb/PITFALLS.md``."""
    root = Path(workspace).resolve()
    found: List[Path] = []
    workspace_pf = root / ".pikb" / "PITFALLS.md"
    if workspace_pf.is_file():
        found.append(workspace_pf)
    try:
        for entry in sorted(root.iterdir()):
            if entry.is_dir() and not entry.name.startswith("."):
                repo_pf = entry / ".pi" / "kb" / "PITFALLS.md"
                if repo_pf.is_file():
                    found.append(repo_pf)
    except OSError:
        pass
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
        return {
            "resolved": None,
            "anchor": None,
            "error": "file not found: %s" % target,
        }

    if anchor is None:
        return {"resolved": path, "anchor": None, "error": None}

    matched_header = _match_anchor(path, anchor)
    if matched_header is None:
        return {
            "resolved": path,
            "anchor": None,
            "error": "anchor not found: %s" % anchor,
        }

    return {"resolved": path, "anchor": matched_header, "error": None}


def github_slug(text: str) -> str:
    """Approximate GitHub's heading anchor: lowercase, drop punctuation,
    collapse whitespace, spaces to hyphens. Keeps CJK and underscores."""
    s = _SLUG_STRIP_RE.sub("", text.strip().lower())
    s = re.sub(r"\s+", " ", s).strip()
    return s.replace(" ", "-")


def heading_anchors(text: str) -> set:
    """Every GitHub-style anchor in a markdown document, including the
    ``-1`` / ``-2`` suffixes GitHub appends to duplicate headings."""
    anchors = set()
    seen = {}
    for line in text.splitlines():
        if not line.startswith("#"):
            continue
        base = github_slug(line.lstrip("#").strip())
        if not base:
            continue
        n = seen.get(base, 0)
        seen[base] = n + 1
        anchors.add(base if n == 0 else "%s-%d" % (base, n))
    return anchors


def resolve_markdown_link(url: str, source_dir: Path) -> dict:
    """Resolve a relative markdown link against its file's directory.

    Only relative ``.md`` targets are checked; absolute URLs, bare anchors and
    non-``.md`` targets return ``skip=True`` so they are not reported.
    Returns {resolved, anchor, error, skip}.
    """
    raw = url.strip()
    if not raw or "://" in raw or raw.startswith(("/", "#", "mailto:", "tel:")):
        return {"resolved": None, "anchor": None, "error": None, "skip": True}
    target_part, _, anchor = raw.partition("#")
    target_part = target_part.strip()
    if not target_part.lower().endswith(".md"):
        return {"resolved": None, "anchor": None, "error": None, "skip": True}
    try:
        target = (source_dir / target_part).resolve()
    except OSError:
        target = None
    if target is None or not target.is_file():
        return {
            "resolved": None,
            "anchor": None,
            "error": "file not found: %s" % target_part,
            "skip": False,
        }
    if not anchor:
        return {"resolved": target, "anchor": None, "error": None, "skip": False}
    try:
        text = target.read_text(encoding="utf-8", errors="replace")
    except OSError:
        return {"resolved": target, "anchor": None, "error": None, "skip": False}
    if anchor.strip("-").lower() not in {a.strip("-") for a in heading_anchors(text)}:
        return {
            "resolved": target,
            "anchor": None,
            "error": "anchor not found: %s" % anchor,
            "skip": False,
        }
    return {"resolved": target, "anchor": anchor, "error": None, "skip": False}


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


def _classify(resolved: dict) -> tuple:
    """Map a resolve result to (status, detail)."""
    if resolved["error"] is None:
        detail = str(resolved["resolved"])
        if resolved["anchor"]:
            detail += " #%s" % resolved["anchor"]
        return "ok", detail
    if resolved["error"].startswith("file not found"):
        return "broken_file", resolved["error"]
    if "anchor" in resolved["error"]:
        return "broken_anchor", resolved["error"]
    return "broken_file", resolved["error"]


def check_crossrefs(cwd: str) -> list:
    """Scan all KB .md files for cross-references, verify each resolves.

    Checks both ``[[wikilink]]`` syntax and relative markdown links to .md
    files. Each reference is resolved from its containing file, not from cwd.

    Returns list of dicts:
      {source_file, line, wikilink, status: ok|broken_file|broken_anchor, detail}
    where ``wikilink`` is the raw reference text (either syntax).
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
            refs = []
            for match in WIKILINK_RE.finditer(line):
                link = match.group(1).strip()
                if link:
                    refs.append((link, resolve_wikilink(link, str(path.parent))))
            for match in MARKDOWN_LINK_RE.finditer(line):
                url = match.group(2).strip()
                resolved = resolve_markdown_link(url, path.parent)
                if not resolved["skip"]:
                    refs.append((url, resolved))
            for ref, resolved in refs:
                status, detail = _classify(resolved)
                results.append(
                    {
                        "source_file": str(path),
                        "line": lineno,
                        "wikilink": ref,
                        "status": status,
                        "detail": detail,
                    }
                )
    return results
