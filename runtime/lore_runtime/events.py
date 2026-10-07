import os
import re
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

LORE_CONTEXT_MAX_CHARS = 500
_HOTSPOT_LOADING = os.environ.get("LORE_HOTSPOT_LOADING") == "1"


def handle(
    event: str, cwd: str, path: str = None, cmd: str = None, error: str = None
) -> dict:
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

    # Wave 3: Hotspot-triggered loading (opt-in via LORE_HOTSPOT_LOADING=1).
    if _HOTSPOT_LOADING and path:
        hotspots = context_mod.match_hotspots(cwd, path)
        if hotspots:
            hotspot_lines = []
            for h in hotspots:
                hotspot_lines.append(
                    "[lore] 📍 %s — %s" % (h["pattern"], h.get("why", ""))
                )
                for ref in h.get("refs", []):
                    # Dedup: if a hotspot ref is a PITFALLS already matched
                    # above, show a link but don't re-inject the body.
                    pitfall_id = None
                    m = re.match(r"PITFALLS?#?(\d+)", ref)
                    if m:
                        pitfall_id = m.group(1)
                    if pitfall_id and any(
                        match["id"] == pitfall_id for match in matches
                    ):
                        hotspot_lines.append(
                            "  → PITFALLS #%s (injected above)" % pitfall_id
                        )
                    else:
                        hotspot_lines.append("  → %s" % ref)
            if hotspot_lines:
                ctx = "\n".join(hotspot_lines)
                if r["additional_context"]:
                    r["additional_context"] += "\n\n" + ctx
                else:
                    r["additional_context"] = ctx
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
    if text:
        # Truncate so the CONTEXT.md portion stays compact: keep RULES + marker
        # + first LORE_CONTEXT_MAX_CHARS characters of the injected context.
        text = text[
            : len(context_mod.RULES) + len("📚 lore loaded") + LORE_CONTEXT_MAX_CHARS
        ]
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
    logger_mod.append(cwd, "after_error", error=error_msg[:200], matches=len(matches))
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
            parts.append(
                "\n[lore] ✏️ %d auto-maintenance action(s) needed" % auto_count
            )
        if draft_count:
            parts.append(
                "\n[lore] 📝 %d draft(s) created in .pikb/.lore-drafts/ — please review"
                % draft_count
            )

    r["additional_context"] = "\n".join(parts)

    logger_mod.append(
        cwd,
        "session_end",
        summary="%d matches, %d auto, %d drafts"
        % (
            summary.get("pitfall_matches", 0),
            summary.get("auto_writes", 0),
            summary.get("drafts", 0),
        ),
    )

    # Wave 3: cross-reference validation
    try:
        crossrefs = discover.check_crossrefs(cwd)
        if crossrefs:
            broken = [c for c in crossrefs if c["status"] != "ok"]
            ok_count = len(crossrefs) - len(broken)
            cr_lines = ["\n[lore] 🔗 cross-reference check:"]
            for c in broken:
                cr_lines.append(
                    "  ❌ %s:%d → %s — %s"
                    % (c["source_file"], c["line"], c["wikilink"], c.get("detail", ""))
                )
            if ok_count:
                cr_lines.append("  ✅ %d references OK" % ok_count)
            r["additional_context"] += "\n".join(cr_lines)
    except Exception:
        pass

    return r
