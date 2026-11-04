---
name: implement
description: 需求开发 SOP 的「动工」阶段技能：依据 docs/feat/<需求名>/ 下的 PRD、前端交互 demo、后端改动方案（如有）完成核心代码变更，产出待人类提交的核心 commit。前端改动与 demo 逐点对齐，后端按方案的修改清单与对外契约施工，真跑自测后交付。当用户要「动工 / 开工 / 开始实现 / 修改代码 / 按方案施工」，或 SOP 走到「动工」环节时使用。
whenToUse: 三件套（PRD + demo + 后端改动方案）已评审落定，需要把方案变成 backend/ 与 frontend/ 的真实代码、产出核心 commit 时。
---

# 需求动工（文档 → 核心 commit）

把评审通过的「PRD + 前端交互 demo + 后端改动方案」落地成**能跑、能自测、人类可直接提交**的核心代码变更。
本技能只做「动工」这一件事；测试反馈修复是 SOP 的下一环节，不在本技能范围内。
代码留在工作区，git 提交永远是人类的事；**变更记录就是 git commit，不另写实施文档**（文档 + commit 双产出拖慢效率）。

## 前置门槛（不满足就退回上一阶段，不硬开工）

1. `docs/feat/<需求名>/` 下 PRD 存在；文件名可能不同（如 `需求描述V1.md`、`PRD-V0.md`），以目录内实际为准。
2. 有后端改动 → `后端改动方案.md` 已评审通过（人类 commit 或明确答复），且文档内无 `⏳` 未决项。
3. 有前端改动 → `demo.html` 已定稿（人类评审通过）。demo 未评审动 `frontend/src` = 越阶段。
4. 基线全绿：动工前先跑一遍 §4 自测命令确认基线，避免在红基线上盖楼；`git status --short` 记下动工前已脏的文件，交付时区分「我的改动 / 原有脏点」。

## 产出契约

| 项 | 约定 |
| --- | --- |
| 代码 | 改动落在 `backend/`（后端）与 `frontend/src/`（前端）；严格按方案「文件修改清单」执行，清单外的改动要在交付回复里说明理由 |
| 跟踪 | 变更记录就是 git commit（人类提交）；AI 在交付回复里给文件级改动面总览，不另写实施文档 |
| 验证脚本 | 一次性脚本放 `var/tmp/`（已 gitignore）或 `uv run python -c '...'`，不散落仓库 |
| git | 只读（status / log / diff / show）；不 add / commit / push / checkout / reset |

## 工作流

### 1. 读三件套，定改动面

- `PRD.md`：正文 + 文末「评审纪要 / 补充要求」；**冲突时以评审纪要为准**。
- `demo.html`（如有）：前端契约 —— 布局、每个可达状态、文案、动效参数。
- `后端改动方案.md`（如有）：后端契约 —— 架构调整 / 文件修改清单 / 内部变更 / 对外变更 / 验收条件。
- 产出「需求点 → 改动落点」映射，判定改动面是**仅前端 / 仅后端 / 前后端**，据此分工。
- 方案有 `⏳` → 先退回 `backend-plan` 落定；文档缺失 → 不凭对话臆测开工（SOP 起点是文档）。

### 2. 对齐契约（唯一口径）

- **前端 = demo**：DOM 轮廓、每个可达状态（空 / 加载 / 失败 / 终态，不能只做 happy path）、文案、动效参数、视觉令牌都要在 `frontend/src` 复现；demo 没画的交互不擅自加；mock 数据只当**形状参考**，不当值写死进产品代码。
- **后端 = 方案**：端点、DTO、错误体、SSE 帧、存储落点严格按「对外契约」与「文件修改清单」施工；方案没写的能力不扩展。
- PRD / demo / 方案互相矛盾 → **先问人类**，不自行裁定。

### 3. 动工

- 后端自底向上：`common`（tier 0→4）→ `graphs` → `service` → `api`；前端：types / lib → store → components → pages。
- 每完成方案清单一项就勾掉；新增 / 修改文件与清单不一致的，交付时写明理由。
- 编码过程中逐条对照下方「硬性规则」（分层 / 精度 / 契约风格 / 注释 / 单 worker / 存量数据），违反任意一条即返工。

