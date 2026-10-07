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

from lore_runtime import discover, pitfalls as pitfalls_mod

REPO_MARKERS = {
    "go.mod",
    "package.json",
    "Cargo.toml",
    ".git",
    "pyproject.toml",
    "Gemfile",
    "pom.xml",
    "build.gradle",
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
            "issues": [
                {
                    "check": ".pikb/",
                    "severity": "error",
                    "detail": ".pikb/ not found — KB not initialized",
                    "action": "run /skill:lore 创建知识库",
                }
            ],
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
                    issues.append(
                        {
                            "check": "CONTEXT.md coverage",
                            "severity": "warning",
                            "detail": "repo '%s' missing CONTEXT.md" % entry,
                            "action": "create .pi/kb/CONTEXT.md for %s" % entry,
                            "repo": entry,
                        }
                    )
    except PermissionError:
        pass

    # 2. KB age check
    try:
        map_file = Path(pikb) / "MAP.md"
        if map_file.is_file():
            age_days = (datetime.now().timestamp() - map_file.stat().st_mtime) / 86400
            if age_days > 30:
                issues.append(
                    {
                        "check": "KB age",
                        "severity": "warning",
                        "detail": "KB last updated %.0fd ago" % age_days,
                        "action": "review and refresh KB entries",
                    }
                )

    except Exception:
        pass

    # 3. PITFALLS entries: missing Triggers / stale Last-verified, across the
    #    workspace file and every repo's .pi/kb file.
    for pf in discover.find_all_pitfalls(workspace):
        rel = os.path.relpath(str(pf), workspace)
        try:
            findings = pitfalls_mod.audit_entries(pf)
        except Exception:
            continue
        for f in findings:
            if f["kind"] == "missing_triggers":
                issue = {
                    "check": "PITFALLS Triggers",
                    "severity": "warning",
                    "detail": "PITFALLS %s #%s '%s' missing Triggers:"
                    % (rel, f["id"], f["title"]),
                    "action": "add Triggers: field to PITFALLS %s #%s" % (rel, f["id"]),
                    "path": str(pf),
                }
            elif f["kind"] == "stale":
                issue = {
                    "check": "KB age",
                    "severity": "warning",
                    "detail": "PITFALLS %s #%s '%s' Last-verified %dd ago"
                    % (rel, f["id"], f["title"], int(f["age_days"])),
                    "action": "review and refresh PITFALLS %s #%s" % (rel, f["id"]),
                    "path": str(pf),
                }
            else:
                continue
            if f["owner"]:
                issue["owner"] = f["owner"]
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

    fingerprint = re.sub(r"\d+", "N", error_message[:80])
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
            proposals.append(
                {
                    "type": "auto",
                    "target": "CONTEXT.md",
                    "content": (
                        "# %s\n\n"
                        "TODO: describe this service.\n\n"
                        "## Entry\n"
                        "- main: \n"
                        "- config: \n"
                    )
                    % repo,
                    "path": "%s/.pi/kb/CONTEXT.md" % repo,
                    "detail": "create CONTEXT.md for new repo '%s'" % repo,
                }
            )

        elif check == "KB age":
            detail = issue.get("detail", "KB may be stale")
            owner = issue.get("owner", "")
            if owner:
                detail += " (Owner: %s)" % owner
            proposals.append(
                {
                    "type": "draft",
                    "target": "MAP.md",
                    "detail": detail,
                    "action": action,
                }
            )

        elif check == "PITFALLS Triggers":
            detail = issue.get("detail", "missing Triggers")
            owner = issue.get("owner", "")
            if owner:
                detail += " (Owner: %s)" % owner
            proposals.append(
                {
                    "type": "auto",
                    "target": "PITFALLS.md",
                    "detail": detail,
                    "action": action,
                }
            )

        elif check == ".pikb/":
            proposals.append(
                {
                    "type": "draft",
                    "target": "KB init",
                    "detail": "KB not initialized — run /skill:lore 创建知识库",
                }
            )

    return proposals
