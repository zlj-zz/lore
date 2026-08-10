# Lore Runtime Wave 2 — 运行时智能（trigger → 真注入、自动维护）

- **Date**: 2026-08-10
- **Status**: draft
- **Dependencies**: Wave 1 `lore_runtime` (complete)

## 1. Motivation

Wave 1 建立了跨 agent 的 KB 共享运行时（检测 + 读取），但存在四个缺口：

1. **triggers 只注入标题，不拉正文** — PITFALLS 匹配时模型只看到标题和难度星级，还需要手动读文件
2. **没有日志** — 用户无法感知 lore 在会话中做了什么
3. **没有自动维护** — SKILL.md 写的「遇到新坑追加 PITFALLS」靠模型手动执行，不是自动的
4. **没有 session_end** — 缺少会话结束时的汇总、staleness 检查和维护提议

Wave 2 把这些补齐。

## 2. Goals

- PITFALLS 匹配时注入条目全文（Symptom / Root Cause / Solution）
- 全程日志：`.pikb/.lore-session-log.jsonl` 记录所有 lore 事件
- 实时通知：关键事件用户当场感知（pi notify + 三平台 additional_context）
- 分级自动维护：低风险静默写入，高风险生成 draft → review
- `session_end` 事件：汇总 + staleness + 维护提议
- `after_error` 事件：error pattern 匹配 → 注入已知坑或提议新坑

## 3. Non-Goals

- `api:` trigger 匹配（当前仅解析未匹配，场景太少，不做）
- `audit-kb.sh` / `scan-workspace.sh` / `graph.sh` 迁移到 Python
- runtime 自己做语义分析写 KB（runtime 只做信号检测 + 模板，语义由模型完成）
- Claude Code / Cursor 上的系统级弹窗（平台不支持）

## 4. Architecture

```
会话生命周期
─────────────────────────────────────────────────────
session_start      → 注入 CONTEXT.md + MAP 摘要 + 健康警告
    ↓
after_edit/shell   → PITFALLS 全文匹配 + 注入 + 日志
after_error        → error pattern 匹配 → 注入已知坑 / 提议新坑
    ↓
[每 N 轮 / 300s]   → health check（已有，不改）
    ↓
session_end        → staleness check + 维护提议 + 会话汇总
─────────────────────────────────────────────────────
全程：logger 写入 .pikb/.lore-session-log.jsonl
```

**核心原则**：runtime 做检测和信号，模型做语义理解和写入。日志贯穿全程。

## 5. Components

### 5.1 PITFALLS 全文注入

**文件**：`runtime/lore_runtime/pitfalls.py`（改）

**现状**：
```
[lore] ⚠️ PITFALLS match — read PITFALLS.md before continuing:
  #1 Auth middleware is order-sensitive (⭐⭐⭐⭐)
```

**改为**：注入标题 + 正文（Symptom / Root Cause / Solution）

```
[lore] ⚠️ PITFALLS #1: Auth middleware is order-sensitive (⭐⭐⭐⭐)
  Symptom: 请求通过认证但后续中间件拿到空 user
  Root Cause: auth middleware 注册顺序错误
  Solution: auth 放在 user resolver 后面注册
```

**实现**：
- `match()` 返回结果新增 `body` 字段（section 全文）
- `format_additional_context()` 优先提取 `Symptom:` / `Root Cause:` / `Solution:` 标准字段
- 无标准字段时取 section body 前 1500 字符
- 多个匹配时按难度排序，总长度超 3000 字符则截断

### 5.2 会话日志

**文件**：`runtime/lore_runtime/logger.py`（新）

**位置**：`.pikb/.lore-session-log.jsonl`

**格式**（JSONL）：
```json
{"ts":"2026-08-10T15:32:01","event":"session_start","status":"healthy","summary":"KB loaded"}
{"ts":"2026-08-10T15:33:12","event":"after_edit","path":"middleware/auth.ts","matches":[{"id":"1","title":"Auth order"}]}
{"ts":"2026-08-10T15:35:00","event":"auto_maintain","action":"pitfall_appended","detail":"#5 connection timeout"}
{"ts":"2026-08-10T15:40:00","event":"draft","action":"draft_created","file":".pikb/.lore-drafts/MAP.patch.md"}
{"ts":"2026-08-10T16:00:00","event":"session_end","summary":"3 PITFALLS matched, 1 auto-append, 1 draft"}
```

