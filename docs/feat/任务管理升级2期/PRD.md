# PRD：导入任务阶段内进度反馈（v0 简版）

> 类型：体验优化 / 可观测性 · 状态：待评审
> 依据：本轮需求对话（2026-11-03）+ MinerU 接口实测；后端契约见 [后端改动方案.md](docs/feat/任务管理升级2期/后端改动方案.md)。
> 说明：前端交互 demo 跳过——`detail` 是可选字段，旧前端零改动兼容；新文案的前端接入量见 §5。

## 1. 当前 SSE 推送文案（现状）

导入进度只到「节点」粒度。后端 `progress` / `child-progress` 快照只有状态与节点名单：

```json
{
  "status": "processing",
  "done_list": ["识别文档类别"],
  "running_list": ["PDF 转 Markdown"]
}
```

前端把 `done_list / running_list` 逐行展示，折叠摘要只有已耗时。以下为各链路的实际可见文案。

### 1.1 PDF 导入（进行中）

```text
华为擎云 S520 Gen2 用户指南-(YTGZ,Windows11_03,zh-cn).pdf   1181.90 KB   处理中...
  已耗时 23.4s，点击收起 / 展开
    ✓ 识别文档类别
    ⟳ PDF 转 Markdown
```

MinerU 解析期间（可能数分钟）界面不再变化，只有「已耗时」在涨。

### 1.2 Markdown 图片识别（ZIP 分支，进行中）

```json
{
  "child_id": "…:md:0",
  "status": "processing",
  "done_list": [],
  "running_list": ["Markdown 图片识别"]
}
```

```text
HAK180用户手册.md   处理中...
  已耗时 8.2s · Markdown 图片识别
```

展开日志同样只有节点名，看不到共几张图、识别到第几张。

### 1.3 文档嵌入入库（ZIP 分支，进行中）

```text
HAK180用户手册.md   处理中...
  已耗时 41.7s · 文档嵌入入库
```

该节点内部包含 1 次 LLM、N 批 embedding 与两次写库，界面无从判断当前阶段。

### 1.4 ZIP 导入（父任务 + 子任务）

```text
HAK180资料包.zip   2048.00 KB   处理中...
  已耗时 51.2s，点击收起 / 展开
    ✓ 识别文档类别
    ✓ 处理 Markdown 压缩包
  已分叉 4 个 md 任务                 1 / 4 完成 · 1 进行中 · 2 等待
    ├─ A.md    处理中...   已耗时 8.2s · Markdown 图片识别
    ├─ B.md    等待中...   等待开始
    └─ …
```

父任务只剩 fork 汇总，单个子任务的内部阶段不可见。

### 1.5 现状汇总

| 节点                 | 当前可见        | 用户无法判断                                 |
| -------------------- | --------------- | -------------------------------------------- |
| PDF 转 Markdown      | 节点名 + 已耗时 | 在上传 / 排队 / 解析 / 下载？解析到第几页？  |
| Markdown 图片识别    | 节点名 + 已耗时 | 共几张图？识别到第几张？                     |
| 文档嵌入入库         | 节点名 + 已耗时 | 在生成摘要 / 向量化 / 写库？向量化到第几批？ |
| 处理 Markdown 压缩包 | 节点名 + 已耗时 | 文档切分与在线图片下载无过程反馈（本期不做） |

## 2. 问题

- 长等待集中在节点内部，SSE 只有节点开始 / 结束 2 帧（[tracing.py](src/common/events/tracing.py:128)）。
- PDF 首帧盲等 `0.5s × 页数`（[node_pdf_to_md.py](src/graphs/import_graph/nodes/node_pdf_to_md.py:117)），100 页即 45s 静默；上限 `10s × 页数 + 30s`。
- 图片识别以 `max_concurrency = 8` 并发调 VLM（[node_md_img.py](src/graphs/import_graph/nodes/node_md_img.py:212)），12 张图可能数十秒。
- 嵌入入库含 1 次 LLM（[node_document_embedding.py](src/graphs/import_graph/nodes/node_document_embedding.py:299)）、`ceil(切片数 / 10)` 批 embedding（[node_document_embedding.py](src/graphs/import_graph/nodes/node_document_embedding.py:194)）与两次写库。
- 用户无法区分「在跑」与「卡死」，只能看着耗时增长。

## 3. 目标效果

### 3.1 目标文案（由后端生成，前端只展示）

