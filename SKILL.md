---
name: lore
description: >-
  Structured, progressively-loaded project knowledge base for multi-repo
  workspaces. Before you read more than 3 files blindly in an unfamiliar
  project — stop and use this skill first. Use when entering a new codebase,
  onboarding, exploring project structure, or when the user mentions 项目知识库,
  创建知识库, 初始化知识库, 多仓库, 项目记忆, 帮我了解这个项目, 这个项目怎么跑,
  explore this codebase, setup project memory. Also triggers when .pikb/ is
  missing in a complex workspace.
---

# lore — 项目知识库

渐进式披露的项目知识体系，跨 agent 通用。

## 安装

```bash
cd ~/projects/lore && ./install.sh   # pi + Claude + Cursor
# ./install.sh --pi --claude         # 指定 agent
```

Agent 也可以自动安装：`/skill:lore 帮我安装到 Claude Code`

## 核心理念

```
小型项目 → CONTEXT.md 就够了
大型/多仓库 → .pikb/（工作区） + .pi/kb/（仓库）分层
```

## 目录结构

```
工作区根（多仓库场景）:
  .pikb/
  ├── MAP.md                     ← 服务地图：仓库列表、模块关系、数据流、文档导航
  ├── CONVENTIONS.md             ← 代码规范、命名约定、模式、禁止事项
  ├── PITFALLS.md                ← 跨仓库已知坑、隐蔽点（带难度星级）
  └── 任何 .md                    ← 自由扩展

仓库级:
  .pi/kb/
  ├── CONTEXT.md                 ← 快速上手：定位、入口、关键文件、@workspace 引用
  └── PITFALLS.md                ← 本仓库独有坑
```

## 渐进式加载

```
会话启动
  → 强制读 .pi/kb/CONTEXT.md
  → 向上查找 .pikb/
  → 按需加载：
      写代码前          → CONVENTIONS.md
      跨模块改动        → MAP.md
      遇到错误           → PITFALLS.md
```

---

## 初始化流程

### Step 1: 侦查

1. 运行 `scripts/scan-workspace.sh [path]` 获取结构化工作区快照（repos、类型、agent 文件、docs）
2. 区分为仓库 / 文档 / 工具（脚本已做，人工确认）
3. 读 `AGENTS.md` / `CLAUDE.md` / `.cursorrules`（脚本已标注哪些仓库有）
4. 读 `docs/` / `README.md`（脚本已列出）
5. 从代码中识别分层（API → 聚合 → 领域 / 类似结构）
6. **交叉验证**：对文档中提取的关键事实（API 路径、数据结构、配置项），抽样 grep 代码确认。若文档与代码不一致 → 以代码为准，标注 `⚠️ 文档过时（doc v.s. code）`

### Step 2: Ask user 补齐

在创建文件之前，把侦查结果结构化后 ask user：

```
我探索了这个工作区，初步理解：

仓库（8个）:
  API: api-gateway
  业务: user-service, order-service, payment-service
  基础: auth-service, notification-service
  
分层规则: API → 业务 → 基础 → DB
外部系统: 微信支付、阿里云 OSS、SendGrid

有几个问题需要确认：
1. notification-service 是同步还是异步？
2. 支付回调的入口路径是什么？
3. 有没有全局的代码规范文档？
```

**目的**：在写文件之前校准理解，避免基于错误假设生成大量内容。

### Step 3: 生成

按模板生成所有文件：

| 顺序 | 文件 | 来源 | 模板 |
|------|------|------|------|
| 1 | `.pikb/MAP.md` | 侦查 + ask user 回答 | [`templates/MAP.md`](templates/MAP.md) |
| 2 | `.pikb/CONVENTIONS.md` | 代码扫描 + AGENTS.md + ask user | [`templates/CONVENTIONS.md`](templates/CONVENTIONS.md) |
| 3 | `.pikb/PITFALLS.md` | 代码中的 TODO/FIXME/HACK + ask user "有什么已知坑？" | [`templates/PITFALLS.md`](templates/PITFALLS.md) |
| 4 | `.pikb/README.md` | 索引 | 自行生成 |
| 5 | **每个仓库** `.pi/kb/CONTEXT.md` | `ls` + `head` 入口文件 | [`templates/CONTEXT.md`](templates/CONTEXT.md) |

⚠️ **必须为工作区下每一个仓库创建 CONTEXT.md**。跳过就是知识盲区。

### Step 4: 交叉引用

生成完成后确保：

