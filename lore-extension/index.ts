/**
 * lore — pi Extension
 *
 * Shows KB status on session start and provides /lore commands.
 *
 * Reads from ~/.agents/skills/lore/scripts/ for all functionality.
 */

import type { ExtensionAPI } from "@earendil-works/pi-coding-agent";
import { execSync } from "node:child_process";
import { existsSync } from "node:fs";
import { homedir } from "node:os";
import { join } from "node:path";

const SCRIPT_DIR = join(homedir(), ".agents", "skills", "lore", "scripts");

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
  } catch (e: any) {
    const stderr = e.stderr?.toString() || e.stdout?.toString() || "";
    const lines = stderr.split("\n").filter((l: string) => l.trim());
    // extract the meaningful part — skip stack traces
    const msg = lines.slice(0, 5).join("\n");
    return { ok: false, output: msg || `${name} failed` };
  }
}

function kbOk(output: string): boolean {
  return output.includes("all good") || output.includes("all fresh");
}

export default function (pi: ExtensionAPI) {
  // ── /lore command ──

  pi.registerCommand({
    name: "lore",
    description: "Check knowledge base status",
    async execute(_args, ctx) {
      const status = runScript("on-session-start.sh");
      if (!status.ok) {
        ctx.ui.notify("[lore] extension not available — see ~/.agents/skills/lore", "warn");
        return;
      }
      if (kbOk(status.output)) {
        ctx.ui.notify("[lore] ✓ KB healthy — run /lore-detail for more", "info");
      } else {
        ctx.ui.notify("[lore] ⚠ KB needs attention — run /lore-detail", "warn");
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

  // ── Session start check ──

  pi.on("session_start", async (_event, ctx) => {
    if (!hasScript("on-session-start.sh")) return;

    const status = runScript("on-session-start.sh");

    if (!status.ok) {
      // non-zero exit → KB not initialized or has issues
      const lines = status.output.split("\n").filter((l) => l.trim());
      const warningLine = lines.find((l) => l.includes("⚠"));
      if (warningLine) {
        ctx.ui.notify(`[lore] ${warningLine.replace(/^\s*⚠\s*/, "").trim()}`, "warn");
      }
    }
    // if KB is healthy, don't interrupt — just be quiet
  });

  // ── Passive hooks ──

  let turnCount = 0;
  const STALENESS_INTERVAL = 5; // check every 5 turns

  pi.on("turn_end", async (_event, ctx) => {
    turnCount++;
    if (turnCount % STALENESS_INTERVAL !== 0) return;
    if (!hasScript("check-staleness.sh")) return;

    // quick staleness check — only notify if there are issues
    try {
      const result = runScript("check-staleness.sh", ["--json"]);
      if (!result.ok) return;
      const data = JSON.parse(result.output);
      if (data.stale) {
        const issues = data.issues || [];
        const warnings = issues.filter((i: any) => i.severity === "warning");
        if (warnings.length > 0) {
          ctx.ui.notify(
            `[lore] ${warnings.length} KB issue(s) — run /lore-detail`,
            "warn",
          );
        }
      }
    } catch {
      // silent — script failures shouldn't interrupt the user
    }
  });

  pi.on("tool_execution_end", async (event, ctx) => {
    // detect potential new repo creation
    const toolName = event.tool?.name || "";
    const isCloneOrInit =
      toolName === "bash" &&
      event.args?.command &&
      /(git\s+clone|git\s+init|mkdir\s+-p.*\/)|(create\s+directory)/i.test(
        String(event.args.command),
      );

    if (!isCloneOrInit) return;
    if (!hasScript("scan-workspace.sh")) return;

    // debounce: wait 2s then check if a new repo appeared
    setTimeout(() => {
      try {
        const scan = runScript("scan-workspace.sh");
        if (!scan.ok) return;
        const data = JSON.parse(scan.output);
        const uncovered = data.repos?.filter((r: any) => !r.has_context_md) || [];
        if (uncovered.length > 0) {
          ctx.ui.notify(
            `[lore] ${uncovered.length} repo(s) without CONTEXT.md — consider /skill:lore 创建知识库`,
            "info",
          );
        }
      } catch {
        // silent
      }
    }, 2000);
  });
}
