# lore D3 — Shared Python Runtime + Thin Adapters

Date: 2026-08-06  
Status: approved in brainstorming (§1–§4)  
Scope: cross-agent capability parity via shared `lore_runtime`

## Problem

Lore behavior is duplicated and uneven across agents:

| Capability | pi | Claude | Cursor |
|------------|----|--------|--------|
| Session CONTEXT inject | extension (inline TS) | rules ask model to read | hooks (inline Python) + rules fallback |
| PITFALLS matching | extension (inline TS) | weak / scripts | hooks (inline Python) |
| Health check | scripts + extension | PostToolUse bash | hooks + scripts |

Changing matching or bootstrap logic requires editing multiple copies. Cursor/Claude adapters should not own domain logic.

## Goal

One **platform-agnostic Python runtime** owns discover / load / match / health / format.  
Each agent keeps a **thin adapter** that only translates stdin/stdout.

**Success criteria**

- Bootstrap, pitfalls match, and health share one JSON semantics across agents.
- Changing match/bootstrap logic requires edits only under `runtime/`.
- Existing script CLIs (`on-session-start.sh`, `match-trigger.sh`) remain usable as facades.
- Adapters never block the agent session (exit 0; soft-fail to empty payload).

## Non-goals (this design)

- New intelligence (auto-writing PITFALLS, end-of-session KB patches).
- Fixing Cursor’s `sessionStart` `additional_context` platform race (keep `env` + `.cursor/rules` fallback).
- Moving `scan-workspace` / `graph` / `audit-kb` into runtime (possible later wave).
- Statusline / slash-command UI parity beyond what adapters already can do.

## Approach chosen

Python stdlib-only package `lore_runtime` + `lore-event` CLI.  
Rejected: bash-only consolidation (hard to test/grow); TypeScript core (forces Node on Claude/Cursor hooks).

---

## §1 Architecture

```
┌─────────────────────────────────────────┐
│  lore_runtime (Python, no third-party)  │
│  discover · load · match · health · fmt │
└─────────────────┬───────────────────────┘
                  │  lore-event CLI → canonical JSON
       ┌──────────┼──────────┐
       ▼          ▼          ▼
  cursor-hooks  claude-hook  pi extension
  (bash map)    (bash map)   (spawn CLI)
```

**Boundaries**

- **Runtime:** given `cwd` and optional `path`/`cmd`, produce platform-free results.
- **Adapter:** platform JSON, timeouts, absolute hook paths, `hooks.json` merge.
- **`scripts/*.sh`:** become thin wrappers over `lore-event` where they overlap runtime (v1: session/pitfalls/health only).

**Layout**

```
runtime/
  lore_runtime/
    __init__.py
    discover.py
    context.py
    pitfalls.py
    health.py
    events.py
    cli.py
  tests/
    fixtures/mini-ws/
    test_events.py
bin/lore-event                  # optional shim → python -m lore_runtime.cli
cursor-hooks/                   # JSON mapping only
lore-extension/                 # spawn CLI; keep UI/notify in TS
scripts/                        # facades
docs/adapters.md                # capability matrix (P4)
```

Invocation (after install, skill root on disk):

```bash
python3 -m lore_runtime.cli <event> [--cwd DIR] [--path FILE] [--cmd STR]
# PYTHONPATH includes runtime/ ; or bin/lore-event sets it
```

---

## §2 Events and CLI contract

### Events (v1)

| Event | Inputs | Purpose |
|-------|--------|---------|
| `session_start` | `cwd` | Rules blurb + CONTEXT + MAP summary + health notes |
| `after_edit` | `cwd`, `path` | PITFALLS `file:` triggers |
| `after_shell` | `cwd`, `cmd` | PITFALLS `cmd:` triggers |
| `health` | `cwd` | Health only (throttled hooks) |

### Canonical stdout JSON

```json
{
  "ok": true,
  "event": "session_start",
  "cwd": "/path",
  "status": "healthy|degraded|missing",
  "context_path": "/path/.pi/kb/CONTEXT.md",
  "additional_context": "text for the model",
  "warnings": [],
  "env": {
    "LORE_LOADED": "1",
    "LORE_CONTEXT": "/path/.pi/kb/CONTEXT.md",
    "LORE_CWD": "/path"
  },
  "matches": [
    { "id": "1", "title": "Auth middleware order", "difficulty": 3 }
  ]
}
```