**接口**：
- `append(event, cwd, **fields)` — 追加一条日志
- `read_session(cwd)` — 读取当前会话的所有日志（通过 SESSION_ID 标记）
- `summarize(cwd)` — 返回当前会话汇总：匹配次数、自动写入次数、draft 数量

**CLI**：`scripts/lore-log.sh`
- `--last` — 最近一次会话汇总
- `--summary` — 最近 N 次会话汇总
- `--since <time>` — 指定时间后的日志
- `--all` — 本次会话全部日志

### 5.3 实时通知

**三个通道**：

| 通道 | pi | Claude Code | Cursor | 用途 |
|------|----|-----------|--------|------|
| `additional_context` | ✅ | ✅ | ✅ | 所有事件，模型都能看到 |
| `notify()` | ✅ | — | — | pi 增强：用户当场看到 |
| `statusLine` | ✅ | ✅ | — | 简短状态如 `📚 l ⚠` |

**通知分级**：

| 级别 | 事件 | 行为 |
|------|------|------|
| 高 | PITFALLS 匹配、自动写入 | notify（pi）+ additional_context + 日志 |
| 中 | draft 创建、健康告警 | additional_context + 日志，pi 额外 notify |
| 低 | 健康正常、日志记录 | 仅写日志，不打扰 |

### 5.4 分级自动维护

**文件**：`runtime/lore_runtime/maintenance.py`（新）

**核心设计**：runtime 只做信号检测 + 生成模板化指令，注入 `additional_context`。模型收到指令后执行实际的 KB 写入。

#### 低风险 — 直接注入执行指令

| 信号 | 检测方式 | 注入指令 |
|------|---------|---------|
| 新仓库无 CONTEXT.md | `session_end` staleness check | `[lore] 检测到新仓库 X，请创建 .pi/kb/CONTEXT.md。模板：…` |
| 错误匹配已知 error pattern | `after_error` 中 regex 匹配 | `[lore] 已命中 PITFALLS #N（全文注入如上）` |
| 新型错误未匹配 | `after_error` 未匹配但多次出现 | `[lore] 检测到新型错误 pattern "…" 出现 N 次，建议追加 PITFALLS 条目` |
| PITFALLS 缺少 Triggers | `session_end` staleness | `[lore] PITFALLS #3 缺少 Triggers 字段，请补充` |

模型收到指令后直接调用 Edit/Write tool 执行，日志自动记录。

#### 高风险 — 生成 draft 文件

| 信号 | 动作 | 文件 |
|------|------|------|
| MAP.md 引用过期（新仓库未记录） | 生成 MAP 补充条目 | `.pikb/.lore-drafts/MAP.patch.md` |
| CONVENTIONS 缺少新模式 | 生成 CONVENTIONS 补充条目 | `.pikb/.lore-drafts/CONVENTIONS.patch.md` |
| PITFALLS 条目可能过时 | 标记待验证 | `.pikb/.lore-drafts/PITFALLS.stale.md` |

**Draft 格式**：最小 unified diff 风格，方便 review：
```markdown
## Proposed: MAP.md

@@ services
+| notification-service | 基础 | 异步通知 | internal/handler/ |
```

**注入指令**：`[lore] 📝 生成了 2 个 KB draft，请 review .pikb/.lore-drafts/`

#### 安全阀

- 每次自动写入记录到日志（`auto_maintain` 事件）
- pi 提供 `/lore-undo` 命令回退最近一次自动写入
- 所有 draft 需人工确认才合并
- 写入前检查文件是否已在本次会话中被修改（避免覆盖用户的并行修改）

### 5.5 session_end 事件

**触发**：会话结束时

**流程**：
1. 跑轻量 staleness check（复用现有的 check-staleness 逻辑，但只做快速检查：新仓库、引用过期）
2. 收集本次会话日志 → `logger.summarize()`
3. 如有 staleness issues → 生成维护 proposals（调用 `maintenance.py`）
4. 将汇总 + proposals 写入 `additional_context`
5. 输出会话汇总通知

