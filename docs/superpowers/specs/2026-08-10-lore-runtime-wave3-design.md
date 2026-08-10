# Lore Runtime Wave 3 — 任务切片、所有权、交叉引用

- **Date**: 2026-08-10
- **Status**: draft
- **Dependencies**: Wave 2 `lore_runtime` (complete)

## 1. Motivation

Wave 2 补齐了全文注入、会话日志、自动维护信号。但三个问题仍然存在：

1. **大 monorepo token 贵** — `session_start` 注入整个 CONTEXT.md（2048 字符）+ MAP.md（80 行），不相关的服务信息也消耗 token
2. **KB 条目无责任人** — 过期了不知道找谁确认
3. **交叉引用断裂** — 自由文本引用（「参见 CONVENTIONS §6」）重构后无声断裂

Wave 3 逐个解决。实现顺序：Feature 2 → Feature 1 → Feature 3（按风险和依赖排序）。

## 2. Feature 2 — CODEOWNERS 式责任字段

**纯增量改动，零风险。最先做。**

### 格式

给 PITFALLS、CONVENTIONS、MAP 条目加 `Owner` 和 `Last verified`：

```markdown
## 3. 支付回调幂等

- Owner: @payment-team
- Last verified: 2026-07-15
- Difficulty: ⭐⭐⭐⭐
- Symptom: ...
```

```markdown
| Repo | Layer | Owner | Key Modules |
|------|-------|-------|-------------|
| order-service | Business | @payment-team | internal/handler/ |
```

`MAP.md` 的 MAP table 新增 `Owner` 列。`CONVENTIONS.md` 每条规范加 Owner/Last verified。

### 运行时解析

- `pitfalls.py`：`_extract_field(body, "Owner")` 和 `_extract_field(body, "Last verified")`（已有 `_extract_field`，直接复用）
- MATCH 返回结果新增 `owner` 和 `last_verified` 字段

### Per-Entry Age

现有 `health.py` 用文件 `st_mtime` 判断 staleness。改为：

```
entry_age = max(entry.Last verified, file.mtime)
```

- 没有 `Last verified` 的旧条目 → 回退到 `file.mtime`（保持现有行为）
- 有 `Last verified` → 用条目字段

### session_end staleness 报告增强

```
[lore] ⚠️ KB staleness:
  - PITFALLS #3 "支付回调幂等" — last verified 120d ago
    Owner: @payment-team
  - MAP.md "user-service" — referenced repo dir missing
    Owner: @infra-team
```

### 不会做的

- `audit-kb.sh --by-owner` 暂不做。runtime 在 JSON 中暴露 owner 数据，shell 脚本后续补。

## 3. Feature 1 — Hotspot-Triggered KB Loading

**需要 Feature 2 打底（引用的条目应有 owner/age）。第二步做。**

### 问题

```
session_start 注入: 整个 CONTEXT.md (2048 chars) + MAP.md (80 lines)
  → 大 monorepo: 15 个服务 × 每服务 2KB = 30KB 上下文
  → 大多不相关: 只改 1 个服务，其他 14 个服务的信息是噪音
```

### 方案

**两步加载**：

1. `session_start` → 只注入 CONTEXT.md 前 500 字符（服务定位 + Hotspots 表头）
2. `after_edit` → 匹配 Hotspots 表 → 注入匹配项 + resolved wikilinks

### CONTEXT.md 格式扩展

```markdown
# order-service
订单服务。@workspace → ../.pikb/MAP.md

## Entry
- main: cmd/server/main.go
- config: etc/

## Hotspots
| File pattern | Why | Refs |
|-------------|-----|------|
| internal/handler/checkout.go | 下单核心，并发敏感 | [[PITFALLS#3]] [[CONVENTIONS#并发安全]] |
| internal/payment/ | 微信回调入口，幂等关键 | [[PITFALLS#1]] |
| db/migrations/ | schema 变更 | [[CONVENTIONS#数据库规范]] |
```

### 运行时行为

```
after_edit: internal/handler/checkout.go

  → PITFALLS match: #3 (existing)
    [lore] ⚠️ PITFALLS #3: 库存超卖 (⭐⭐⭐⭐)
      Symptom: ...
      Root Cause: ...
      Solution: ...
  
  → Hotspot match: "internal/handler/checkout.go"
    [lore] 📍 checkout.go — 下单核心流程，并发敏感
      关联 PITFALLS #3: 库存超卖 (已在上方注入，跳过)
      关联 CONVENTIONS §并发安全:
        所有写操作必须用 SELECT FOR UPDATE
        锁顺序: account → order → inventory
```

### 实现

**context.py 改动**：

- 提取 `parse_context(content)` → `{desc, entry_points, hotspots[]}`
- 新增 `match_hotspots(cwd, path)` → 返回匹配的 hotspot 条目 + resolved wikilinks

**events.py 改动**：

- `_session_start_event()` → CONTEXT 截断 500 字（可配置）
- `_pitfalls_event()` → 叠加 hotspot 匹配结果到 `additional_context`