### 4. 自测（必须真跑，不能目测）

后端：

```bash
.venv/bin/ruff check . && .venv/bin/ruff format --check .
.venv/bin/python tools/check_layout.py
.venv/bin/python tools/check_layers.py
.venv/bin/pytest -q
```

- 改动必须能过 pre-commit；过不了就不算完成。
- 单测只覆盖零外部依赖部分（`tests/conftest.py` 约定）；本轮改动的纯函数要补 / 改单测。
- 涉及 Milvus / MinIO / LLM 的链路：起服务 `uvicorn --app-dir backend api.main:app --reload`（:8000）观察 loguru 日志，或对应节点 `__main__` 点火；确认 `.env` 配置与外部服务可用。
- 方案的「验收条件」逐条跑、逐条记录结果。

前端：

```bash
cd frontend && npm run build   # tsc --noEmit + vite build，类型检查必须全绿
```

- 联调：后端 :8000 + `cd frontend && npm run dev`（:5173，代理 `/api` → :8000）；组件工作台 `npm run storybook`（:6006，无后端也能看）。
- 浏览器走查（对照 demo）：每个状态可直达；console 无 error；明暗主题；1280 / 768 / 390 三档；`prefers-reduced-motion` 降级；点一遍主交互（含弹窗 Esc、toast、tab 切换）。
- 有回归清单（如 `docs/feat/前端重构/回归清单.md`）逐条核对。
- DSH 环境用 `browser_open` / `browser_read` / `browser_console` / `browser_screenshot`；会话提供 `frontend-verify` 技能时按其流程走。

### 5. 交付

- 最终回复必须包含：改动面总览（文件级，与方案清单对照）、与 demo / 方案的对照结论、自测命令与结果、遗留事项（需人类起外部服务验证的）、下一步（人类验收与提交）。
- 只说「改完了」不算交付。不做任何 git 写操作；人类 commit 即核心 commit 的落点。

## 硬性规则

1. **只写代码**：PRD / demo / 后端方案的正文不改（发现文档问题提请人类）；不做任何 git 写操作。
2. **契约优先**：demo（前端）、方案（后端）是唯一口径；互相矛盾先问人。
3. **分层不可破**：`check_layers` 违规即返工；架构调整同步更新检查脚本。
4. **注释三原则**：无文件头注释；关键 schema 带示例实例；注释只说代码本身。
5. **自测必须真跑**：至少 ruff + layout + layers + pytest（后端）、`npm run build`（前端）；临时脚本只进 `var/tmp/`。
6. **改动可控**：只动方案清单内文件；清单外新增必须在交付回复里说明理由。
7. **状态完整**：前端每个 demo 状态（含 loading / error / 空态）都有真实语义，不只做 happy path。
8. **存量数据**：方案规定的清库 / 迁移动作照做并记录；不擅自清库。
9. **进程事实**：不假设进程内单例跨 worker、跨重启可用。
10. **交付规范**：回复里给文件级改动面总览、自测结果、遗留事项；变更记录就是 git commit，不另写实施文档。

## 反模式

- 无 PRD / 方案就凭对话开工。
- demo 未定稿动 `frontend/src`；方案有 `⏳` 动 `backend/`。
- 跳过自测就交付；临时验证脚本散落在仓库根目录（应进 `var/tmp/`）。
- 顺手改 demo / 方案 / PRD 正文。
- 把 demo 的 mock 数值、`bsess-8f2a1c` 这类示例 id 写进产品代码。
- 前端另起炉灶不跟 demo：布局、文案、动效漂移。
- 维护实施文档：变更记录是 git commit，文档 + commit 双产出拖慢迭代。
- `git add` / `git commit`。

## 参考

- 三件套样例：`docs/feat/Token统计/`（PRD.md + demo.html + 后端改动方案.md）、`docs/feat/文档管理页面/`（评审 → 动工 → 验收全流程）。
- SOP 与约束：`AGENTS.md`（需求开发 SOP / 代码验证 / 架构约束 / 注释原则）、`README.md`（运行限制 / 目录约定）；分层自查可用 `tools/check_layers.py --list` 看模块 tier 归属。