**Rules**

- Process exit code always `0` (do not block agents). Logical failure → `ok: false` and `warnings`.
- `additional_context` may be `""`; adapters decide whether to omit platform fields.
- `matches` is meaningful for `after_edit` / `after_shell`; empty array for `session_start` / `health` is fine.
- stdout is **pure JSON**; debug only on stderr.

### Script compatibility

- `scripts/on-session-start.sh` and `scripts/match-trigger.sh` keep external behavior as far as practical; internals call runtime.
- Prefer stable human-readable stdout for match-trigger (title lines) for existing callers; `--json` optional later if needed.

---

## §3 Adapters and migration

### Adapter mapping

| Agent | Triggers | Runtime call | Platform write-back |
|-------|----------|--------------|---------------------|
| Cursor | `sessionStart`, `postToolUse` | `session_start` or `after_edit` / `after_shell` / `health` by tool | `{additional_context, env}` or `{}`; absolute hook paths |
| Claude | `PostToolUse` (throttled) | `health` (v1); edit match optional follow-up | Non-blocking text in hook output |
| pi | `session_start`, `tool_call`, `turn_end` | same CLI | `sendMessage` / notify; delete duplicated PITFALLS parsers in TS |

Shared optional helper: `adapters/common.sh` resolves skill root and runs `lore-event`.

### Migration order

1. Land `runtime/` + CLI + unit tests (green).
2. Point Cursor hooks at CLI only (remove embedded domain Python).
3. Turn `on-session-start.sh` / `match-trigger.sh` into facades.
4. Shorten Claude `install.sh` hook command to `lore-event health`.
5. pi extension: bootstrap + pitfalls via CLI; keep UI in TS.
6. Docs: `docs/adapters.md` + README Agents notes.

### Explicitly not moved

- `install.sh` symlink / hooks.json merge (distribution).
- `scan-workspace` / `graph` / `audit-kb` (wave 2).
- Policy for copying `templates/cursor-lore.mdc` (already exists).

### Failure behavior

- Missing runtime → adapter emits `{}` / no-op; session continues.
- Cursor timeouts stay 8–10s; CLI internal work budgets shorter.
- During dual-write, **runtime is source of truth**; old scripts are facades only.

---

## §4 Tests and rollout

### Fixtures

`runtime/tests/fixtures/mini-ws/`:

- `.pikb/MAP.md`, `CONVENTIONS.md`, `PITFALLS.md` (with `file:` / `cmd:` triggers)
- `app/.pi/kb/CONTEXT.md` (references `@workspace`)

### Unit tests (stdlib `unittest`, no pytest required)

- `session_start`: status not `missing`; context contains CONTEXT title and `📚`
- `after_edit`: hit and miss on path
- `after_shell`: hit on cmd
- `health`: missing `.pikb` → `missing`
- CLI: stdout `json.loads` cleanly

### Adapter smoke

- Fake Cursor `sessionStart` stdin → hook → has `additional_context` and `env`
- `match-trigger.sh` facade on fixture path prints pitfall title

### Rollout checklist

| Step | Work | Done when |
|------|------|-----------|
| P0 | `runtime/` + CLI + unit tests | `python3 -m unittest` green |
| P1 | Cursor hooks → CLI + reinstall merge | `install.sh status --to cursor` + smoke |
| P2 | Script facades | Old invocation paths still work |
| P3 | Claude hook + pi extension → CLI | No duplicated PITFALLS parse logic |
| P4 | `docs/adapters.md` + README | Matrix documents runtime ownership |

### Rollback

Point adapters back at previous script bodies if needed; runtime lives under the skill checkout (no global site-packages install required).

---

## Open decisions (resolved in brainstorming)

- Language: Python stdlib only.
- Parity depth: D3 (shared runtime), not D1-doc-only or D2-commands-only.
- Wave-1 events only: `session_start`, `after_edit`, `after_shell`, `health`.

## Next step

After user reviews this spec: write an implementation plan (`writing-plans`), then execute P0→P4.