**Feature flag**：环境变量 `LORE_HOTSPOT_LOADING=1` 启用，默认关闭。逐项目灰度。

### 去重

Hotspot 引用的 PITFALLS 可能已经被 `pitfalls.match()` 注入了。`events.py` 中检查 `matched_pitfall_ids` 避免重复注入。

### 性能

- 每次 `after_edit` 解析 CONTEXT.md → 文件小（&lt; 5KB），正则解析 &lt; 1ms
- PITFALLS.md 可能在同一事件中被解析两次（`pitfalls.match()` + wikilink resolve）→ 在事件生命周期内缓存解析结果

### 不会做的

- 不需要新摘要格式。500 字就是 CONTEXT.md 开头 500 字。
- 不做编辑大小阈值。先全量做，后续根据实际体验调。

## 4. Feature 3 — Wikilink 交叉引用验证

**缩减版：只做解析 + 验证 + 报告，不做自动修复。第三步做。**

### 格式规范

```markdown
[[PITFALLS#3]]
[[CONVENTIONS#并发安全]]
[[MAP#services]]
```

- 文件扩展名可选（`[[PITFALLS]]` = `[[PITFALLS.md]]`）
- 锚点是条目标题（`#N. Title` 匹配数字前缀 + 文本，`#文本` 匹配纯文本标题）
- 大小写不敏感

### discover.py 新增

```python
def resolve_wikilink(link: str, cwd: str) -> dict:
    """Resolve a wikilink to a file path and anchor.
    Returns {resolved: Path|None, anchor: str|None, error: str|None}"""

def check_crossrefs(cwd: str) -> list:
    """Scan all KB files for wikilinks, verify each resolves.
    Returns [{source_file, line, wikilink, status: ok|broken_file|broken_anchor, detail}]"""
```

### session_end 集成

在现有 staleness check 之后追加 crossref check：

```
[lore] ⚠️ KB staleness:
  - ... (existing staleness)

[lore] 🔗 cross-reference check:
  ❌ PITFALLS.md:5 → [[CONVENTIONS#§6 并发]] — anchor not found
  ❌ MAP.md:12 → [[PITFALLS#99]] — PITFALLS #99 does not exist
  ✅ 23 references OK
```

断裂引用注入 `additional_context`。模型收到后可以用 Edit tool 手动修正（保持一致架构：「runtime 提案，模型执行」）。

### 迁移路径

现有 KB 用自由文本引用（`参见 CONVENTIONS §6`、`见 PITFALLS #3`）。`audit-kb.sh` 的现有链接检查器（Markdown `[text](path)` 解析）继续工作。

迁移策略：
- Wave 3：两种格式并存。`check_crossrefs()` 只验证 `[[]]` wikilinks。`audit-kb.sh` 继续检查 Markdown links。
- 推荐用户逐步迁移。`audit-kb.sh` 增加提示：「Found N loose references, consider converting to wikilinks」
- Wave 4+：自动迁移 + 自动修复

### 不会做的（推迟 Wave 4）

- ❌ 自动修复 wikilink 路径
- ❌ 合并检测（需要版本历史）
- ❌ `audit-kb.sh --fix`
- ❌ 循环引用检测（YAGNI — KB 规模不会大到需要）

## 5. File Changes

### Feature 2 (Owner fields)

```
pitfalls.py          # _extract_field() for Owner/Last verified; match() returns owner fields
health.py            # per-entry age = max(Last verified, file.mtime)
maintenance.py       # staleness report includes owner
templates/           # PITFALLS, CONVENTIONS, MAP: add Owner/Last verified fields
```

### Feature 1 (Hotspot loading)

```
context.py           # parse_context(), match_hotspots()
events.py            # _session_start_event: 500-char truncation; _pitfalls_event: hotspot overlay
types.py             # LORE_HOTSPOT_LOADING env var default
templates/CONTEXT.md # Hotspots table format with Refs column
```

### Feature 3 (Wikilink validation)

```
discover.py          # resolve_wikilink(), check_crossrefs()
events.py            # _session_end_event: crossref check integration
maintenance.py       # check_crossrefs() call in session_end
audit-kb.sh          # flag loose refs alongside wikilink checks
```

### No changes

```
logger.py            # (may log crossref check results in Wave 4)
cli.py               # no new events
adapters/            # no adapter changes
```

## 6. Testing

- Feature 2: `test_pitfalls_owner_parsing`, `test_health_per_entry_age`
- Feature 1: `test_parse_context_hotspots`, `test_match_hotspots`, `test_session_start_truncation`
- Feature 3: `test_resolve_wikilink`, `test_check_crossrefs`
- ~15 新测试用例

## 7. Implementation Order

```
Day 1-2:  Feature 2 (Owner fields)        — 纯增量，零风险
Day 3-5:  Feature 1 (Hotspot loading)     — 依赖 Feature 2 的字段解析
Day 6-8:  Feature 3 (Wikilink validation) — 依赖 wikilink 解析器（Feature 1 已建）
```
