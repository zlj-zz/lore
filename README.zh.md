# lore

<p align="center">
  <em>多仓库项目的结构化知识库，agent 的记忆系统。</em>
</p>

<p align="center">
  <img src="https://img.shields.io/badge/license-MIT-blue" alt="License">
  <img src="https://img.shields.io/badge/agents-pi%20%7C%20Claude%20%7C%20Cursor-6e56cf" alt="Agents">
</p>

---

多仓库工作区里，agent 每次打开都是「新人」——不知道有哪些服务、怎么连接、什么规范、踩过什么坑。

**Lore 给 agent 一个记忆。** 装一次，初始化一次，之后全自动。

```
$ ./scripts/on-session-start.sh

[lore] workspace: ~/projects
  ✓  .pikb/: 已存在
  ✓  KB 文件: 7 个
  ✓  最近更新: 3 天前
  ✓  CONTEXT.md: 8 个仓库全覆盖
```

---

## 安装

```bash
# pi（推荐）
pi install git:github.com/zlj-zz/lore

# 全 agent（pi + Claude + Cursor）
git clone https://github.com/zlj-zz/lore.git ~/projects/lore
cd ~/projects/lore
./install.sh
```

## 使用

```bash
/skill:lore 创建知识库          # 初始化当前工作区
./scripts/graph.sh --embed     # 生成 Mermaid 依赖关系图
./scripts/quick-ref.sh 支付      # 搜索 KB
./scripts/check-staleness.sh    # KB 是否过期
./scripts/audit-kb.sh           # 质量审计
```

Agent 会探索代码、提问确认，然后生成：

```
workspace/
  .pikb/
  ├── MAP.md              ← 服务地图：仓库关系、数据流、模块导航
  ├── CONVENTIONS.md      ← 代码规范：命名约定、模式、禁止事项
  └── PITFALLS.md         ← 已知坑：难度星级、现象、根因、解法
  each-repo/
    .pi/kb/
    └── CONTEXT.md         ← 快速上手：入口、配置、关键文件
```

后续每次会话启动，agent 自动加载上下文，不再从零开始。

---

## 工作原理

| 阶段 | 行为 |
|------|------|
| **会话启动** | `on-session-start.sh` 健康检查 → agent 读 CONTEXT.md + MAP.md |
| **写代码** | agent 先看 CONVENTIONS.md，按规范写 |
| **跨模块改动** | agent 查 MAP.md 了解服务间关系 |
| **遇到错误** | agent 先搜 PITFALLS.md，复用已知解法 |
| **会话结束** | agent 检测新仓库/新模式/新坑 → 自动更新 KB |

---

## 脚本

| 脚本 | 用途 |
|------|------|
| `scan-workspace.sh` | 扫描工作区：识别仓库类型、agent 文件、文档 |
| `graph.sh --embed` | 生成 Mermaid 依赖关系图，直接贴进 MAP.md |
| `on-session-start.sh` | 会话启动时 KB 健康检查 |
| `quick-ref.sh <关键词>` | 按段落搜索 KB 内容 |
| `check-staleness.sh` | 检测过期：新仓库未覆盖、引用文件变更 |
| `audit-kb.sh` | 质量审计：交叉引用、字段完整、死链接、标记一致性 |

---

## Agents

| Agent | 安装内容 |
|-------|---------|
| pi | `AGENTS.md` + extension |
| Claude Code | `CLAUDE.md` + PostToolUse hook |
| Cursor | `~/.cursor/hooks.json`（`sessionStart` + `postToolUse`）+ hook 脚本 |

Cursor：`sessionStart` 注入 CONTEXT/MAP；`postToolUse` 匹配 PITFALLS triggers；安装时会移除旧的 `~/.cursorrules` lore 块（与已有 hooks 合并，不覆盖）。

---

## 设计原则

- **自包含** — 事实内联，外部文档只是来源标注，文档删了 KB 不受影响
- **代码为准** — 文档与代码不一致时，以代码实际行为为准
- **静默维护** — 新仓库、新坑、新模式自动追加，无需手动维护
- **渐进加载** — 启动只读 CONTEXT.md，其余按需加载，不浪费 token

## License

MIT
