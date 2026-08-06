/**
 * lore — pi Extension
 *
 * Persistent KB status widget + /lore commands + passive monitoring.
 * Reads from ~/.agents/skills/lore/scripts/ for all functionality.
 */

import type { ExtensionAPI } from "@earendil-works/pi-coding-agent";
import { execSync } from "node:child_process";
import { existsSync } from "node:fs";
import { homedir } from "node:os";
import { join } from "node:path";

const SCRIPT_DIR = join(homedir(), ".agents", "skills", "lore", "scripts");
const WIDGET_ID = "lore-status";
const REFRESH_INTERVAL = 5; // turns between full refreshes

// ── cached status ──
interface KbStatus {
  healthy: boolean;
  repos: number;
  age: number | null; // days
  issues: string[];
  hasKB: boolean;
}
let cached: KbStatus | null = null;
let turnsSinceRefresh = 0;

// ── helpers ──

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
  // fast path: try on-session-start.sh
  const status = runScript("on-session-start.sh");
  if (!status.ok) return { healthy: false, repos: 0, age: null, issues: [], hasKB: false };

  // try JSON for structured data
  const json = runScript("on-session-start.sh", ["--json"]);
  const data = parseJson(json.output);

  if (data && data.warnings !== undefined) {
    return {
      healthy: data.healthy,
      repos: 0, // not in current JSON output
      age: null,
      issues: data.warnings?.map((w: any) => w.detail) || [],
      hasKB: data.has_pikb,
    };
  }

  // fallback: parse text output
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

// ── widget ──

function renderLine(kb: KbStatus): string {
  if (!kb.hasKB) return "  lore  —";
  if (kb.healthy) return "  lore  ✓  healthy";
  const issue = kb.issues[0] || "needs attention";
  const short = issue.length > 40 ? issue.slice(0, 37) + "..." : issue;
  return `  lore  ⚠  ${short}`;
}

function updateWidget(ctx: { ui: { setWidget: (id: string, content: any, opts?: any) => void } }) {
  if (!cached) cached = refreshStatus();
  const line = renderLine(cached);
  ctx.ui.setWidget(WIDGET_ID, [line], { placement: "belowEditor" });
}

// ── extension ──

export default function (pi: ExtensionAPI) {
  // ── /lore commands ──

  pi.registerCommand({
    name: "lore",
    description: "Check knowledge base status",
    async execute(_args, ctx) {
      cached = refreshStatus();
      updateWidget(ctx);
      if (!cached.hasKB) {
        ctx.ui.notify("[lore] No knowledge base — run /skill:lore 创建知识库", "info");
      } else if (cached.healthy) {
        ctx.ui.notify("[lore] ✓ KB healthy", "info");
      } else {
        ctx.ui.notify(`[lore] ⚠ ${cached.issues.length} issue(s) — run /lore-detail`, "warn");
      }
    },
  });

  pi.registerCommand({
    name: "lore-detail",
    description: "Show full knowledge base status",
    async execute(_args, ctx) {
      const status = runScript("on-session-start.sh");
      if (status.ok) {
        ctx.ui.notify(status.output, kbOk(status.output) ? "info" : "warn");
      } else {
        ctx.ui.notify("[lore] No knowledge base found. Run /skill:lore 创建知识库", "info");
      }
    },
  });

  pi.registerCommand({
    name: "lore-audit",
    description: "Audit knowledge base quality",
    async execute(_args, ctx) {
      ctx.ui.notify("[lore] Running audit...", "info");
      const result = runScript("audit-kb.sh");
      if (result.ok) {
        ctx.ui.notify(result.output, "info");
      } else {
        ctx.ui.notify("[lore] audit failed — run manually: ./scripts/audit-kb.sh", "warn");
      }
    },
  });

  pi.registerCommand({
    name: "lore-search",
    description: "Search knowledge base. Usage: /lore-search <keyword>",
    async execute(args, ctx) {
      const keyword = args.join(" ").trim();
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
    if (!hasScript("on-session-start.sh")) return;
    cached = refreshStatus();
    if (ctx.ui && typeof ctx.ui.setWidget === "function") {
      updateWidget(ctx);
    }
    if (cached.hasKB && cached.issues.length > 0) {
      ctx.ui.notify(`[lore] ⚠ ${cached.issues[0]}`, "warn");
    }
  });

  // ── Turn end: refresh widget + staleness check ──

  pi.on("turn_end", async (_event, ctx) => {
    turnsSinceRefresh++;

    if (turnsSinceRefresh >= REFRESH_INTERVAL) {
      turnsSinceRefresh = 0;
      cached = refreshStatus();
      if (ctx.ui && typeof ctx.ui.setWidget === "function") {
        updateWidget(ctx);
      }

      // notify on new issues
      if (cached.hasKB && cached.issues.length > 0) {
        ctx.ui.notify(`[lore] ${cached.issues.length} issue(s) — run /lore-detail`, "warn");
      }
    }
  });

  // ── Tool end: detect new repo ──

  pi.on("tool_execution_end", async (event, ctx) => {
    const toolName = event.tool?.name || "";
    const cmd = String(event.args?.command || "");
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
        // refresh widget after new repo detection
        cached = refreshStatus();
        if (ctx.ui && typeof ctx.ui.setWidget === "function") {
          updateWidget(ctx);
        }
      }
    }, 2000);
  });
}
