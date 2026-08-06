from pathlib import Path

from lore_runtime.types import empty_result, STATUS_HEALTHY, STATUS_DEGRADED, STATUS_MISSING
from lore_runtime import health as health_mod
from lore_runtime import discover


def handle(event: str, cwd: str, path: str = None, cmd: str = None) -> dict:
    cwd = str(Path(cwd).resolve())
    if event == "health":
        return _health_event(cwd)
    r = empty_result(event, cwd)
    r["ok"] = False
    r["warnings"] = ["unknown event: %s" % event]
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
