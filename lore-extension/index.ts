/**
 * lore — pi Extension
 *
 * KB status checks + /lore commands + passive monitoring.
 * Runtime events via bin/lore-event; legacy scripts for /lore commands.
 *
 * NOTE: Persistent setWidget disabled — multiple belowEditor widgets
 * may trigger pi editor autocomplete crash. Re-enable when resolved.
 */

import type { ExtensionAPI } from "@earendil-works/pi-coding-agent";
import { execSync } from "node:child_process";
import { existsSync, readFileSync } from "node:fs";
import { homedir } from "node:os";
import { join } from "node:path";

const SCRIPT_DIR = join(homedir(), ".agents", "skills", "lore", "scripts");
const WIDGET_ID = "lore-status";
const REFRESH_INTERVAL = 5;

interface LoreEventResult {
  ok?: boolean;
  event?: string;
  cwd?: string;
  status?: string;
  context_path?: string | null;
  additional_context?: string;
  warnings?: string[];
  env?: Record<string, string>;
  matches?: Array<{ id: string; title: string; difficulty: number }>;
}

interface KbStatus {
  healthy: boolean;
  repos: number;
  age: number | null;
  issues: string[];
  hasKB: boolean;
}
let cached: KbStatus | null = null;
let turnsSinceRefresh = 0;

function loreRoot(): string | null {
  const cands = [
    process.env.LORE_ROOT,
    join(homedir(), ".agents", "skills", "lore"),
  ].filter(Boolean) as string[];
  for (const c of cands) {
    if (existsSync(join(c, "bin", "lore-event"))) return c;
    if (existsSync(join(c, "runtime", "lore_runtime", "cli.py"))) return c;
  }
  return null;
}

function shellQuote(s: string): string {
  return `"${s.replace(/\\/g, "\\\\").replace(/"/g, '\\"')}"`;
}

function runLoreEvent(
  event: string,
  opts: { cwd?: string; path?: string; cmd?: string } = {},
): LoreEventResult | null {
  const root = loreRoot();
  if (!root) return null;

  const parts = [event];
  if (opts.cwd) parts.push("--cwd", opts.cwd);
  if (opts.path) parts.push("--path", opts.path);
  if (opts.cmd) parts.push("--cmd", opts.cmd);
  const args = parts.map(shellQuote).join(" ");

  const bin = join(root, "bin", "lore-event");
  const cmd = existsSync(bin)
    ? `${shellQuote(bin)} ${args}`
    : `PYTHONPATH=${shellQuote(join(root, "runtime"))} python3 -m lore_runtime ${args}`;

  try {
    const output = execSync(cmd, {
      encoding: "utf-8",
      timeout: 5000,
      cwd: opts.cwd || process.cwd(),
    });
    return parseJson(output.trim());
  } catch {
    return null;
  }
}

function hasScript(name: string): boolean {
  return existsSync(join(SCRIPT_DIR, name));
}

function runScript(name: string, args: string[] = []): { ok: boolean; output: string } {
  if (!hasScript(name)) return { ok: false, output: `${name} not found` };
  try {
    const output = execSync(
      `bash "${join(SCRIPT_DIR, name)}" ${args.join(" ")} 2>&1`,
      { encoding: "utf-8", timeout: 5000, cwd: process.cwd() },
    );
    return { ok: true, output: output.trim() };
  } catch {
    return { ok: false, output: "" };
  }
}

function kbOk(output: string): boolean {
  return output.includes("all good") || output.includes("all fresh");
}

function parseJson(output: string): any | null {
  try { return JSON.parse(output); } catch { return null; }
}

function refreshStatus(cwd?: string): KbStatus {
  const workCwd = cwd || process.cwd();
  const result = runLoreEvent("health", { cwd: workCwd });

  if (result) {
    const hasKB = result.status !== "missing" || !!result.context_path;
    return {
      healthy: result.status === "healthy",
      repos: 0,
      age: null,
      issues: result.warnings || [],
      hasKB,
    };
  }

  // Fallback: legacy on-session-start.sh
  const status = runScript("on-session-start.sh");
  if (!status.ok) return { healthy: false, repos: 0, age: null, issues: [], hasKB: false };

  const json = runScript("on-session-start.sh", ["--json"]);
  const data = parseJson(json.output);

  if (data && data.warnings !== undefined) {
    return {
      healthy: data.healthy,
      repos: 0,
      age: null,
      issues: data.warnings?.map((w: any) => w.detail) || [],
      hasKB: data.has_pikb,
    };
  }

  const lines = status.output.split("\n").filter(l => l.trim());
  const hasKB = !status.output.includes("not found");
  const healthy = kbOk(status.output);
  const warningLines = lines.filter(l => l.includes("⚠"));

  return {
    healthy,
    repos: 0,
    age: null,
    issues: warningLines.map(l => l.replace(/^\s*⚠\s*/, "").trim()),
    hasKB,
  };
}

