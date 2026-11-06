# query_graph / import_graph 流程图

依据 `backend/graphs/` 当前实现绘制（Archify workflow v2）。每个节点的主文本是**节点功能**，副文本是**节点入口函数**（`@trace_node` 包装的函数名）。

> 系统级架构见 [docs/architecture.md](../../docs/architecture.md)；本文件只记录图与节点级细节。

## 文件

| 文件                             | 说明                                                                                                              |
| -------------------------------- | ----------------------------------------------------------------------------------------------------------------- |
| `query-graph-flow.html`          | 查询图交互版：明暗主题、搜索、聚焦、关系追踪、动态轨迹、导出                                                      |
| `query-graph-flow.animated.svg`  | 查询图独立 SVG：箭头流动动画（CSS 虚线流动 + SMIL 沿路径箭头）                                                    |
| `import-graph-flow.html`         | 导入图交互版                                                                                                      |
| `import-graph-flow.animated.svg` | 导入图独立 SVG，同上                                                                                              |
| `*-graph-flow.json`              | Archify 规格源文件，可直接重新生成                                                                                |
| `tools/`                         | 生成链脚本：`adjust-frames.py`（去框/裁切）、`export-svg.mjs`（导出 canonical SVG）、`animate-svg.py`（叠加动画） |

排版约定：

- 隐藏泳道底框与 `01/02/03` 链路标签；隐藏图例（`meta.legend.mode = hidden`）；所有连线统一样式（不再高亮主链路）。
- 画布按内容裁切（viewBox 收紧到节点/连线/子图框的实际包围盒），底板网格同步裁切。
- 规格里的 lane 标签只参与排版（产物中已隐藏），保持短名，避免 Archify 的 lane-header 位移把图整体推宽。
- 查询图：HyDE / 联网两支从意图节点上、下两侧对称扇出，由**左侧**进入 `node_search_hyde` / `node_search_web`，再对称汇入 RRF。
- 导入图：入口节点向上、右、下三向扇出；独立 md / 压缩包两支由**左侧**进入支路，PDF 直连，最终汇入 `md_tail` 子图；子图用虚线框标出。

SVG 自带明暗主题（跟随 `prefers-color-scheme`），动画由两层叠加：边线上的流动虚线（CSS `stroke-dashoffset`）与沿边线移动的小箭头（SMIL `animateMotion`）。

## 查询图结构

查询图以 `node_intent_recognize` 为入口（`set_entry_point`），单入口单出口：

- `node_intent_recognize` 后由 `after_node_intent_recognize` 条件扇出：必定进入 `node_search_embedding`，`enable_hyde` / `enable_web_search` 为真时追加对应节点；返回节点名列表，三路在同一 superstep 并行。
- 三路分别写 `embedding_recalls` / `hyde_recalls` / `web_matches`，统一汇入 `node_rrf_and_rerank`（RRF 只融合文库两路，联网结果直接进精排）。
- `node_rrf_and_rerank` → `node_answer_output` → END；答案不写回 state，只经 SSE 推 `DELTA` / `FINAL` 并落库。

| 主文本             | 入口函数                | 写入 state                                                          |
| ------------------ | ----------------------- | ------------------------------------------------------------------- |
| 意图识别与查询改写 | `node_intent_recognize` | `rewritten_query`、`confirm_list`、`suspect_list`、`suspect_titles` |
| 文档内向量召回     | `node_search_embedding` | `embedding_recalls`                                                 |
| 假设性答案召回     | `node_search_hyde`      | `hyde_recalls`                                                      |
| 联网搜索补充       | `node_search_web`       | `web_matches`                                                       |
| RRF 融合与精排     | `node_rrf_and_rerank`   | `rerank_results`                                                    |
| 生成答案并推流     | `node_answer_output`    | 仅 `token_meter`                                                    |

## 导入图结构

`node_entry` 校验文件并按 `origin_file_type` 分叉；三条链路最终都进入 `md_tail` 子图。

- PDF：`node_pdf_to_md`（MinerU）→ `md_tail`。
- 独立 md：`node_process_standalone_md`（下载在线图片、重写地址）→ `md_tail`。
- md 压缩包：`node_process_md_zip`（解压、防 zip-slip、图片完整性）→ `node_md_fork`（物化 `md_children`）→ 按 md 数 `Send` 到 `node_md_tail`，每个 md 独立 state。
- `md_tail` 子图：`node_md_img` → `node_document_split` → `node_document_embedding` → END，由 `node_md_tail_branch` 包装并收口子任务的 complete / failed。

| 主文本            | 入口函数                     | 关键产出                         |
| ----------------- | ---------------------------- | -------------------------------- |
| 识别文件类型      | `node_entry`                 | `origin_file_type`、`file_title` |
| PDF 转 Markdown   | `node_pdf_to_md`             | `markdown_file_path`             |
| 整理独立 Markdown | `node_process_standalone_md` | `markdown_file_path`             |
| 解压并校验压缩包  | `node_process_md_zip`        | `markdown_file_paths`            |
| 拆分 md 子任务    | `node_md_fork`               | `md_children`                    |
| 图片识别与替换    | `node_md_img`                | 修正后的 `markdown_file_path`    |
| 按标题递归切分    | `node_document_split`        | `chunks_json_path`               |
| 嵌入并写入向量库  | `node_document_embedding`    | docs / chunks 两表 + MinIO 制品  |

## 重新生成

在仓库根目录执行：

```shell
# 1) 由规格生成基础 HTML（Archify 9/9 校验）
node ~/.agents/skills/archify/bin/archify.mjs deliver workflow assets/archify/query-graph-flow.json assets/archify/query-graph-flow.html --quality showcase
node ~/.agents/skills/archify/bin/archify.mjs deliver workflow assets/archify/import-graph-flow.json assets/archify/import-graph-flow.html --quality showcase

# 2) 去泳道框/链路标签、画 md_tail 虚线框、按内容裁切
python assets/archify/tools/adjust-frames.py assets/archify/query-graph-flow.html --crop
python assets/archify/tools/adjust-frames.py assets/archify/import-graph-flow.html --boundary md_img,split,embedding "md_tail 子图" --crop

# 3) 从 HTML 导出 canonical SVG，再叠加流动动画
node assets/archify/tools/export-svg.mjs "$PWD/assets/archify/query-graph-flow.html" /tmp/archify-svg-q
node assets/archify/tools/export-svg.mjs "$PWD/assets/archify/import-graph-flow.html" /tmp/archify-svg-i
python assets/archify/tools/animate-svg.py /tmp/archify-svg-q/query_graph.svg assets/archify/query-graph-flow.animated.svg
python assets/archify/tools/animate-svg.py /tmp/archify-svg-i/import_graph.svg assets/archify/import-graph-flow.animated.svg
```

- 第 2 步是必需的后处理：Archify 的 lane 无法在规格里关闭，子图框与画布裁切也在这一步完成。
- 第 3 步通过 viewer 的 `Archify.exportMenu.run('svg')` 导出 canonical SVG（含明暗主题），动画层由 `animate-svg.py` 叠加。
- `animate-svg.py` 依赖 `lxml`（项目 `.venv` 未内置）：先 `uv pip install lxml`，或改用任意带 `lxml` 的 Python 解释器执行；`adjust-frames.py` 只用标准库。
- 验收：交付时已通过 Archify 9/9 与 `visual-check`（1440×900 / 1600×1000 / 1920×1080 / 2048×1320，明暗两套）；验收截图未随仓库保留，如需复查执行 `node ~/.agents/skills/archify/bin/archify.mjs visual-check assets/archify/<file>.html`。
