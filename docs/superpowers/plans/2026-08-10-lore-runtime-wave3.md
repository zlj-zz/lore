# Lore Runtime Wave 3 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development

**Goal:** Add hotspot-triggered KB loading, CODEOWNERS ownership fields, and wikilink cross-reference validation.

**Architecture:** Three incremental features in dependency order: (1) Owner/Last-verified field parsing + per-entry age, (2) CONTEXT.md hotspot matching with wikilink resolution, (3) cross-reference validation. Runtime stays read-only — no auto-fix.

**Tech Stack:** Python 3 (stdlib), Bash

---

## Task 1: Feature 2 — Owner/Last-verified field parsing

**Files:**
- Modify: `runtime/lore_runtime/pitfalls.py` — `match()` returns owner/last_verified
- Modify: `runtime/lore_runtime/health.py` — per-entry age = max(Last verified, file.mtime)
- Modify: `runtime/lore_runtime/maintenance.py` — staleness report includes owner
- Modify: `runtime/tests/test_events.py` — test owner field in match results

**Steps:**

- [ ] Parse Owner/Last-verified in pitfalls.match() using existing _extract_field()
- [ ] Add owner, last_verified to match() return dict
- [ ] Update health.py: per-entry age = max(parse_date(Last verified), file_mtime)
- [ ] Update maintenance.py: include owner in staleness issue detail
- [ ] Add test: test_pitfalls_parses_owner_fields
- [ ] All 28 existing tests still pass
- [ ] Commit

---

## Task 2: Feature 2 — Templates update

**Files:**
- Modify: `templates/PITFALLS.md` — add Owner/Last-verified fields
- Modify: `templates/CONVENTIONS.md` — add Owner/Last-verified fields
- Modify: `templates/MAP.md` — add Owner column to table

**Steps:**

- [ ] Update all 3 templates
- [ ] Commit

---

## Task 3: Feature 1 — CONTEXT.md parser extraction

**Files:**
- Modify: `runtime/lore_runtime/context.py` — extract parse_context(), add match_hotspots()

**Steps:**

- [ ] Refactor build_session_additional_context() to use shared parse_context()
- [ ] parse_context() returns {desc, entry_points, hotspots[]}
- [ ] match_hotspots(cwd, path) returns matched hotspots
- [ ] Add tests: test_parse_context, test_match_hotspots
- [ ] Commit

---

## Task 4: Feature 1 — Session truncation + hotspot overlay

**Files:**
- Modify: `runtime/lore_runtime/events.py` — session_start 500-char truncation, after_edit hotspot overlay
- Modify: `runtime/lore_runtime/types.py` — LORE_HOTSPOT_LOADING default

**Steps:**

- [ ] _session_start_event: truncate CONTEXT.md to 500 chars
- [ ] _pitfalls_event: after PITFALLS match, call match_hotspots(), merge results
- [ ] Dedup: skip wikilinks already matched as PITFALLS
- [ ] Feature flag via env var LORE_HOTSPOT_LOADING
- [ ] Add tests
- [ ] Commit

---

## Task 5: Feature 3 — Wikilink resolver

**Files:**
- Modify: `runtime/lore_runtime/discover.py` — resolve_wikilink(), check_crossrefs()

**Steps:**

- [ ] resolve_wikilink(link, cwd) → {resolved, anchor, error}
- [ ] Parse [[FILE#anchor]] format, resolve file path, find anchor in target
- [ ] check_crossrefs(cwd) → scan all KB .md files, verify all wikilinks
- [ ] Add tests
- [ ] Commit

---

## Task 6: Feature 3 — session_end crossref integration

**Files:**
- Modify: `runtime/lore_runtime/events.py` — _session_end_event: crossref check
- Modify: `runtime/lore_runtime/maintenance.py` — call check_crossrefs()

**Steps:**

- [ ] _session_end_event: run check_crossrefs(), append results to additional_context
- [ ] maintenance.py: optionally expose crossref check utility
- [ ] Add integration test
- [ ] Commit

---

## Task 7: audit-kb.sh — loose ref detection

**Files:**
- Modify: `scripts/audit-kb.sh`

**Steps:**

- [ ] Add wikilink check alongside existing Markdown link check
- [ ] Flag loose refs: "N loose references found, consider converting to wikilinks"
- [ ] Commit

---

## Task 8: Final verification

- [ ] Run full test suite: 28 + new tests all pass
- [ ] Smoke test: session_start with truncation, after_edit with hotspot match, session_end with crossref
- [ ] Verify backward compat: old KB without Owner fields still works
- [ ] Commit any remaining changes
