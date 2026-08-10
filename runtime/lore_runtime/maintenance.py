"""Maintenance engine — staleness detection + proposal generation.

Design: runtime does signal detection and template generation.
The AI model receives instructions via additional_context and
executes the actual KB writes (Edit/Write tool calls).
"""

import os
import re
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List

from lore_runtime import discover
from lore_runtime.pitfalls import _extract_field

REPO_MARKERS = {
    "go.mod", "package.json", "Cargo.toml", ".git",
    "pyproject.toml", "Gemfile", "pom.xml", "build.gradle",
}

# Track error occurrences within this process
_ERROR_SEEN: Dict[str, int] = {}


def check_staleness(cwd: str) -> Dict[str, Any]:
    """Lightweight staleness check. Returns {stale: bool, issues: [...]}."""
    issues: List[Dict[str, Any]] = []
    workspace = str(Path(cwd).resolve())

    pikb = discover.find_pikb(workspace)
    if not pikb:
        return {
            "stale": True,
            "issues": [{
                "check": ".pikb/",
                "severity": "error",
                "detail": ".pikb/ not found — KB not initialized",
                "action": "run /skill:lore 创建知识库",
            }],
        }

    # 1. Repos missing CONTEXT.md
    try:
        for entry in sorted(os.listdir(workspace)):
            if entry.startswith("."):
                continue
            full = os.path.join(workspace, entry)
            if not os.path.isdir(full):
                continue
            entries = set(os.listdir(full))
            if entries & REPO_MARKERS:
                ctx = os.path.join(full, ".pi", "kb", "CONTEXT.md")
                if not os.path.isfile(ctx):
                    issues.append({
                        "check": "CONTEXT.md coverage",
                        "severity": "warning",
                        "detail": "repo '%s' missing CONTEXT.md" % entry,
                        "action": "create .pi/kb/CONTEXT.md for %s" % entry,
                        "repo": entry,
                    })
    except PermissionError:
        pass

    # 2. KB age check
    try:
        map_file = Path(pikb) / "MAP.md"
        if map_file.is_file():
            age_days = (datetime.now().timestamp() - map_file.stat().st_mtime) / 86400
            if age_days > 30:
                issues.append({
                    "check": "KB age",
                    "severity": "warning",
                    "detail": "KB last updated %.0fd ago" % age_days,
                    "action": "review and refresh KB entries",
                })

        # Per-entry PITFALLS Last-verified staleness
        pitfalls_file = Path(pikb) / "PITFALLS.md"
        if pitfalls_file.is_file():
            content = pitfalls_file.read_text(encoding="utf-8", errors="replace")
            file_mtime = pitfalls_file.stat().st_mtime
            for pm in re.finditer(r'^## (\d+)\. (.+)$', content, re.MULTILINE):
                pid, title = pm.group(1), pm.group(2)
                end = content.find('\n## ', pm.end())
                if end == -1:
                    end = len(content)
                section = content[pm.end():end]
                owner = _extract_field(section, "Owner")
                lv = _extract_field(section, "Last verified")
                lv_ts = None
                if lv:
                    try:
                        lv_ts = datetime.strptime(lv.strip(), "%Y-%m-%d").timestamp()
                    except (ValueError, TypeError):
                        lv_ts = None
                # Entries without a parseable Last verified fall back to file
                # mtime (backward compat) and stay covered by the MAP.md check.
                if lv_ts is None:
                    continue
                now = datetime.now().timestamp()
                lv_age = (now - lv_ts) / 86400
                mtime_age = (now - file_mtime) / 86400
                entry_age = max(lv_age, mtime_age)
                if entry_age > 90:
                    issues.append({
                        "check": "KB age",
                        "severity": "warning",
                        "detail": "PITFALLS #%s '%s' Last-verified %dd ago"
                                  % (pid, title, int(entry_age)),
                        "action": "review and refresh PITFALLS #%s" % pid,
                        "owner": owner,
                    })
    except Exception:
        pass

    # 3. PITFALLS triggers completeness
    pitfalls_file = Path(pikb) / "PITFALLS.md"
    if pitfalls_file.is_file():
        content = pitfalls_file.read_text(encoding="utf-8", errors="replace")
        for m in re.finditer(r'^## (\d+)\. (.+)$', content, re.MULTILINE):
            pid, title = m.group(1), m.group(2)
            end = content.find('\n## ', m.end())
            if end == -1:
                end = len(content)
            section = content[m.end():end]
            if 'Triggers:' not in section:
                issue = {
                    "check": "PITFALLS Triggers",
                    "severity": "warning",
                    "detail": "PITFALLS #%s '%s' missing Triggers:" % (pid, title),
                    "action": "add Triggers: field to PITFALLS #%s" % pid,
                }
                owner = _extract_field(section, "Owner")
                if owner:
                    issue["owner"] = owner
                issues.append(issue)

    return {
        "stale": len(issues) > 0,
        "issues": issues,
    }


def detect_novel_error(cwd: str, error_message: str) -> bool:
    """Return True if this error has been seen multiple times and is 'novel'.

    Novel = seen >= 3 times in this session without matching a known PITFALLS pattern.
    """
    import re
    fingerprint = re.sub(r'\d+', 'N', error_message[:80])
    count = _ERROR_SEEN.get(fingerprint, 0) + 1
    _ERROR_SEEN[fingerprint] = count
    return count >= 3


def generate_proposals(cwd: str, stale: Dict[str, Any]) -> List[Dict[str, Any]]:
    """Generate maintenance proposals from staleness issues.

    Returns list of proposals, each with type: 'auto' (low risk) or 'draft' (high risk).
    """
    proposals: List[Dict[str, Any]] = []

    for issue in stale.get("issues", []):
        check = issue.get("check", "")
        action = issue.get("action", "")

        if check == "CONTEXT.md coverage" and "repo" in issue:
            repo = issue["repo"]
            proposals.append({
                "type": "auto",
                "target": "CONTEXT.md",
                "content": (
                    "# %s\n\n"
                    "TODO: describe this service.\n\n"
                    "## Entry\n"
                    "- main: \n"
                    "- config: \n"
                ) % repo,
                "path": "%s/.pi/kb/CONTEXT.md" % repo,
                "detail": "create CONTEXT.md for new repo '%s'" % repo,
            })

        elif check == "KB age":
            detail = issue.get("detail", "KB may be stale")
            owner = issue.get("owner", "")
            if owner:
                detail += " (Owner: %s)" % owner
            proposals.append({
                "type": "draft",
                "target": "MAP.md",
                "detail": detail,
                "action": action,
            })

        elif check == "PITFALLS Triggers":
            detail = issue.get("detail", "missing Triggers")
            owner = issue.get("owner", "")
            if owner:
                detail += " (Owner: %s)" % owner
            proposals.append({
                "type": "auto",
                "target": "PITFALLS.md",
                "detail": detail,
                "action": action,
            })

        elif check == ".pikb/":
            proposals.append({
                "type": "draft",
                "target": "KB init",
                "detail": "KB not initialized — run /skill:lore 创建知识库",
            })

    return proposals
