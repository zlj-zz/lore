---
name: lore
description: 项目知识库——大项目/多仓库场景下结构化积累、渐进式加载。触发：项目文档、架构、规范、踩坑、多仓库、知识库、项目记忆、onboarding
---

# lore — 项目知识库

渐进式披露的项目知识体系，跨 agent 通用（pi / Claude Code / Cursor CLI）。

## 核心理念

```
小型项目 → CONTEXT.md 就够了
大型/多仓库 → .pikb/（工作区） + .pi/kb/（仓库）分层
```

## 目录结构

```
工作区根（多仓库场景）:
  .pikb/                         ← 全局知识库（手写或 agent 生成）
  ├── MAP.md                     ← 服务地图：仓库列表、模块关系、数据流
  ├── CONVENTIONS.md             ← 代码规范、命名约定、模式
  ├── PITFALLS.md                ← 跨仓库已知坑、隐蔽点
  └── 任何 .md                    ← 自由扩展

仓库级:
  .pi/kb/                        ← 本仓库专属
  ├── CONTEXT.md                 ← 快速上手：定位、入口、关键文件
  └── PITFALLS.md                ← 本仓库独有坑
```

## 渐进式加载

```
会话启动
  → 强制读 .pi/kb/CONTEXT.md（轻量，1-2KB）
  → 向上查找 .pikb/
  → 按需加载：
      写代码前          → CONVENTIONS.md
      跨模块改动        → MAP.md
      遇到错误           → PITFALLS.md
```

## 创建知识库

### 初始化

如果 `.pikb/` 不存在，根据对话内容判断是否需要：

1. **有**.pikb/ → 按需加载
2. **没有**，但项目复杂（多仓库 / 大项目 / 对话已超过 5 轮）→ ask user:
   - "看起来项目比较复杂，要我帮忙创建一套项目知识库吗？"
   - 确认后：探索代码 → 生成模板 → ask user 补齐

### 内容要求

- **只记录已实现的事实**，方案/意图标记 `📋 planned`
- **记录难点**：现象 + 根因 + 解决
- **记录约定**：代码风格、模式、禁止事项

## 状态标记

| 标记 | 含义 |
|------|------|
| ✅ | 已实现 |
| 🔧 | 进行中 |
| 📋 | 已规划，待实现 |
| 💡 | 提议，未定 |

## 维护

- 每次代码变更后评估是否需要更新
- 重大变更 → ask user: "知识库需要更新吗？"
- 新坑 → 直接追加到 PITFALLS.md
- 规范变了 → 更新 CONVENTIONS.md

## 跨 Agent 使用

其他 agent 在 `AGENTS.md` 中加入：

```markdown
## Knowledge Base

On session start, read .pi/kb/CONTEXT.md. If it references a workspace,
read .pikb/MAP.md. Consult CONVENTIONS.md before writing code,
PITFALLS.md on errors. Update kb after significant changes.
```
