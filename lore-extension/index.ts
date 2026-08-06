/**
 * lore — pi Extension
 *
 * KB status checks + /lore commands + passive monitoring.
 * Reads from ~/.agents/skills/lore/scripts/ for all functionality.
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

interface KbStatus {
  healthy: boolean;
  repos: number;
  age: number | null;
  issues: string[];
  hasKB: boolean;
}
let cached: KbStatus | null = null;
let turnsSinceRefresh = 0;

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

function refreshStatus(): KbStatus {
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
      cached = refreshStatus();
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
      const status = runScript("on-session-start.sh");
      if (status.ok) {
        ctx.ui.notify(status.output, kbOk(status.output) ? "info" : "warn");
      } else {
        ctx.ui.notify("[lore] No knowledge base found. Run /skill:lore 创建知识库", "info");
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
    // Auto-inject knowledge base content
    const cwd = ctx.cwd || process.cwd();
    const contextPath = join(cwd, ".pi", "kb", "CONTEXT.md");

    if (existsSync(contextPath)) {
      let kbContent = readFileSync(contextPath, "utf-8").slice(0, 2048);

      // If CONTEXT.md references workspace, inject MAP summary too
      if (kbContent.includes("@workspace") || kbContent.includes(".pikb")) {
        const mapPath = join(cwd, "..", ".pikb", "MAP.md");
        if (existsSync(mapPath)) {
          const mapLines = readFileSync(mapPath, "utf-8")
            .split("\n")
            .slice(0, 80)
            .join("\n");
          kbContent += `\n\n## Workspace Map (summary)\n${mapLines}`;
        }
      }

      pi.sendMessage(
        { customType: "lore-kb-context", content: `[Knowledge Base]\n\n${kbContent}`, display: false },
        { triggerTurn: false },
      );
      ctx.ui.notify("📚 lore loaded", "info");
      ctx.ui.setStatus("lore", "📚 l");
    } else {
      ctx.ui.setStatus("lore", undefined);
    }

    // Health check
    if (!hasScript("on-session-start.sh")) return;
    cached = refreshStatus();
    if (cached.hasKB && cached.issues.length > 0) {
      ctx.ui.notify(`[lore] ⚠ ${cached.issues[0]}`, "warn");
    }
  });

  // ── Turn end: staleness check ──

  pi.on("turn_end", async (_event, ctx) => {
    turnsSinceRefresh++;
    if (turnsSinceRefresh < REFRESH_INTERVAL) return;
    turnsSinceRefresh = 0;
    cached = refreshStatus();

    if (cached.hasKB && cached.issues.length > 0) {
      ctx.ui.notify(`[lore] ${cached.issues.length} issue(s) — run /lore-detail`, "warn");
    }
  });

  // ── Tool end: detect new repo ──

  pi.on("tool_execution_end", async (event, ctx) => {
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
