# Milvus DB 重构方案（minirag_docs / minirag_chunks）

> 状态：**预览稿（已并入第一轮评审），待确认**。本文档是基于 `docs/Milvus minirag_docs_meta db design.md` 原始设计，
> 结合现有代码实现（`milvus_client.py`、导入/查询链路）评审后的定案改动方案。
> 旧设计文档 `docs/milvus_db_design.md` 将在实施后标记为历史版本。

## 1. 背景与目标

现有两表以 `item_name`（主体名）为一级检索键：

- `minirag_item_name`：仅存 file_title / item_name / 双向量，信息量少；
- `minirag_chunks`：冗余 item_name，无文档级关联键，无 chunk 序号。

重构目标：

1. 一级索引从"主体名"升级为**文档**（`minirag_docs`），承载关键词、摘要、三份制品 URL 等元数据；
2. 切片通过 `doc_id` 与文档强关联（`minirag_chunks`）；
3. 表名映射：`minirag_item_name` → `minirag_docs`，`minirag_chunks` → `minirag_chunks`（名称不变，schema 变更）。

## 2. 决策记录（已与用户确认）

| 决策点 | 结论 |
| :--- | :--- |
| 文档主键 | 保持 Int64 自增（auto_id），插入后**查回 id** 再写 chunks |
| 文档向量规模 | 精简为两路：`keywords_sparse_vector` + `abstract_dense_vector` |
| confirm / suspect 对象 | 对象即**文档**（doc_id），展示用 `file_title`，而非关键词 |
| 旧数据 | 旧表**直接废弃**，不写迁移脚本 |
| keywords / abstract 来源 | **LLM 在导入时生成** |
| task_id 字段 | **采纳**：作为必选字段，用于无歧义查回 id 与溯源 |
| 导入节点合并 | `document_split` 之后的节点合并为单个 `node_document_embedding` |
| 一级召回范围 | `confirm_list` 是二级召回**唯一** doc_id 源；`suspect_list` 仅在 confirm 为空时终止流程并提示 |
| confirm 阈值 | 在旧值 0.8 基础上**适当放宽**（具体值待实测标定） |
| MinIO 制品 | 重导入时**递归清理**该文档在 MinIO 上的三份制品 |

## 3. 表结构定案

### 3.1 minirag_docs（文档级索引）

每篇文档一行，作为检索的"一级筛选器"。

| 字段名                 | 字段类型              | 说明                                                         |
| :--------------------- | :-------------------- | :----------------------------------------------------------- |
| id                     | INT64（自增主键）     | 文档唯一标识，auto_id 生成                                    |
| task_id                | VarChar(256)          | 导入批次唯一键（第一轮评审采纳）：无歧义查回 id 与溯源          |
| file_title             | VarChar(65535)        | 文档名称；重导入回退去重键（主去重键为 task_id）               |
| origin_file_url        | VarChar(65535)        | 原始上传文档的 Minio 链接（PDF / md / zip 分支中的 md）       |
| final_markdown_url     | VarChar(65535)        | 图片语法替换后的最终 markdown 的 Minio 链接                   |
| chunks_url             | VarChar(65535)        | chunks.json 的 Minio 链接                                    |
| docs_keywords          | VarChar(65535)        | LLM 生成，英文逗号分隔；稀疏向量编码源                        |
| docs_abstract          | VarChar(65535)        | LLM 生成，文档摘要；稠密向量编码源                            |
| keywords_sparse_vector | SparseFloatVector     | docs_keywords 的稀疏向量（术语精确匹配）                      |
| abstract_dense_vector  | FloatVector(1024)     | docs_abstract 的稠密向量（语义模糊匹配），维度随 `EMBEDDING.dense_dimension` |

相对原始设计的变更：

- **删除** `keywords_dense_vector`、`abstract_sparse_vector`（关键词天然配稀疏、摘要天然配稠密，与现有双路混合检索对齐）；
- **新增** `task_id`（已采纳，规避查回 id 歧义，见 §4.2）。

### 3.2 minirag_chunks（切片级索引）

检索的"精准匹配层"，通过 `doc_id` 关联文档。

| 字段名                | 字段类型          | 说明                                                         |
| :-------------------- | :---------------- | :----------------------------------------------------------- |
| id                    | INT64（自增主键） | 切片全局唯一标识，auto_id 生成                                |
| doc_id                | INT64             | 指向 `minirag_docs.id`，chunk 来源文档                       |
| file_title            | VarChar(65535)    | 冗余快照：Milvus 无 join，召回结果自带标题（docs 侧为准）     |
| chunk_index           | INT64             | 当前 chunk 在文档中的序号，从 0 开始；(doc_id, chunk_index) 内唯一，靠写入侧保证 |
| chunk_content         | VarChar(65535)    | 切片文本（含标题层级）；与 `max_chunk_size`(当前 1000) 隐性耦合，调大超过 65535 会插入失败 |
| content_dense_vector  | FloatVector(1024) | 切片语义向量，维度随 `EMBEDDING.dense_dimension`              |
| content_sparse_vector | SparseFloatVector | 切片关键词向量                                                 |

