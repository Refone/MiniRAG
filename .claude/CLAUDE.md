# CLAUDE.md

## 项目简介

RAG Agent，LangGraph 编排。导入链路已实现，查询链路待实现。

## 核心约束

- **测试已在框架层面禁用（快速迭代阶段）**：不要新建 `*_test.py`，不要修改 `test/` 下已有文件，不要把运行测试当作验收步骤。`uv run pytest` 只会跑 `test_guard/` 里的恒绿占位用例（exit 0），真实 `test/` 默认不收集。
- 验收方式：直接运行目标脚本 / 启动服务观察 loguru 日志，或跑 `dev/` 下的调试脚本。
- 确实需要回归某个已有用例时，显式指定路径绕过默认配置：`uv run pytest test/unit/...`。

## 常用命令

- ~~`uv run pytest`~~：**默认入口已禁用**，只会跑恒绿占位用例（开关在 `pyproject.toml` 的 `testpaths`）
- 手动回归（按需，显式路径）：`uv run pytest test/unit/utils/path_utils_test.py` / `uv run pytest test/smoke -s -v --run-smoke`
- 调试导入流程 (PDF)：直接运行 `dev/import_pdf.py`
- 安装依赖：`uv sync`

## 导入链路（7 节点）

1. `node_entry` ✅ — 文件识别 + 状态补全
2. `node_pdf_to_md` ✅ — MinerU 云端转换（依赖 `MINERU_API_KEY`）
3. `node_md_img` TODO — 图片上传 MinIO + 多模态描述
4. `node_document_split` TODO — 标题递归切分 + Metadata
5. `node_item_name_vect` TODO — LLM 归纳主体
6. `node_chunks_vect` TODO — BGE-M3 稠密/稀疏向量
7. `node_upsert_milvus` TODO — 删旧 + 批量插入

**实现 TODO 节点时**：先更新 `state.py`，再写节点函数，最后在 `nodes/__init__.py` 导出。

## 项目结构（关键部分）

- `src/processor/import_processor/` — 导入链路核心
- `src/processor/query_processor/` — 查询链路（空）
- `src/utils/node_utils.py` — 节点装饰器
- `test/` — 测试目录（完整保留，框架层已禁用：默认不收集、不运行，回归需显式路径）
- `test_guard/` — 测试禁用的恒绿占位用例（`uv run pytest` 默认入口）
- `dev/` — 实验性调试脚本（直接运行观察 src 逻辑，不受测试保护）

## 架构图

见 ![架构图](docs/architecture.png)

## 关于 Git

可以执行任何只读命令, 但是不要有任何改变状态的操作 (包括但不限于 `git add`、`git commit` 等)。