**JSON 结果新增字段**：
```json
{
  "session_summary": {
    "pitfall_matches": 3,
    "auto_writes": 1,
    "drafts": 2,
    "errors_logged": 5
  },
  "staleness": {
    "stale": true,
    "issues": [
      {"check": "CONTEXT.md coverage", "detail": "2 repos missing"}
    ]
  },
  "maintenance_proposals": [
    {"type": "auto", "target": "PITFALLS.md", "content": "..."},
    {"type": "draft", "target": "MAP.md", "file": ".pikb/.lore-drafts/MAP.patch.md"}
  ]
}
```

#### 平台适配

| 平台 | 实现 | 备注 |
|------|------|------|
| **Claude Code** | `Stop` hook → `lore-event session_end --cwd $PWD` | 原生支持 |
| **pi** | `turn_end` 中调用 session_end 逻辑（每 N 轮或检测会话终止） | 无原生 `session_end` hook，模拟 |
| **Cursor** | `session_start` 时补跑上次遗留的 session_end 任务 | 无 session end hook，降级 |

### 5.6 after_error 事件

**触发**：工具调用失败时

**流程**：
1. 适配器捕获 error message → 传入 `lore-event after_error --cwd DIR --error "message"`
2. `pitfalls.py` 对 error message 做 pattern 匹配（复用 Triggers `cmd:` 中的关键字 + 新增 error-specific patterns）
3. 匹配到 → 注入对应 PITFALLS 全文
4. 未匹配但同类型错误重复出现 → 注入提议指令

**JSON 结果**：
```json
{
  "ok": true,
  "event": "after_error",
  "matches": [{"id": "3", "title": "connection timeout", "body": "..."}],
  "new_pattern": null,
  "additional_context": "..."
}
```

#### 平台适配

| 平台 | 实现 |
|------|------|
| **pi** | 现有 `tool_execution_end` 中调用 `after_error`（已有 error logging 基础设施） |
| **Claude Code** | `PostToolUse` 中检测 tool result exit code ≠ 0，调用 `after_error` |
| **Cursor** | `post-tool-use.sh` 中检测 error，调用 `after_error` |

## 6. File Changes

### Runtime (shared)

```
runtime/lore_runtime/
  pitfalls.py         # 改: match() 返回 body; format_additional_context() 注入全文
  events.py           # 改: 新事件路由 + logger 集成
  cli.py              # 改: 注册 session_end, after_error
  types.py            # 改: session_end 结果字段
  logger.py           # 新: 会话日志模块
  maintenance.py      # 新: 维护引擎
```

### Adapters

```
lore-extension/
  index.ts            # 改: after_error (tool_execution_end 中); session_end (turn_end 中)

cursor-hooks/
  session-start.sh    # 改: 补跑遗留维护任务
  post-tool-use.sh    # 改: after_error 检测

~/.claude/
  settings.json       # 改: 新增 Stop hook → session_end; PostToolUse 新增 after_error
```

### Scripts

```
scripts/
  lore-log.sh         # 新: 日志查看 CLI
```

### No changes

```
runtime/lore_runtime/
  context.py          # 不改
  discover.py         # 不改
  health.py           # 不改

adapters/
  common.sh           # 不改
```

## 7. Platform Capability Matrix

| 能力 | pi | Claude Code | Cursor |
|------|----|-----------|--------|
| PITFALLS 全文注入 | ✅ tool_call → additional_context | ✅ PreToolUse → stdout | ✅ post-tool-use → additional_context |
| 会话日志 | ✅ runtime 内部 | ✅ runtime 内部 | ✅ runtime 内部 |
| 实时通知 | ✅ notify() 原生 | ⚠️ additional_context 间接 | ⚠️ additional_context 间接 |
| session_end | ⚠️ turn_end 模拟 | ✅ Stop hook 原生 | ❌ session_start 补跑 |
| after_error | ✅ tool_execution_end | ✅ PostToolUse | ✅ post-tool-use |
| 自动维护 | ✅ 模型执行 | ✅ 模型执行 | ✅ 模型执行 |

**能力梯度**：pi > Claude Code > Cursor。核心功能三平台共享，通知和 session_end 在不同平台上有体验差异。

## 8. Testing

- 扩展现有 `runtime/tests/test_events.py`：新增 `session_end`、`after_error` 测试
- 新增 `runtime/tests/test_logger.py`：日志读写、汇总
- 新增 `runtime/tests/test_maintenance.py`：信号检测、draft 生成
- 夹具 `mini-ws/` 扩展：新增有错误模式的场景
