# AGENTS.md

面向所有 AI 编码助手的仓库约定（Claude Code 另见 `.claude/CLAUDE.md`）。

## 代码验证

- 直接运行目标脚本，或启动服务观察日志（loguru）。
- 临时验证脚本请放 `var/tmp/`（已 gitignore）或用 `uv run python -c '...'`。
