# lore

大项目 / 多仓库场景下的项目知识库。
跨 agent 通用：pi / Claude Code / Cursor CLI。

## 安装

```bash
git clone https://github.com/zlj-zz/lore.git ~/projects/lore
cd ~/projects/lore
./install.sh          # 全部 agent
# ./install.sh --pi --claude  # 指定
```

| Agent | 安装内容 |
|------|---------|
| pi | `~/.pi/agent/AGENTS.md` + Extension（会话启动自动注入） |
| Claude Code | `~/.claude/AGENTS.md` + PostToolUse hook（首次工具调用提醒） |
| Cursor | `~/.cursorrules` |

## 使用

```
/skill:lore 创建知识库
```

Agent 会探索代码、提问确认，然后生成：

- `.pikb/` — 工作区级：MAP（服务地图）、CONVENTIONS（规范）、PITFALLS（踩坑）
- `.pi/kb/` — 仓库级：CONTEXT（快速上手）

## 渐进式加载

```
新会话 → 自动读 CONTEXT.md（轻量）
写代码 → 查 CONVENTIONS.md
跨模块 → 查 MAP.md
遇错误 → 查 PITFALLS.md
```

## 目录结构

```
lore/
├── SKILL.md              # 方法论
├── install.sh            # 一键安装
├── AGENTS.md             # 跨 agent 加载规则
├── templates/            # 文档模板
│   ├── MAP.md            # 服务地图
│   ├── CONVENTIONS.md    # 代码规范
│   ├── PITFALLS.md       # 已知坑
│   └── CONTEXT.md        # 仓库快速上手
└── README.md
```

## License

MIT