| 节点              | 阶段   | `detail.text`                                             |
| ----------------- | ------ | --------------------------------------------------------- |
| PDF 转 Markdown   | 上传   | `24 页 · 正在上传`                                        |
|                   | 排队   | `24 页 · 排队中`                                          |
|                   | 解析   | `24 页 · 解析中 12/24 页`                                 |
|                   | 下载   | `24 页 · 转换完成 · 正在下载`                             |
| Markdown 图片识别 | 摘要   | `12 张图片 · 生成摘要 5/12`                               |
|                   | 上传   | `12 张图片 · 上传中 11/12 · 1 张失败`（无失败时不带后缀） |
|                   | 无图   | `无内联图片`                                              |
| 文档嵌入入库      | LLM    | `87 个切片 · 生成关键词与摘要`                            |
|                   | 向量化 | `87 个切片 · 向量化 3/9 批`                               |
|                   | 写库   | `87 个切片 · 写入向量库`                                  |

### 3.2 页面效果（示意）

```text
华为擎云 S520 Gen2 用户指南.pdf   1181.90 KB   处理中...
  已耗时 48.2s，点击收起 / 展开
    ✓ 识别文档类别
    ⟳ PDF 转 Markdown · 解析中 12/24 页
```

```text
HAK180资料包.zip   2048.00 KB   处理中...
  已分叉 4 个 md 任务                 1 / 4 完成 · 1 进行中 · 2 等待
    ├─ HAK180用户手册.md   处理中...
      已耗时 31.2s · 文档嵌入入库
        ⟳ 文档嵌入入库 · 87 个切片 · 向量化 3/9 批
```

### 3.3 交互要求

- 文案由后端生成，前端不拼业务语义；前端只按 `detail.node` 对齐当前 running 行。
- 折叠摘要（summary）文案保持不变，`detail.text` 只追加到展开后的 running 行。
- `metrics.done / total` 可用于进度条；仅 `stage` 无总数时（如 LLM 阶段）按不确定态展示。
- 断线重连以最新快照为准，不依赖增量顺序。

## 4. 需求点

| 编号 | 优先级 | 需求                                                                            |
| ---- | ------ | ------------------------------------------------------------------------------- |
| R1   | P0     | `progress` / `child-progress` 新增可选 `detail` 字段（`node / text / metrics`） |
| R2   | P0     | PDF 转 Markdown：上传 / 排队 / 解析页进度 / 下载四阶段                          |
| R3   | P0     | Markdown 图片识别：图片总数、摘要完成数、上传完成数                             |
| R4   | P0     | 文档嵌入入库：LLM / 向量化批进度 / 写库阶段                                     |
| R5   | P0     | 长等待期间按轮询持续刷新（≤1 帧 / 5s）                                         |
| R6   | P0     | 终态清理 `detail`；失败仍以 `failed_list` + `error` 为准                        |
| R7   | P1     | 旧前端与查询链路兼容：无 `detail` 时行为不变                                    |
| R8   | P1     | PDF 去掉首帧盲等，进度尽早出现                                                  |

## 5. 范围与非目标

- 覆盖：导入链路的 PDF 转 Markdown、Markdown 图片识别、文档嵌入入库；ZIP 子任务经 `child-progress` 自动获得。
- 不做：任务取消 / 中止、任务详情回放、查询节点摘要、文档切分过程进度（CPU 秒级）、在线图片下载节点（另立需求）、前端交互 demo。
- 前端接入量：5 个文件（`types/app.ts`、`types/docs.ts`、`store/docsStore.ts`、`components/docs/ImportTaskItem.tsx`、`components/docs/ImportChildItem.tsx`），约 40 行。**旧前端不改可正常运行，但看不到新文案**；后端可先行交付并用 SSE 帧验收。

## 6. 验收要点

| 编号 | 验收项                                                                              |
| ---- | ----------------------------------------------------------------------------------- |
| A1   | 上传 24 页 PDF，SSE 连续帧出现上传 / 解析 12/24 / 下载文案，`done` 后 `detail` 消失 |
| A2   | 上传多图 md，出现「生成摘要 5/12」与上传进度文案                                    |
| A3   | ZIP 导入，子任务卡片收到带 `detail` 的 `child-progress`                             |
| A4   | 失败时 `failed_list` + `error` 正常，且无残留 `detail`                              |
| A5   | 旧前端页面节点名 / 状态 / 耗时展示不变                                              |
| A6   | 质量命令全绿（ruff / check_layout / check_layers / pytest）                         |

## 7. 评审纪要

| 日期 | 评审人 | 结论 / 补充 |
| ---- | ------ | ----------- |
|      |        |             |
