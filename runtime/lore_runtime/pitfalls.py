import re
from pathlib import Path
from typing import List

from lore_runtime import discover


def _start_dir(cwd: str, path: str) -> str:
    if path and Path(path).is_absolute():
        return str(Path(path).resolve().parent)
    return cwd


def _find_pitfalls_file(start: str):
    found = discover.find_pitfalls(start)
    return found[0] if found else None


def match(cwd: str, path: str = "", cmd: str = "") -> List[dict]:
    pitfalls_path = _find_pitfalls_file(_start_dir(cwd, path))
    if not pitfalls_path:
        return []

    raw = pitfalls_path.read_text(encoding="utf-8", errors="replace")
    sections = re.split(r"^## ", raw, flags=re.M)[1:]
    matched = []

    for sec in sections:
        m = re.match(r"^(\d+)\.\s*(.+)", sec)
        if not m:
            continue
        pid, title = m.group(1), m.group(2).strip().splitlines()[0].strip()
        trig = re.search(r"Triggers:\s*(.+)", sec)
        if not trig:
            continue
        trig_str = trig.group(1)
        hit = False
        for kind, val in re.findall(r"`(file|api|cmd):([^`]+)`", trig_str):
            if kind == "file" and path and val in path:
                hit = True
            elif kind == "cmd" and cmd and val in cmd:
                hit = True
        if hit:
            diff = sec.count("⭐")
            # Extract body: everything between title line and Triggers line
            body_lines = sec.splitlines()
            # Skip the "N. Title" line (first line)
            body_start = 1
            body_end = len(body_lines)
            for i, bl in enumerate(body_lines):
                if re.match(r"^\s*(?:- )?Triggers:", bl):
                    body_end = i
                    break
            body = "\n".join(body_lines[body_start:body_end]).strip()
            matched.append({"id": pid, "title": title, "difficulty": diff, "body": body})

    return matched


def _extract_field(body: str, field: str) -> str:
    """Extract a field value from a PITFALLS body. Supports both 'Field: value' and '- Field: value' formats."""
    import re
    pattern = r'(?:^|\n)\s*(?:- )?' + re.escape(field) + r'\s*[:：-]\s*(.+?)(?:\n\s*(?:- )?(?:\w|$)|$)'
    m = re.search(pattern, body)
    if m:
        return m.group(1).strip()
    return ""


def format_additional_context(cwd: str, path: str, matches: List[dict]) -> str:
    if not matches:
        return ""
    pitfalls_path = _find_pitfalls_file(_start_dir(cwd, path))
    if not pitfalls_path:
        return ""
    lines = [
        "[lore] ⚠️ PITFALLS match — see %s:" % pitfalls_path
    ]
    total_chars = len(lines[0])
    max_total = 3000
    max_per_body = 1500

    for m in matches:
        stars = "⭐" * m["difficulty"] if m["difficulty"] else ""
        extra = (" (%s)" % stars) if stars else ""
        header = "  #%s %s%s" % (m["id"], m["title"], extra)
        lines.append(header)
        total_chars += len(header)

        body = m.get("body", "")
        if body:
            # Try to extract standard fields first
            symptom = _extract_field(body, "Symptom")
            root_cause = _extract_field(body, "Root Cause")
            solution = _extract_field(body, "Solution")

            if symptom or root_cause or solution:
                extracted = []
                if symptom:
                    extracted.append("    Symptom: %s" % symptom)
                if root_cause:
                    extracted.append("    Root Cause: %s" % root_cause)
                if solution:
                    extracted.append("    Solution: %s" % solution)
                body_text = "\n".join(extracted)
            else:
                body_text = "    " + body[:max_per_body].replace("\n", "\n    ")

            if total_chars + len(body_text) > max_total:
                remaining = max_total - total_chars - 20
                trunc = (body_text[:remaining] + "...") if remaining > 0 else "..."
                lines.append(trunc)
                break
            lines.append(body_text)
            total_chars += len(body_text)

    return "\n".join(lines)


def match_error(cwd: str, error_message: str) -> List[dict]:
    """Match an error message against PITFALLS patterns.

    Uses Triggers cmd: patterns plus file path extraction from error messages.
    Returns matched pitfalls with full body.
    """
    path_in_error = ""
    for word in error_message.split():
        if "/" in word and "." in word:
            path_in_error = word
            break
    return match(cwd, path=path_in_error, cmd=error_message)
