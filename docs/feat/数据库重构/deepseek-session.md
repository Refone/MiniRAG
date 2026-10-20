# 会话归档：Milvus 数据库重构需求

> 归档日期：2026-10-20
> 需求状态：✅ 已完成（代码实现 + 真库验证通过，阈值/权重标定与全链路实测遗留）
> 会话模型：DeepSeek（deepseek-session）
> 关联文档：本目录下 `Milvus minirag_docs_meta db design.md`（原始设计）、`Milvs DB Refactor.md`（重构定案）、`milvus_db_design.md`（旧设计，历史版本）

---

## 一、需求概述

重构 Milvus 向量数据库两张表，承载更多更清晰的数据：

- `minirag_item_name`（主体名索引）→ `minirag_docs`（文档级索引：task_id / 制品 URL / 关键词 / 摘要 / 双向量）
- `minirag_chunks` → `minirag_chunks`（名称不变，schema 变更：doc_id 关联 + chunk_index + 内容双向量）

## 二、会话时间线

### 第 1 轮 · 新表设计评审

用户要求先评判 `docs/Milvus minirag_docs_meta db design.md` 中的新表设计。

评审结论——**3 个严重问题**：

1. `doc_id` 关联与"自增主键"互相矛盾：auto_id 模式下插入拿不到主键，查回有竞态，重导入后 id 漂移导致旧 chunks 失联；
2. 删除 `item_name` 是查询链路语义级变更（confirm/suspect 展示、chunks 过滤、阈值标定都要重设计），文档未覆盖；
3. docs 表 4 个向量字段使检索复杂度/成本/代码改动全部翻倍（关键词天然配稀疏、摘要天然配稠密）。

另有若干 P1（迁移方案、file_title 去重脆弱、URL 新存储步骤、chunk 上限耦合、索引参数缺失等）。

**用户决策**（问答确认）：① 保持自增主键、插入后查回 id；② 向量精简为 `keywords_sparse + abstract_dense`；③ confirm/suspect 对象即文档；④ 旧表直接废弃；⑤ keywords/abstract 由 LLM 导入时生成。

### 第 2 轮 · 方案文档预览

创建 `docs/Milvs DB Refactor.md` 改动方案预览稿（8 个部分：决策记录 / 表结构定案 / 导入链路 / 查询链路 / 废弃策略 / 代码清单 / 风险 / 评审记录）。

### 第 3 轮 · 第一轮评审（用户 4 点）

① **采纳 `task_id` 字段**（无歧义查回 id 与溯源）；② 重导入需**递归清理 MinIO** 三份制品；③ `document_split` 之后的节点**合并为 `node_document_embedding`**；④ 召回逻辑定案：`confirm_list` 为二级召回唯一 doc_id 源、阈值可适当放宽；`suspect_list` 唯一作用是 confirm 为空时终止流程，提示"文库暂无内容与您的查询内容匹配，可能相关的文档有《》《》…"。

### 第 4 轮 · 第二轮评审

同名文件覆盖明确为：**先完整删除**（MinIO 制品 + chunks + docs），**后插入新文档**，删除全部完成前不做任何新写入。

### 第 5 轮 · 开始实现

按方案文档完成全部代码改造，并在真实服务上验证：

- **配置**：`collection_docs`、`docs_*` 参数（确认阈值放宽至 0.75）、MinIO 三个制品目录；
- **milvus_client**：docs/chunks 新 schema 与索引、`hybrid_search_docs`、`hybrid_search_chunks(doc_ids)`、`_minirag_hybrid_search` 的 `anns_field` 参数化（消除旧 TODO）、文档级增删查辅助（`query_doc_rows_by_file_title` / `query_doc_id` / 三个 delete）；
- **minio_client**：`doc_artifact_prefix` + `clear_doc_artifacts`（尾斜杠前缀防误删）；
- **导入链路**：新建 `node_document_embedding.py`（同名覆盖先删后插 → 三份制品上传 → LLM 元数据 → 双向量化 → 插 docs 取 id → 插 chunks），删除旧两节点；
- **查询链路**：confirm/suspect 改 doc id 列表 + `doc_titles` 展示映射，chunks 过滤改 `doc_id in [...]`；
- **文档**：setup.md / architecture.md / milvus_db_design.md（历史标记）/ web types.ts 同步。

**实现中发现的两个偏差**（已回写方案文档 §4.2）：
1. pymilvus 3.x 的 insert 实际会返回生成主键（`ids`），改为优先直接使用、task_id 查回兜底；
2. 查询辅助方法加 `consistency_level="Strong"`——Bounded 一致性有延迟可见窗口（冒烟测试实测复现）。

**真库操作**：废弃旧表 drop `minirag_item_name`（9 行）、旧 schema `minirag_chunks`（908 行）；`minirag_docs` 已存在且 schema 与设计一致，复用；`minirag_chunks` 按新 schema 重建。

**验证**：compileall 全绿；两张图编译正常；后端启动自检 4 项硬依赖全通过；真库闭环冒烟（插入取 id → 查回 → chunks 数值过滤 → 同名覆盖完整删除 → MinIO 幂等清理）通过。

