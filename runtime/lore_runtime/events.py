from pathlib import Path

from lore_runtime.types import empty_result, STATUS_HEALTHY, STATUS_DEGRADED, STATUS_MISSING
from lore_runtime import health as health_mod
from lore_runtime import discover
from lore_runtime import context as context_mod
from lore_runtime import pitfalls as pitfalls_mod


def handle(event: str, cwd: str, path: str = None, cmd: str = None) -> dict:
    cwd = str(Path(cwd).resolve())
    if event == "health":
        return _health_event(cwd)
    if event == "session_start":
        return _session_start_event(cwd)
    if event in ("after_edit", "after_shell"):
        return _pitfalls_event(event, cwd, path or "", cmd or "")
    r = empty_result(event, cwd)
    r["ok"] = False
    r["warnings"] = ["unknown event: %s" % event]
    return r


def _pitfalls_event(event: str, cwd: str, path: str, cmd: str) -> dict:
    r = empty_result(event, cwd)
    matches = pitfalls_mod.match(cwd, path=path, cmd=cmd)
    r["matches"] = matches
    if matches:
        r["additional_context"] = pitfalls_mod.format_additional_context(
            cwd, path, matches
        )
    return r


def _session_start_event(cwd: str) -> dict:
    r = empty_result("session_start", cwd)
    h = health_mod.check(cwd)
    text, ctx_path, ctx_warnings = context_mod.build_session_additional_context(cwd)
    r["additional_context"] = text
    r["context_path"] = ctx_path
    r["status"] = h["status"]
    r["warnings"] = h["warnings"] + ctx_warnings
    r["env"] = {
        "LORE_LOADED": "1" if ctx_path else "0",
        "LORE_CONTEXT": ctx_path or "",
        "LORE_CWD": cwd,
    }
    return r


def _health_event(cwd: str) -> dict:
    r = empty_result("health", cwd)
    h = health_mod.check(cwd)
    r["status"] = h["status"]
    r["warnings"] = h["warnings"]
    ctx = discover.find_context(cwd)
    r["context_path"] = str(ctx) if ctx else None
    r["env"] = {
        "LORE_LOADED": "1" if ctx else "0",
        "LORE_CONTEXT": str(ctx) if ctx else "",
        "LORE_CWD": cwd,
    }
    return r