// ── Widget (disabled — pi editor autocomplete conflict with multiple belowEditor widgets) ──
// Re-enable when pi-tui resolves: call _updateWidget(ctx) on session_start + turn_end

function _renderLine(kb: KbStatus): string {
  if (!kb.hasKB) return "  lore  —";
  if (kb.healthy) return "  lore  ✓  healthy";
  const issue = kb.issues[0] || "needs attention";
  const short = issue.length > 40 ? issue.slice(0, 37) + "..." : issue;
  return `  lore  ⚠  ${short}`;
}

function _updateWidget(ctx: { ui: { setWidget: (id: string, content: any, opts?: any) => void } }) {
  if (!cached) cached = refreshStatus();
  ctx.ui.setWidget(WIDGET_ID, [_renderLine(cached)], { placement: "belowEditor" });
}

// ── extension ──

export default function (pi: ExtensionAPI) {
  // ── /lore commands ──

  pi.registerCommand("lore", {
    description: "Check knowledge base status",
    async handler(_args, ctx) {
      cached = refreshStatus(ctx.cwd);
      if (!cached.hasKB) {
        ctx.ui.notify("[lore] No knowledge base — run /skill:lore 创建知识库", "info");
      } else if (cached.healthy) {
        ctx.ui.notify("[lore] ✓ KB healthy", "info");
      } else {
        ctx.ui.notify(`[lore] ⚠ ${cached.issues.length} issue(s) — run /lore-detail`, "warn");
      }
    },
  });

  pi.registerCommand("lore-detail", {
    description: "Show full knowledge base status",
    async handler(_args, ctx) {
      const cwd = ctx.cwd || process.cwd();
      const result = runLoreEvent("health", { cwd });
      if (result) {
        const lines = result.warnings?.length
          ? result.warnings.map(w => `⚠ ${w}`)
          : [`status: ${result.status}`];
        ctx.ui.notify(lines.join("\n"), result.status === "healthy" ? "info" : "warn");
      } else {
        const status = runScript("on-session-start.sh");
        if (status.ok) {
          ctx.ui.notify(status.output, kbOk(status.output) ? "info" : "warn");
        } else {
          ctx.ui.notify("[lore] No knowledge base found. Run /skill:lore 创建知识库", "info");
        }
      }
    },
  });

  pi.registerCommand("lore-audit", {
    description: "Audit knowledge base quality",
    async handler(_args, ctx) {
      ctx.ui.notify("[lore] Running audit...", "info");
      const result = runScript("audit-kb.sh");
      if (result.ok) {
        ctx.ui.notify(result.output, "info");
      } else {
        ctx.ui.notify("[lore] audit failed — run manually: ./scripts/audit-kb.sh", "warn");
      }
    },
  });

  pi.registerCommand("lore-search", {
    description: "Search knowledge base. Usage: /lore-search <keyword>",
    async handler(args, ctx) {
      const keyword = args.trim();
      if (!keyword) {
        ctx.ui.notify("[lore] Usage: /lore-search <keyword>", "info");
        return;
      }
      const result = runScript("quick-ref.sh", [keyword]);
      if (result.ok) {
        ctx.ui.notify(result.output.slice(0, 500), "info");
      } else {
        ctx.ui.notify("[lore] Search failed", "warn");
      }
    },
  });

  // ── Session start ──

  pi.on("session_start", async (_event, ctx) => {
    const cwd = ctx.cwd || process.cwd();
    const result = runLoreEvent("session_start", { cwd });

    if (result?.additional_context) {
      pi.sendMessage(
        { customType: "lore-kb-context", content: result.additional_context, display: false },
        { triggerTurn: false },
      );
    }

    if (result?.env?.LORE_LOADED === "1") {
      ctx.ui.notify("📚 lore loaded", "info");
      ctx.ui.setStatus("lore", "📚 l");
    } else {
      ctx.ui.setStatus("lore", undefined);
    }

    cached = refreshStatus(cwd);
    if (cached.hasKB && cached.issues.length > 0) {
      ctx.ui.notify(`[lore] ⚠ ${cached.issues[0]}`, "warn");
    }
  });

  // ── L2: Triggers matching (via lore-event) ──

  let pendingPitfallContext = "";
  const matchedPitfallIds = new Set<string>();
  const matchedPitfallTitles = new Set<string>();

  pi.on("tool_call", async (event, ctx) => {
    const cwd = ctx.cwd || process.cwd();
    const path = event.input?.path as string | undefined;
    const cmd = event.toolName === "bash" ? (event.input?.command as string | undefined) : undefined;
    if (!path && !cmd) return;

    const result = path
      ? runLoreEvent("after_edit", { cwd, path, cmd })
      : runLoreEvent("after_shell", { cwd, cmd: cmd! });

    if (!result?.matches?.length) return;

    for (const m of result.matches) {
      matchedPitfallIds.add(m.id);
      if (m.title) matchedPitfallTitles.add(m.title);
    }
    const ctxBlock = result.additional_context || "";
    if (ctxBlock) {
      pendingPitfallContext = pendingPitfallContext
        ? `${pendingPitfallContext}\n\n${ctxBlock}`
        : ctxBlock;
    }
    ctx.ui.setStatus("lore", `📚 l ⚠`);
    ctx.ui.notify(
      `[lore] ⚠ PITFALLS #${[...matchedPitfallIds].join(",#")}: ${[...matchedPitfallTitles].join("; ")}`,
      "warn",
    );
  });

  pi.on("before_agent_start", async () => {
    if (!pendingPitfallContext && matchedPitfallIds.size === 0) return;
    const content = pendingPitfallContext;
    pendingPitfallContext = "";
    matchedPitfallIds.clear();
    matchedPitfallTitles.clear();
    return {
      message: {
        customType: "lore-pitfalls-warning",
        content,
        display: false,
      },
    };
  });

  // ── Turn end: staleness check ──

  pi.on("turn_end", async (_event, ctx) => {
    turnsSinceRefresh++;
    if (turnsSinceRefresh < REFRESH_INTERVAL) return;
    turnsSinceRefresh = 0;

    const cwd = ctx.cwd || process.cwd();
    cached = refreshStatus(cwd);
    if (cached.hasKB && cached.issues.length > 0) {
      ctx.ui.notify(`[lore] ⚠ ${cached.issues.length} issue(s) — run /lore-detail`, "warn");
    }

    const logFile = join(cwd, ".pi", "kb", ".error-log.jsonl");
    if (existsSync(logFile)) {
      const count = readFileSync(logFile, "utf-8").split("\n").filter(Boolean).length;
      if (count > 0) {
        ctx.ui.notify(`[lore] 📋 ${count} errors in log — /skill:lore 检查是否需要更新 PITFALLS`, "info");
      }
    }

    // ── Wave 2: session_end summary every REFRESH_INTERVAL turns ──
    const sessionEndResult = runLoreEvent("session_end", { cwd });
    if (sessionEndResult?.additional_context) {
      pi.sendMessage(
        { customType: "lore-session-summary", content: sessionEndResult.additional_context, display: false },
        { triggerTurn: false },
      );
    }
  });

  // ── Tool end: detect new repo ──

  pi.on("tool_execution_end", async (event, ctx) => {
    if (event.isError) {
      const cwd = ctx.cwd || process.cwd();
      const logDir = join(cwd, ".pi", "kb");
      const logFile = join(logDir, ".error-log.jsonl");
      try {
        if (existsSync(logDir)) {
          const entry = JSON.stringify({
            time: new Date().toISOString(),
            tool: event.toolName,
            error: String((event as any).result?.content ?? "unknown").slice(0, 200),
          });
          const { appendFileSync } = await import("node:fs");
          appendFileSync(logFile, entry + "\n");
          const count = existsSync(logFile) ? readFileSync(logFile, "utf-8").split("\n").filter(Boolean).length : 0;
          if (count > 0 && count % 5 === 0) {
            ctx.ui.notify(`[lore] ${count} errors logged — any worth recording as PITFALLS?`, "info");
          }
        }
      } catch { /* ignore */ }

      // ── Wave 2: after_error PITFALLS matching ──
      const errorMsg = String((event as any).result?.content ?? event.toolName ?? "unknown");
      const errorResult = runLoreEvent("after_error", { cwd, cmd: errorMsg });
      if (errorResult?.additional_context) {
        pendingPitfallContext = pendingPitfallContext
          ? `${pendingPitfallContext}\n\n${errorResult.additional_context}`
          : errorResult.additional_context;
      }
      if (errorResult?.matches?.length) {
        for (const m of errorResult.matches) {
          matchedPitfallIds.add(m.id);
          if (m.title) matchedPitfallTitles.add(m.title);
        }
        ctx.ui.setStatus("lore", "📚 l ⚠");
        ctx.ui.notify(
          `[lore] ⚠ error matched PITFALLS #${[...matchedPitfallIds].join(",#")}`,
          "warn",
        );
      }
    }

    const toolName = event.toolName;
    const cmd = String(event.input?.command || "");
    const isCloneOrInit =
      toolName === "bash" &&
      /(git\s+clone|git\s+init|mkdir\s+-p.*\/)|create\s+directory/i.test(cmd);

    if (!isCloneOrInit || !hasScript("scan-workspace.sh")) return;

    setTimeout(() => {
      const scan = runScript("scan-workspace.sh");
      if (!scan.ok) return;
      const data = parseJson(scan.output);
      const uncovered = data?.repos?.filter((r: any) => !r.has_context_md) || [];
      if (uncovered.length > 0) {
        ctx.ui.notify(
          `[lore] ${uncovered.length} new repo(s) without CONTEXT.md — /skill:lore 创建知识库`,
          "info",
        );
      }
    }, 2000);
  });
}