### 第 6 轮 · reset_db.py 修复

用户运行 `tools/reset_db.py` 报 `AttributeError: 'MilvusSettings' object has no attribute 'collection_item_name'`。原因是此前排查残留引用只覆盖了 src/docs/web，遗漏 tools/。修复两处引用并全仓库补漏。`test/` 目录按 AGENTS.md 约定未改动（旧节点名测试引用保留，默认不收集）。

### 第 7 轮 · "Agent 检索不到"问题修复

用户反馈：minirag_docs 中关键词含 "Agent" 的文档，查询 "Agent 和 Workflow 有什么区别？" 匹配不到。日志定位：`识别出的检索线索: []` —— LLM 线索提取返回空后一级召回被短路，Milvus 检索根本没执行。根因：`step_4` 复用的旧"询问主体"prompt 明确排除话题词（"Agent"/"Workflow" 正是话题词）。

修复：新 prompt 提取"实体 + 主题/概念词"两类线索 + 完整查询兜底。真库实测：`["Agent", "Workflow"]` 命中目标文档 **0.8583**（>0.75 阈值），兜底完整查询 **0.8417**。

### 第 8 轮 · 一级召回简化（用户决策）

用户期望：**直接拿重写查询匹配 docs 双向量，不做多余的线索总结**。移除 LLM 线索提取步骤（删除 `prompt_doc_queries_of_query.py` 与 `doc_queries` 状态字段），`hybrid_search_docs(texts=[rewritten_query])` 直接检索。历史上下文由查询重写步骤融入。

### 第 9 轮 · doc_titles 字段 Q&A

用户询问 `QueryGraphState.doc_titles` 的意义、可否删除。结论：它是 doc_id → file_title 展示映射，仅 `node_intent_recognize` 自己生产自己消费（无确认文档时的终止提示语），无其他节点读取 → **从 state 删除**，本地变量保留。

### 第 10 轮 · 关键词收敛（黑名单方案）

用户反馈 docs 关键词总结太宽泛（"产品安全手册"、"安全警告"、"操作规范"、"用户指南"、"笔记本电脑"等大类词），使一级召回失去区分度。方案：prompt 改为"文档指纹"原则（3-5 个、禁三类宽泛词、宁缺毋滥）+ `filter_broad_keywords` 黑名单后处理（精确黑名单 + 文档类型后缀规则，全滤掉回退 file_title）。用库中真实关键词实测过滤效果（hak180 6→3、华为 7→5、hello-agent 全保留）。

### 第 11 轮 · 否决黑名单（用户决策）

用户指出：**黑名单方式是糟糕的方式**——穷举不完，且需要过滤的词总是事后才发现（信息已落库）。移除 `filter_broad_keywords` 与全部黑名单常量，keywords 收敛**只保留 prompt 约束**（文档指纹原则 + "换一篇同类文档大概率不会出现"自检规则），宁可效果弱一点。

### 第 12 轮 · 稠密/稀疏权重机制 Q&A

用户询问一级召回中稠密与稀疏向量对最终分数的影响。结论（机制 + 真库实测）：

- 融合公式：最终分 = **0.3 × 稠密归一化分 + 0.7 × 稀疏归一化分**（`docs_hybrid_weight=(0.3, 0.7)`，融合前各字段距离归一化到 [0,1]）；
- 实测拆解（"Agent 和 Workflow 有什么区别？"）：稀疏路只有 hello-agent 命中（IP=2.898），稠密路全部文档有平滑信号（0.18~0.43）；融合后 hello-agent 0.840 一骑绝尘，其余 0.18~0.19；
- **稀疏路是"门槛"**（权重 0.7，关键词 token 重叠才命中），**稠密路是"兜底/微调"**（权重 0.3，贡献上限 0.3）——因此当前 0.75 阈值下，仅语义相似、无关键词重叠的文档理论上过不了确认线；
- 调参旋钮：提高稠密权重（如 0.5/0.5）或降低阈值可放开纯语义召回；维持 0.3/0.7 则保持严格关键词门槛定位。

### 第 13 轮 · 需求归档（本轮）

创建 `docs/feat/数据库重构/` 归档目录，移入三份数据库设计文档，导出本会话为 `deepseek-session.md`。

## 三、关键决策记录总表

| # | 决策 | 出处 |
| :--- | :--- | :--- |
| 1 | docs 主键保持 Int64 自增；实现上优先用 insert 返回的 `ids`，`task_id` 查回兜底（Strong 一致性） | 第 1 轮 + 第 5 轮 |
| 2 | docs 向量精简为 `keywords_sparse_vector` + `abstract_dense_vector` 两路 | 第 1 轮 |
| 3 | confirm/suspect 对象为文档（doc_id），展示用 file_title | 第 1 轮 |
| 4 | 旧表直接废弃，不写迁移脚本 | 第 1 轮 |
| 5 | keywords/abstract 由 LLM 导入时生成 | 第 1 轮 |
| 6 | 采纳 `task_id` 字段（批次唯一键，查回与溯源） | 第 3 轮 |
| 7 | `document_split` 之后合并为单节点 `node_document_embedding` | 第 3 轮 |
| 8 | `confirm_list` 为二级召回唯一 doc_id 源；confirm 阈值放宽至 0.75（待标定）；suspect 仅用于终止提示 | 第 3 轮 |
| 9 | 重导入递归清理 MinIO 三份制品（前缀含 task_id） | 第 3 轮 |
| 10 | 同名覆盖：先完整删除（MinIO + chunks + docs），后插入新文档 | 第 4 轮 |
| 11 | 一级召回直接使用重写后的完整查询，无 LLM 线索提取 | 第 8 轮 |
| 12 | `doc_titles` 不入 state（仅 intent_recognize 内使用） | 第 9 轮 |
| 13 | keywords 收敛只靠 prompt（文档指纹原则），**否决黑名单方式** | 第 11 轮 |

