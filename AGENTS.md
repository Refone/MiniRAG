# AGENTS.md

面向所有 AI 编码助手（Claude Code / Codex / Cursor / DSH …）的仓库约定。
**本文件是唯一来源**，各工具的私有配置目录不再单独维护规则。

## 代码验证

- 直接运行目标脚本，或启动服务观察日志（loguru）。
- 临时验证脚本请放 `var/tmp/`（已 gitignore）或用 `uv run python -c '...'`。
- 代码改动必须能通过 pre-commit，过不了就不算完成：

## 关于 Git

- 任何**只读**命令都可以执行：`git status`、`git log`、`git diff`、`git show` 等。
- **不要做任何改变状态的操作**，包括但不限于 `git add`、`git commit`、`git push`、
  `git checkout --`、`git restore`、`git reset`。
- 改动留在工作区，由人审阅后自行提交。
