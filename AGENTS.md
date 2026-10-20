# AGENTS.md

面向所有 AI 编码助手的仓库约定（Claude Code 另见 `.claude/CLAUDE.md`）。

## 测试策略：单元测试已禁用（快速迭代阶段）

单元测试已在框架层面禁用：`pyproject.toml` → `[tool.pytest.ini_options]` → `testpaths = ["test_guard"]`。

- `test/` 目录**完整保留，但默认不收集、不运行**。
- **不要**新建 `*_test.py` 文件；**不要**修改 `test/` 下已有内容。
- **不要**把 `uv run pytest` 当作验证手段 —— 它只会跑 `test_guard/` 里一个恒绿占位用例。
- 验证代码正确性：直接运行目标脚本，或启动服务观察日志（loguru）。
- 确实需要回归某个已有用例时，显式指定路径绕过默认配置：`uv run pytest test/unit/...`。

恢复默认测试：把 `pyproject.toml` 的 `testpaths` 改回 `["test"]`（CI 工作流同步把
`.github/workflows/unittest.yml.disable` 重命名回 `unittest.yml`）。
