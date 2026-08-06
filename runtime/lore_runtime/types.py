"""Canonical event result keys (dict, not a class — JSON-friendly)."""

STATUS_HEALTHY = "healthy"
STATUS_DEGRADED = "degraded"
STATUS_MISSING = "missing"

REQUIRED_KEYS = (
    "ok", "event", "cwd", "status", "context_path",
    "additional_context", "warnings", "env", "matches",
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
