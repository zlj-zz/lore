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
            matched.append({"id": pid, "title": title, "difficulty": diff})

    return matched


def format_additional_context(cwd: str, path: str, matches: List[dict]) -> str:
    if not matches:
        return ""
    pitfalls_path = _find_pitfalls_file(_start_dir(cwd, path))
    if not pitfalls_path:
        return ""
    lines = [
        "[lore] ⚠️ PITFALLS match — read %s before continuing:" % pitfalls_path
    ]
    for m in matches:
        stars = "⭐" * m["difficulty"] if m["difficulty"] else ""
        extra = (" (%s)" % stars) if stars else ""
        lines.append("  #%s %s%s" % (m["id"], m["title"], extra))
    return "\n".join(lines)