## 四、实现变更清单（代码）

| 文件 | 变更 |
| :--- | :--- |
| `src/common/config/env_config.py` | `collection_docs`（minirag_docs）；MinIO 新增 origin-files / final-markdowns / chunks-json 目录 |
| `src/common/config/app_config.py` | `item_name_*` → `docs_*`；`docs_confirm_threshold=0.75`（放宽，待实测标定） |
| `src/common/client/milvus_client.py` | 重写：docs/chunks 新 schema 与索引；`hybrid_search_docs`；`hybrid_search_chunks(doc_ids)`；`_minirag_hybrid_search` anns_field 参数化；文档级增删查辅助（Strong 一致性 + filter 转义） |
| `src/common/client/minio_client.py` | `doc_artifact_prefix` + `clear_doc_artifacts` |
| `src/common/prompt/prompt_doc_keywords_abstract.py` | 新增：keywords/abstract 生成 prompt（文档指纹原则，无黑名单） |
| `src/processor/import_processor/nodes/node_document_embedding.py` | 新增：合并节点（同名覆盖先删后插 + 制品上传 + LLM 元数据 + 双表写入） |
| `src/processor/import_processor/nodes/node_item_name_vect.py` / `node_chunks_vect.py` | 删除 |
| `src/processor/import_processor/{state,main_graph,nodes/__init__}.py` | 移除 item_name；子图接线 `md_img → document_split → document_embedding` |
| `src/processor/query_processor/state.py` | `doc_queries` / `doc_titles` 不入 state；confirm/suspect 为 doc id 列表 |
| `src/processor/query_processor/nodes/node_intent_recognize.py` | 一级召回直接用 rewritten_query；文档粒度 confirm/suspect；终止提示语 |
| `src/processor/query_processor/nodes/node_search_embedding.py` / `node_search_hyde.py` | `doc_ids` 过滤 |
| `src/api/setup.py` | `prepare_docs_collection` / `prepare_chunks_collection` |
| `tools/reset_db.py` | 集合名与方法名同步 |
| `web/src/lib/types.ts` | 移除废弃 `item_names` 字段 |
| `docs/setup.md` / `docs/architecture.md` | 集合名、管线图与节点清单同步 |

## 五、验证记录

- `compileall` 全绿；导入/查询图编译正常；后端启动自检 4 项硬依赖全通过；
- 真库闭环冒烟：docs 插入取 id → task_id 查回 → chunks 写入 → `doc_id in [...]` 过滤 → 同名覆盖完整删除（含"同名两批次并存"场景清理）→ MinIO 幂等清理；
- 真实数据实验 1（Agent 召回）：完整查询命中目标文档 **0.8417** > 0.75 阈值；
- 真实数据实验 2（权重拆解）：稀疏路仅关键词重叠文档命中（IP=2.898），稠密路全库平滑（0.18~0.43），融合分 0.840 vs 其余 ≤0.19；
- 关键词过滤实测（黑名单方案期间，后按用户要求移除）：hak180 6→3、华为 7→5、hello-agent 全保留。

## 六、遗留事项

1. **阈值/权重重标定**：`docs_confirm_threshold=0.75` 与 `docs_hybrid_weight=(0.3, 0.7)` 均为初值，建议积累 20~50 条真实查询后实测标定（方案文档 TODO）；
2. **存量 docs 行**：库中已导入文档的关键词为旧 prompt 产物，需重新导入才生效；
3. **端到端实测**：未擅自跑全链路（LLM/Embedding 配额 + 真实数据写入），建议手动导入一个 md 试跑；
4. **test/ 未同步**：旧节点名的单元测试（`node_item_name_vect_test.py` 等）引用已删除模块，按 AGENTS.md 约定未改动，默认不收集；
5. **关键词收敛效果待观察**：仅 prompt 约束（无黑名单），若生成质量仍不足，下一步可考虑召回侧权重/阈值调整。

## 七、归档目录说明

```
docs/feat/数据库重构/
├── Milvus minirag_docs_meta db design.md   # 原始新表设计（用户手写）
├── Milvs DB Refactor.md                    # 重构定案方案（经两轮评审 + 实现备注）
├── milvus_db_design.md                     # 旧表设计（历史版本）
└── deepseek-session.md                     # 本会话归档（即本文件）
```
