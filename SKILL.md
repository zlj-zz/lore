---
name: lore
description: 项目知识库——大项目/多仓库场景下结构化积累、渐进式加载。触发：项目文档、架构、规范、踩坑、多仓库、知识库、项目记忆、onboarding
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

1. `ls` 工作区根目录，列出所有子目录
2. 区分哪些是仓库（有 `go.mod` / `package.json` / `.git`），哪些是文档/工具
3. 读 `AGENTS.md` / `CLAUDE.md` / `.cursorrules`（如果有）
4. 读 `docs/` / `README.md`（如果有）
5. 从代码中识别分层（API → 聚合 → 领域 / 类似结构）

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

| 顺序 | 文件 | 来源 |
|------|------|------|
| 1 | `.pikb/MAP.md` | 侦查 + ask user 回答 |
| 2 | `.pikb/CONVENTIONS.md` | 代码扫描 + AGENTS.md + ask user |
| 3 | `.pikb/PITFALLS.md` | 代码中的 TODO/FIXME/HACK + ask user "有什么已知坑？" |
| 4 | `.pikb/README.md` | 索引 |
| 5 | **每个仓库** `.pi/kb/CONTEXT.md` | `ls` + `head` 入口文件 |

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

---

## 跨 Agent

`./install.sh` 自动配置加载规则。也可手动添加——见 [AGENTS.md](./AGENTS.md)。

## 模板

Templates 在 `templates/` 目录下，初始化时复制使用。
