"""Canonical event result keys (dict, not a class — JSON-friendly)."""

STATUS_HEALTHY = "healthy"
STATUS_DEGRADED = "degraded"
STATUS_MISSING = "missing"

REQUIRED_KEYS = (
    "ok",
    "event",
    "cwd",
    "status",
    "context_path",
    "additional_context",
    "warnings",
    "env",
    "matches",
)


def empty_result(event: str, cwd: str) -> dict:
    return {
        "ok": True,
        "event": event,
        "cwd": cwd,
        "status": STATUS_MISSING,
        "context_path": None,
        "additional_context": "",
        "warnings": [],
        "env": {"LORE_LOADED": "0", "LORE_CONTEXT": "", "LORE_CWD": cwd},
        "matches": [],
    }


def session_end_summary_template() -> dict:
    return {
        "session_summary": {
            "pitfall_matches": 0,
            "auto_writes": 0,
            "drafts": 0,
            "errors_logged": 0,
        },
        "staleness": {
            "stale": False,
            "issues": [],
        },
        "maintenance_proposals": [],
    }
