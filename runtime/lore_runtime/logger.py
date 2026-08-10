"""Session logging to `.pikb/.lore-session-log.jsonl` (JSONL).

Each record written by :func:`append` is a single JSON object on one line with:
``ts`` (ISO-8601 UTC), ``session`` (per-process session id), ``event``, plus
any extra keyword fields.  ``None`` field values are filtered out.
"""

import json
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List

#: Per-process session id — all log lines written by this process share it.
_SESSION_ID = uuid.uuid4().hex[:12]

_LOG_FILE = ".lore-session-log.jsonl"
_PIKB_DIR = ".pikb"


def _resolve_log_path(cwd: str) -> Path:
    """Compute the log file path without creating any directories."""
    return Path(cwd) / _PIKB_DIR / _LOG_FILE


def _log_path(cwd: str) -> str:
    """Resolve log file path, creating .pikb/ if needed."""
    pikb = Path(cwd) / _PIKB_DIR
    pikb.mkdir(parents=True, exist_ok=True)
    return str(pikb / _LOG_FILE)


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def append(cwd: str, event: str, **fields: Any) -> None:
    """Append one log line. Each record has: ts, session, event, plus any extra fields.

    None values are filtered out for cleaner output.
    """
    record = {"ts": _now(), "session": _SESSION_ID, "event": event}
    record.update(fields)
    record = {k: v for k, v in record.items() if v is not None}

    log_path = _log_path(cwd)
    with open(log_path, "a", encoding="utf-8") as f:
        f.write(json.dumps(record, ensure_ascii=False, default=str) + "\n")


def read_all_sessions(cwd: str) -> List[Dict[str, Any]]:
    """Read all log lines from the log file regardless of session."""
    log_path = _resolve_log_path(cwd)
    if not log_path.is_file():
        return []
    records: List[Dict[str, Any]] = []
    with open(log_path, "r", encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            try:
                records.append(json.loads(line))
            except json.JSONDecodeError:
                # Skip malformed / partial lines written by a crashed process.
                continue
    return records


def read_session(cwd: str) -> List[Dict[str, Any]]:
    """Read all log lines for the current session (matching _SESSION_ID)."""
    return [r for r in read_all_sessions(cwd) if r.get("session") == _SESSION_ID]


def summarize(cwd: str) -> Dict[str, int]:
    """Return event counts for current session:
    {pitfall_matches: int, auto_writes: int, drafts: int, errors_logged: int}
    """
    counts = {
        "pitfall_matches": 0,
        "auto_writes": 0,
        "drafts": 0,
        "errors_logged": 0,
    }
    for rec in read_session(cwd):
        event = rec.get("event")
        if event in ("after_edit", "after_shell"):
            # Count individual matches, not events.
            counts["pitfall_matches"] += len(rec.get("matches") or [])
        elif event == "auto_maintain":
            counts["auto_writes"] += 1
        elif event == "draft":
            counts["drafts"] += 1
        elif event == "after_error":
            counts["errors_logged"] += 1
    return counts
