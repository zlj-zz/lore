import os
import re
from datetime import datetime
from pathlib import Path

from lore_runtime import discover
from lore_runtime.pitfalls import _extract_field
from lore_runtime.types import STATUS_DEGRADED, STATUS_HEALTHY, STATUS_MISSING

REPO_MARKERS = {
    "go.mod", "package.json", "Cargo.toml", ".git",
    "pyproject.toml", "Gemfile", "pom.xml", "build.gradle",
}


def check(cwd: str) -> dict:
    workspace = str(Path(cwd).resolve())
    warnings = []
    ok_items = []

    pikb = discover.find_pikb(workspace)
    has_pikb = pikb is not None

    if has_pikb:
        ok_items.append(".pikb/: exists")
    else:
        warnings.append("KB: missing — .pikb/ not found. Run /skill:lore 创建知识库")

    ctx = discover.find_context(workspace)
    if ctx is not None:
        ok_items.append("CONTEXT.md: exists")
    else:
        warnings.append(f"CONTEXT.md: missing at {workspace}/.pi/kb/CONTEXT.md")

    if has_pikb:
        kb_files = []
        for root, _dirs, files in os.walk(str(pikb)):
            for f in files:
                if f.endswith(".md"):
                    kb_files.append(os.path.join(root, f))

        if kb_files:
            ok_items.append(f"KB files: {len(kb_files)} files")

            try:
                newest = max(os.path.getmtime(f) for f in kb_files)
                oldest = min(os.path.getmtime(f) for f in kb_files)
                age_days = (datetime.now().timestamp() - oldest) / 86400
                newest_age = (datetime.now().timestamp() - newest) / 86400

                if age_days > 30:
                    warnings.append(f"KB age: oldest file modified {age_days:.0f}d ago — may be stale")
                elif age_days > 14:
                    warnings.append(f"KB age: oldest file modified {age_days:.0f}d ago")
                else:
                    ok_items.append(f"KB freshness: {age_days:.0f}d old, newest {newest_age:.0f}d")
            except Exception:
                pass

            # Per-entry PITFALLS Last-verified staleness
            try:
                pitfalls_path = Path(pikb) / "PITFALLS.md"
                if pitfalls_path.is_file():
                    file_mtime = pitfalls_path.stat().st_mtime
                    raw = pitfalls_path.read_text(encoding="utf-8", errors="replace")
                    sections = re.split(r"^## ", raw, flags=re.M)[1:]
                    for sec in sections:
                        m = re.match(r"^(\d+)\.\s*(.+)", sec)
                        if not m:
                            continue
                        pid = m.group(1)
                        title = m.group(2).strip().splitlines()[0].strip()
                        owner = _extract_field(sec, "Owner")
                        lv = _extract_field(sec, "Last verified")
                        lv_ts = None
                        if lv:
                            try:
                                lv_ts = datetime.strptime(lv.strip(), "%Y-%m-%d").timestamp()
                            except (ValueError, TypeError):
                                lv_ts = None
                        # Entries without a parseable Last verified fall back to
                        # file mtime (backward compat) and stay covered by the
                        # file-level KB age check above.
                        if lv_ts is None:
                            continue
                        now = datetime.now().timestamp()
                        lv_age = (now - lv_ts) / 86400
                        mtime_age = (now - file_mtime) / 86400
                        entry_age_days = max(lv_age, mtime_age)
                        if entry_age_days > 90:
                            owner_note = " (Owner: %s)" % owner if owner else ""
                            warnings.append(
                                "PITFALLS #%s '%s': Last-verified %dd ago%s"
                                % (pid, title, int(entry_age_days), owner_note)
                            )
            except Exception:
                pass

            repos_without_context = []
            try:
                for entry in sorted(os.listdir(workspace)):
                    if entry.startswith("."):
                        continue
                    full = os.path.join(workspace, entry)
                    if not os.path.isdir(full):
                        continue
                    entries = set(os.listdir(full))
                    if entries & REPO_MARKERS:
                        if not os.path.isfile(os.path.join(full, ".pi", "kb", "CONTEXT.md")):
                            repos_without_context.append(entry)
            except PermissionError:
                pass

            if repos_without_context:
                missing = ", ".join(repos_without_context[:5])
                suffix = "..." if len(repos_without_context) > 5 else ""
                warnings.append(
                    f"CONTEXT.md coverage: {len(repos_without_context)} repos missing: {missing}{suffix}"
                )
            else:
                ok_items.append("CONTEXT.md coverage: all repos covered")
        else:
            warnings.append("KB files: empty — no .md files in .pikb/")

    if not has_pikb:
        status = STATUS_MISSING
    elif warnings:
        status = STATUS_DEGRADED
    else:
        status = STATUS_HEALTHY

    return {"status": status, "warnings": warnings, "ok_items": ok_items}