相对现状的变更：

- **删除** `item_name` 字段（由 doc_id 取代）；
- **新增** `doc_id`、`chunk_index`。

### 3.3 索引参数（沿用现状）

| 表 | 向量字段 | index_type | metric_type | 参数 | 索引名 |
| :--- | :--- | :--- | :--- | :--- | :--- |
| minirag_docs | abstract_dense_vector | HNSW | COSINE | M=64, efConstruction=100 | abstract_dense_index |
| minirag_docs | keywords_sparse_vector | SPARSE_INVERTED_INDEX | IP | DAAT_MAXSCORE | keywords_sparse_index |
| minirag_chunks | content_dense_vector | HNSW | COSINE | M=64, efConstruction=100 | content_dense_index |
| minirag_chunks | content_sparse_vector | SPARSE_INVERTED_INDEX | IP | DAAT_MAXSCORE | content_sparse_index |

备注：docs 表数据量小（每文档一行），可评估 dense 改 FLAT 暴力检索省内存（待评估，非阻塞项）。

## 4. 导入链路变更

当前顺序：`entry → (pdf_to_md / standalone_md / md_zip) → md_img → document_split → item_name → chunks_vect`

变更后顺序：`entry → (pdf_to_md / standalone_md / md_zip) → md_img → document_split → node_document_embedding → END`

即 `document_split` 之后的全部节点（原 `node_item_name_vect` + `node_chunks_vect` + 新增 MinIO 制品上传）
**合并为单个节点 `node_document_embedding`**（第一轮评审采纳）。合并后 `doc_id` 在节点内内存传递，
无需写入 state —— 原跨节点方案中的 `doc_id` state 字段作废，导入 state 无需新增字段。

### 4.1 三份制品上传 MinIO（含递归清理）

- 将原始文件、最终 markdown、chunks.json 上传 MinIO，得到三个 URL 供 docs 行使用；
- 目前只有图片走 MinIO，这三份制品是本方案**新增的存储步骤**；桶为 public-read 策略，URL 公开可读（隐私敏感文档需评估）；
- **重导入时先递归清理**该文档在 MinIO 上的三份制品目录（复用 `clear_dir_if_exist` 按前缀递归删除；
  前缀命名必须包含 `task_id`，避免误删其他文档制品；图片目录由 `node_md_img` 前置清理）。

### 4.2 node_document_embedding 节点内部步骤

1. LLM 生成 `docs_keywords`（英文逗号分隔）+ `docs_abstract`（新 prompt；可合并为一次结构化输出）；
2. 向量化：keywords → sparse、abstract → dense；chunks 按现有分批 + 线程池逻辑批量向量化；
3. 插入 `minirag_docs`（auto_id，无返回主键；携带 task_id / file_title / 三个 URL / keywords / abstract / 双向量）；
4. **查回 id**：`query(filter="task_id == '...'", output_fields=["id"])`，按 **id 降序取第一条**（task_id 已采纳，查询无歧义；降序兜底规避 Milvus delete 延迟可见）；
5. 插入 `minirag_chunks`：携带 `doc_id` + `chunk_index`（按 chunks.json 顺序 enumerate）。

### 4.3 重导入删除顺序（单节点内串行）

```
1. 查旧 doc_id（按 task_id 过滤）
2. 递归清理 MinIO 上该文档三份制品目录（§4.1）
3. 删 chunks（doc_id == X；查不到旧 id 时回退按 file_title 删）
4. 删 docs（id == X）
5. 上传新三份制品 → 得到新 URL
6. 插 docs（新行，自增 id 变化）→ 查回新 id
7. 插 chunks（携带新 doc_id）
```

说明：因自增 id 在重导入后变化，旧 chunks 的 `doc_id` 必然失效，故必须先删后插；
各步均为幂等操作（delete / upload / insert），中途失败再次导入即可恢复。

## 5. 查询链路变更

### 5.1 一级召回（docs）

- `hybrid_search_item_name` → `hybrid_search_docs`；
- 两路混合：`abstract_dense_vector`(COSINE) + `keywords_sparse_vector`(IP)；
- `output_fields`：`file_title`（+ `docs_abstract` 供展示）。

### 5.2 confirm / suspect 角色划分（第一轮评审定案）

- `confirm_list` / `suspect_list` 从"主体名字符串"改为 **doc id 列表**（`list[int]`），展示用 `file_title`，需保留 doc_id → file_title 映射；
- **`confirm_list` 是二级召回的唯一定位源**：只有确认文档参与 chunks 向量检索范围（`doc_id in [...]`），疑似文档不参与检索；
- **confirm 阈值适当放宽**：因疑似文档不参与二级召回，一级确认阈值在旧值 0.8 基础上放宽（具体值待实测标定），
  换取召回覆盖率、避免漏检；放宽引入的噪声由二级混合检索 + RRF + rerank 兜底；
