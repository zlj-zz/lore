# Adapter matrix

Cross-agent KB behavior is owned by **`lore_runtime`** (Python, stdlib-only under `runtime/`).  
Each agent keeps a **thin adapter** that maps platform hooks to the shared CLI:

```bash
bin/lore-event <event> [--cwd DIR] [--path FILE] [--cmd STR]
# equivalent: PYTHONPATH=runtime python3 -m lore_runtime ...
```

Adapters **soft-fail**: missing runtime or parse errors emit `{}` / no-op; process exit code is always `0` so agent sessions are never blocked.

Shared helper: `adapters/common.sh` (`lore_root`, `lore_event`).

## Capability matrix

| Capability | Runtime event | pi | Claude Code | Cursor | Status |
|------------|---------------|----|-------------|--------|--------|
| Session CONTEXT + MAP bootstrap | `session_start` | `lore-extension/index.ts` → `bin/lore-event session_start` → `sendMessage` + `📚 lore loaded` notify | Rules in `CLAUDE.md` ask the model to read `.pi/kb/CONTEXT.md` (no runtime bootstrap hook in v1) | `cursor-hooks/session-start.sh` → `lore_event session_start` → `{additional_context, env}` | ✅ |
| PITFALLS match on file edit | `after_edit` | `tool_call` with path → `after_edit` → notify + queue for `before_agent_start` | — (optional follow-up; not wired in v1) | `cursor-hooks/post-tool-use.sh` when tool input has a path | ✅ |
| PITFALLS match on shell command | `after_shell` | `tool_call` with command → `after_shell` | — | `post-tool-use.sh` for Shell/Bash tools | ✅ |
| KB health check (throttled) | `health` | `turn_end`, status refresh, `/lore-detail` → `health` (fallback: `on-session-start.sh`) | `install.sh` PostToolUse hook → `lore-event health` every 300s | `post-tool-use.sh` → `health` every 300s (`/tmp/.lore-cursor-check`) | ✅ |
| PITFALLS match on tool errors | `after_error` | `tool_execution_end` error → `after_error` → notify + inject | `PostToolUse` exit code ≠ 0 → `after_error` | `post-tool-use.sh` → `after_error` | ✅ |
| Session-end staleness + summary | `session_end` | `turn_end` (every 5 turns) → `session_end` → hidden context | `Stop` hook → `session_end` → summary print | `session-start.sh` catch-up (no native session-end hook) | ✅ |

## Script facades

Legacy entry points delegate to the same runtime events:

| Script | Runtime event | Notes |
|--------|---------------|-------|
| `scripts/on-session-start.sh` | `health` | Human text or legacy JSON; exit `1` when degraded (unlike CLI, which always exits `0`) |
| `scripts/match-trigger.sh` | `after_edit` / `after_shell` | Prints `additional_context` title lines for existing callers |

## Canonical JSON (stdout)

All events return one JSON object on stdout (debug on stderr only). Key fields:

- `ok`, `event`, `cwd`, `status` (`healthy` \| `degraded` \| `missing`)
- `additional_context` — text for the model
- `env` — e.g. `LORE_LOADED`, `LORE_CONTEXT`, `LORE_CWD` (`session_start` only)
- `matches` — pitfall hits (`after_edit` / `after_shell`)
- `warnings` — health notes

See `docs/superpowers/specs/2026-08-06-lore-runtime-adapters-design.md` for the full contract.

## In runtime (wave 2)

- `after_error` — PITFALLS matching on tool execution errors
- `session_end` — staleness detection + session summary + maintenance proposals
- `maintenance.py` — staleness check, novel error detection, proposal generation
- `logger.py` — session logging to `.pikb/.lore-session-log.jsonl`
- `lore-log.sh` — log viewer CLI (`--summary`, `--all`, `--last`, `--since`)

## Not in runtime (wave 3?)

- `scan-workspace.sh`, `graph.sh`, `audit-kb.sh` — still standalone scripts
- Cursor `sessionStart` `additional_context` platform race — keep `.cursor/rules/lore.mdc` fallback
- Full auto-maintenance (runtime writes KB files directly without model involvement)
