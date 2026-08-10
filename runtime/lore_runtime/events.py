from pathlib import Path

from lore_runtime.types import empty_result, session_end_summary_template
from lore_runtime import health as health_mod
from lore_runtime import discover
from lore_runtime import context as context_mod
from lore_runtime import pitfalls as pitfalls_mod
from lore_runtime import logger as logger_mod

try:
    from lore_runtime import maintenance as maintenance_mod
except ImportError:
    maintenance_mod = None


def handle(event: str, cwd: str, path: str = None, cmd: str = None, error: str = None) -> dict:
    cwd = str(Path(cwd).resolve())
    if event == "health":
        return _health_event(cwd)
    if event == "session_start":
        return _session_start_event(cwd)
    if event in ("after_edit", "after_shell"):
        return _pitfalls_event(event, cwd, path or "", cmd or "")
    if event == "after_error":
        return _after_error_event(cwd, error or "")
    if event == "session_end":
        return _session_end_event(cwd)
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
        logger_mod.append(cwd, event, path=path, cmd=cmd, matches=matches)
    return r


def _format_health_notes(status: str, warnings: list) -> str:
    if status == "healthy" or not warnings:
        return ""
    filtered = [w for w in warnings if "not found" not in w]
    if not filtered:
        return ""
    return "[lore] health:\n" + "\n".join(filtered)[:1200]


def _session_start_event(cwd: str) -> dict:
    r = empty_result("session_start", cwd)
    h = health_mod.check(cwd)
    text, ctx_path, ctx_warnings = context_mod.build_session_additional_context(cwd)
    health_notes = _format_health_notes(h["status"], h["warnings"])
    if health_notes:
        text = (text + "\n\n" + health_notes) if text else health_notes
    r["additional_context"] = text
    r["context_path"] = ctx_path
    r["status"] = h["status"]
    r["warnings"] = h["warnings"] + ctx_warnings
    r["env"] = {
        "LORE_LOADED": "1" if ctx_path else "0",
        "LORE_CONTEXT": ctx_path or "",
        "LORE_CWD": cwd,
    }
    logger_mod.append(cwd, "session_start", status=h["status"])
    return r


def _health_event(cwd: str) -> dict:
    r = empty_result("health", cwd)
    h = health_mod.check(cwd)
    r["status"] = h["status"]
    r["warnings"] = h["warnings"]
    r["ok_items"] = h["ok_items"]
    ctx = discover.find_context(cwd)
    r["context_path"] = str(ctx) if ctx else None
    r["env"] = {
        "LORE_LOADED": "1" if ctx else "0",
        "LORE_CONTEXT": str(ctx) if ctx else "",
        "LORE_CWD": cwd,
    }
    logger_mod.append(cwd, "health", status=h["status"])
    return r


def _after_error_event(cwd: str, error_msg: str) -> dict:
    r = empty_result("after_error", cwd)
    matches = pitfalls_mod.match_error(cwd, error_msg)
    r["matches"] = matches
    if matches:
        r["additional_context"] = pitfalls_mod.format_additional_context(
            cwd, "", matches
        )
    else:
        if maintenance_mod is not None:
            novel = maintenance_mod.detect_novel_error(cwd, error_msg)
            if novel:
                r["new_pattern"] = error_msg[:200]
                r["additional_context"] = (
                    "[lore] 检测到新型错误 pattern，建议追加 PITFALLS 条目:\n"
                    "  %s\n"
                    "  → create entry in .pikb/PITFALLS.md with Triggers: `cmd:...`"
                ) % error_msg[:200]
    logger_mod.append(cwd, "after_error",
                      error=error_msg[:200],
                      matches=len(matches))
    return r


def _session_end_event(cwd: str) -> dict:
    r = empty_result("session_end", cwd)
    r.update(session_end_summary_template())
    h = health_mod.check(cwd)
    r["status"] = h["status"]

    summary = logger_mod.summarize(cwd)
    r["session_summary"] = summary

    if maintenance_mod is not None:
        stale = maintenance_mod.check_staleness(cwd)
        proposals = maintenance_mod.generate_proposals(cwd, stale)
    else:
        stale = {"stale": False, "issues": []}
        proposals = []

    r["staleness"] = stale
    r["maintenance_proposals"] = proposals

    parts = []
    parts.append("[lore] session end")
    parts.append("  PITFALLS matched: %d" % summary.get("pitfall_matches", 0))
    parts.append("  auto-writes: %d" % summary.get("auto_writes", 0))
    parts.append("  drafts: %d" % summary.get("drafts", 0))

    if stale.get("stale"):
        parts.append("\n[lore] ⚠️ KB staleness detected:")
        for iss in stale.get("issues", []):
            parts.append("  - %s: %s" % (iss.get("check", ""), iss.get("detail", "")))

    if proposals:
        auto_count = sum(1 for p in proposals if p.get("type") == "auto")
        draft_count = sum(1 for p in proposals if p.get("type") == "draft")
        if auto_count:
            parts.append("\n[lore] ✏️ %d auto-maintenance action(s) needed" % auto_count)
        if draft_count:
            parts.append("\n[lore] 📝 %d draft(s) created in .pikb/.lore-drafts/ — please review" % draft_count)

    r["additional_context"] = "\n".join(parts)

    logger_mod.append(cwd, "session_end",
                      summary="%d matches, %d auto, %d drafts" % (
                          summary.get("pitfall_matches", 0),
                          summary.get("auto_writes", 0),
                          summary.get("drafts", 0)))
    return r