- **`suspect_list` 唯一作用**：当 `confirm_list` 为空时，**终止查询流程**并返回提示：
  "文库暂无内容与您的查询内容匹配，可能相关的文档有《file_title》《file_title》…"（走 state.answer 短路，同现状实现）；
- 阈值 `item_name_confirm_threshold` / `item_name_suspect_threshold` 均为旧双路信号标定值，换信号后**需实测重标定**（TODO）。

### 5.3 二级召回（chunks）

- 检索范围严格限定为 `confirm_list` 中的确认文档：过滤条件 `item_name in ['a','b']` → **`doc_id in [1,2]`**（数值过滤，不带引号）；
- `output_fields`：`doc_id`、`file_title`、`chunk_index`、`chunk_content`。

### 5.4 检索函数重构

- `_minirag_hybrid_search` 中 `anns_field` 硬编码（现为 item_name 字段常量，代码已有 TODO 注释）→ 改为 `dense_field` / `sparse_field` 入参，两表共用；
- `app_config` 中 `item_name_*` 配置名 → `docs_*`（`item_name_recall_limit`、`item_name_hybrid_weight` 等）。

## 6. 旧数据废弃策略

- Milvus 不支持 rename，直接 drop `minirag_item_name`，`minirag_chunks` 因 schema 变更一并重建；
- `docs/setup.md` 连通性检查改为 `minirag_docs` / `minirag_chunks`；
- `docs/milvus_db_design.md` 标记为历史版本。

## 7. 代码变更清单

| 文件 | 变更 |
| :--- | :--- |
| `src/common/config/env_config.py` | `collection_item_name` → `collection_docs`（默认值 `minirag_docs`） |
| `src/common/client/milvus_client.py` | 字段/索引/类型常量重构；新增 `hybrid_search_docs`；改造 `hybrid_search_chunks`；`_minirag_hybrid_search` 支持传参 anns_field；`prepare_docs_collection` / `prepare_chunks_collection` 新 schema |
| `src/processor/import_processor/nodes/node_document_embedding.py`（新） | 合并原 `node_item_name_vect.py` + `node_chunks_vect.py`：三份制品上传/递归清理、keywords/abstract LLM 生成、docs 写入 + 查回 id、chunks 向量化 + 写入 |
| `src/processor/import_processor/state.py` | 无必改项（合并后 doc_id 无需跨节点传递）；可选清理 `item_name` 残留字段 |
| `src/processor/import_processor/main_graph.py` | 合并节点接线；`MdTailOutput` 移除 `item_name` |
| `src/common/client/minio_client.py` | 新增三份制品目录的递归清理/上传辅助方法（前缀含 task_id） |
| `src/processor/query_processor/nodes/node_intent_recognize.py` | confirm/suspect 文档粒度改造 |
| `src/processor/query_processor/nodes/node_search_embedding.py` / `node_search_hyde.py` | doc_id 过滤 |
| `src/common/config/app_config.py` | 配置改名 + 阈值重标定 |
| `src/common/prompt/` | 新增 keywords/abstract 生成 prompt |
| `docs/setup.md` | 集合名更新 |

## 8. 风险与注意事项

1. **查回 id 竞态**：Milvus delete 非即时可见 → 已按 `task_id` 过滤 + id 降序兜底；
2. **MinIO 递归清理误删**：三份制品目录前缀必须包含 `task_id`，避免同名文档/多文档共享目录时误删他人制品；
3. **合并节点长链路幂等**：`node_document_embedding` 串行 7 步，中途失败需可重跑 —— 各步均为 delete/upload/insert 幂等操作，再次导入即可恢复；
4. **confirm 阈值放宽的副作用**：放宽后确认文档可能增多，二级召回范围变大，需靠 `chunks_recall_threshold`(0.55) 与 rerank 兜底，建议实测对比后定值；
5. **MinIO 公开可读**：三个 URL 为公开链接，隐私敏感文档需评估；
6. **LLM 成本**：每篇文档新增 keywords/abstract 生成（注意 `LLM_RPM=500` 限流）；zip 扇出多分支并发时放大；
7. **chunk_content 上限**：VarChar(65535) 与 `max_chunk_size` 配置隐性耦合；
8. **同名文件互踩**（既有问题，本方案暂沿袭）：不同文件同名会互相覆盖，`task_id` 可支撑将来的文档唯一键优化。

## 9. 评审记录

| 轮次 | 变更 |
| :--- | :--- |
| 第一轮（用户） | ① 采纳 `task_id` 字段；② 重导入需递归清理 MinIO 三份制品；③ `document_split` 之后的节点合并为 `node_document_embedding`；④ `confirm_list` 作为二级召回唯一 doc_id 源、confirm 阈值适当放宽，`suspect_list` 仅在 confirm 为空时终止流程并提示"文库暂无内容与您的查询内容匹配，可能相关的文档有《》…" |