- MAP.md 顶部有 `> 常见坑：[PITFALLS.md](./PITFALLS.md)` 链接
- PITFALLS.md 每个条目引用相关 CONVENTIONS 或 MAP 小节（如 `参见 CONVENTIONS §6`）
- 每个 CONTEXT.md 有 `工作区知识库：../.pikb/MAP.md` 引用

---

## 内容规范

### 核心原则：自包含

**知识库是快照，不是索引。** 事实必须内联，外部文档只是来源标注。

外部文档可能过时。**事实以代码实现为准，文档只是线索。** 若代码与文档矛盾，知识库记录代码实际行为，并标注文档版本/日期。用 `⚠️ 文档过时（doc v.s. code）` 标记不一致项。

```markdown
# ❌ 只引用外部文档
支付回调规则见 docs/payment/callback.md

# ✅ 事实内联 + 来源标注
## 支付回调
- 入口: POST /webhook/payment
- 幂等: Redis order:{id}:callback_lock 60s
- 来源: docs/payment/callback.md（2024-03）
```

外部文档可能被删除、移动或过时。知识库中的事实不依赖它们存在。

### 状态标记

| 标记 | 含义 |
|------|------|
| ✅ | 已实现 |
| 🔧 | 进行中 |
| 📋 | 已规划，待实现 |
| 💡 | 提议，未定 |

强制要求：**只记 ✅ 事实**。📋 💡 必须显式标记，防止 agent 把方案当现状。

### PITFALLS.md 条目格式

```markdown
## N. 坑的标题

- Difficulty: ⭐⭐⭐⭐（1-5，越多越隐蔽/难排查）
- Symptom: 现象
- Root Cause: 根因
- Solution: 正确做法
- Related: 参见 [CONVENTIONS §X](./CONVENTIONS.md#...)
```

### MAP.md 仓库条目格式

```markdown
| 仓库 | 层 | 职责 | 关键模块 |
|------|----|------|----------|
| api-gateway | API | 路由、鉴权 | internal/middleware/, internal/handler/ |
```

### CONTEXT.md 最小内容

```markdown
# repo-name

一句话定位。

## 入口
- 主程序: main.go
- 配置: etc/
- @workspace → ../.pikb/MAP.md
```

---

## 维护规则

### 自动更新（不打扰用户）

以下情况**直接追加/修改**，不需要 ask：

- 遇到新坑 → 追加到 PITFALLS.md
- 发现代码模式 → 补充 CONVENTIONS.md
- 新增仓库 → 创建 CONTEXT.md + 更新 MAP.md

### 询问后更新

以下情况 **ask user 确认**再改：

- 跨仓库架构变更（如拆分/合并服务）→ MAP.md
- 规范变更（如换 linter / 改命名约定）→ CONVENTIONS.md
- 已有 PITFALLS 条目不适用于当前版本 → 标记 `⏳ 待验证` 或删除

### 触发检测

每轮对话结束时检查：

- 是否涉及了新仓库？ → 补 CONTEXT.md
- 是否有工具调用失败？ → 查 PITFALLS.md，没有则追加
- 是否改了 API 签名 / 数据模型？ → 更新 MAP.md 相关条目
- 是否引入了新模式？ → 补 CONVENTIONS.md

定期运行质量检查：

```bash
scripts/check-staleness.sh   # KB 是否过期
scripts/audit-kb.sh          # KB 质量审计
```

---

## 使用脚本

| 脚本 | 用途 | 阶段 |
|------|------|------|
| `scripts/scan-workspace.sh` | 工作区结构快照 | 创建 |
| `scripts/graph.sh --embed` | 生成 Mermaid 依赖关系图 | 创建 |
| `scripts/on-session-start.sh` | KB 健康检查 | 使用 |
| `scripts/quick-ref.sh <keyword>` | KB 关键词检索 | 使用 |
| `scripts/check-staleness.sh` | 检测 KB 过期（新仓库/引用变更） | 维护 |
| `scripts/audit-kb.sh` | KB 质量审计（交叉引用/字段完整/死链接） | 维护 |

### 会话启动集成

在 `AGENTS.md` 或 PostToolUse hook 中调用：

```bash
./scripts/on-session-start.sh || echo "[lore] run /skill:lore 创建知识库 to initialize"
```

## 跨 Agent

`./install.sh` 自动配置加载规则。也可手动添加——见 [AGENTS.md](./AGENTS.md)。

## 模板

Templates 在 `templates/` 目录下，初始化时复制使用。
