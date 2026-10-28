# SSE 节点摘要推送设计（P2 预研）

> 目标：任务状态卡从「只有节点名」升级为「节点名 + 一行业务摘要」。
> 结论：**可行**。不需要新增 SSE 事件类型，扩展现有 `progress` 载荷即可；主要工作量在「节点上报摘要」和「前端兼容渲染」。
> 关联：`节点可观测数据统计.md` 的 G1（progress 不带业务数据）、G4（查询终态不推最终快照）、G6（无节点耗时/序号）。

---

## 1. 目标效果

### 1.1 查询任务

```text
阶段进度（进行中：融合排序）
  意图识别：HAK 180 产品安全手册              1.8s
  向量化查询：最高得分 0.83                   0.9s
  HyDE 搜索：最高得分 0.79                    1.2s
  互联网搜索：4 条结果                        0.4s
  融合排序：保留 3 条 · Top1 0.91             2.1s
  答案输出：生成回答中…
```

失败时：

```text
  融合排序：失败 · rerank 请求超时
```

### 1.2 导入任务

```text
识别文档类别：PDF · HAK 180 产品安全手册
PDF 转 Markdown：23 页 · 转换完成
Markdown 图片识别：12 张图片
文档切分：87 个切片
文档嵌入入库：doc_id 7 · 87 个切片
```

多 md 压缩包（同一节点多分支）：

```text
Markdown 图片识别（HAK180）：12 张图片
Markdown 图片识别（RS12）：8 张图片
```

### 1.3 设计原则

| 原则 | 说明 |
| --- | --- |
| 后端生产摘要 | 摘要由节点根据业务数据生成，前端不拼业务语义 |
| 单行可读 | 每行一个节点，`节点名：摘要`，长文本截断 |
| 快照优先 | 继续用 `progress` 快照，断线/重连/重复渲染都不会错序 |
| 向后兼容 | 保留 `done_list/running_list`，新增字段为可选 |
| 不传大文本 | 只传摘要和少量指标，不传 chunk 全文、prompt、abstract |
| 失败不阻塞 | 摘要生成失败只丢摘要，不影响节点执行和任务结果 |

---

## 2. 可行性判断

### 2.1 当前链路

| 层 | 现状 | 是否阻塞 |
| --- | --- | --- |
| SSE 传输 | `sse_utils` 支持任意 JSON，事件类型固定 6 种 | 不阻塞 |
| `progress` 载荷 | `{status, done_list, running_list}` | **阻塞**：没有业务字段 |
| 节点追踪 | `trace_node` 只记录 running/done 与耗时 | 部分阻塞：没有摘要入口 |
| 节点数据 | 大部分在 state、局部变量或日志里 | 需要补“上报”动作 |
| 前端类型 | `ProgressView` 只有 done/running/status | 需要加可选字段 |
| 前端渲染 | `QueryProgress` / `ImportTaskItem` 只渲染节点名 | 需要加摘要行 |

### 2.2 关键结论

1. **协议层完全可行**：SSE 是文本流，`progress.data` 加字段即可，不需要新事件、不需要改 nginx。
2. **数据层需要少量改造**：部分摘要可从返回值/state 直接算；页数、图片数、chunk 数、doc_id 以及意图识别的文档标题目前只在局部变量或日志里，需要节点显式上报。
3. **前端改动小**：`StatusLog` 已经支持「状态图标 + 文本行」，只需把文本从「节点名」换成「节点名：摘要」，旧载荷回退即可。
4. **不需要数据库变更**：摘要只存在于任务内存快照和 SSE，不落库。

### 2.3 不建议的做法

| 做法 | 问题 |
| --- | --- |
| 把摘要拼进 `done_list` 字符串 | 破坏节点标识；旧前端会显示整句；前端无法区分节点名/摘要 |
| 新增 `node` 事件只发增量 | 需要前端维护节点状态、处理乱序/重连/重复；当前只有 13 个节点，快照足够 |
| 前端解析日志 | 日志不是 SSE 数据源；多 worker/文件关闭时不可靠 |
| 把完整 state 塞进 SSE | 包含 chunk 全文、prompt，体积与隐私都不可控 |

---

## 3. 方案对比

| 方案 | 载荷 | 优点 | 缺点 | 结论 |
| --- | --- | --- | --- | --- |
| A. 扩展 `progress` 快照 | 在现有字段旁加 `nodes[]` | 兼容、断线安全、前端改动最小 | 每次重发全量节点，分支多时体积上升 | **推荐** |
| B. 新增 `node` 增量事件 | `{key, status, summary}` | 单次载荷小 | 需要前端维护状态、乱序/重连处理；与现有快照并存易不一致 | 暂不采用 |
| C. `details` 按节点名映射 | `{details: {"意图识别": {...}}}` | 改动最小 | 中文名作 key，重名/多分支冲突；无顺序/状态 | 不推荐 |

> 如果后续出现高频中间状态（如逐张图片进度），再在方案 A 上增加 `node` 事件；当前单分支任务的节点级更新频率低（查询 6 个节点、导入 7 个节点，每个节点开始/结束各一次，≤26 次），快照足够。

---

## 4. 推荐协议

### 4.1 `progress` 事件示例

```json
{
  "status": "processing",
  "done_list": ["意图识别", "向量化查询"],
  "running_list": ["融合排序"],
  "nodes": [
    {
      "key": "node_intent_recognize",
      "name": "意图识别",
      "status": "done",
      "seq": 1,
      "cost_ms": 1834,
      "summary": "HAK 180 产品安全手册",
      "metrics": {
        "confirm_count": 1,
        "suspect_count": 0,
        "recall_count": 5
      }
    },
    {
      "key": "node_search_embedding",
      "name": "向量化查询",
      "status": "done",
      "seq": 2,
      "cost_ms": 912,
      "summary": "最高得分 0.83",
      "metrics": {
        "count": 20,
        "max_score": 0.83
      }
    },
    {
      "key": "node_rrf_and_rerank",
      "name": "融合排序",
      "status": "running",
      "seq": 5,
      "summary": null,
      "metrics": null
    }
  ]
}
```

### 4.2 字段定义

| 字段 | 类型 | 必有 | 说明 |
| --- | --- | --- | --- |
| `status` | string | 是 | 任务级状态，沿用 `pending/processing/complete/failed` |
| `done_list` | string[] | 是 | 已完成节点显示名，**保留兼容** |
| `running_list` | string[] | 是 | 运行中节点显示名，**保留兼容** |
| `nodes` | NodeProgress[] | 否 | 节点明细；旧服务没有该字段时前端回退 |
| `nodes[].key` | string | 是 | 稳定机器标识，取 `func.__name__` |
| `nodes[].name` | string | 是 | 中文显示名，取 `trace_node(desc=...)` |
| `nodes[].status` | string | 是 | `running/done/failed/skipped` |
| `nodes[].seq` | number | 是 | 节点启动序号，前端按此排序 |
| `nodes[].summary` | string/null | 否 | 单行摘要，≤60 字符；running 可为空 |
| `nodes[].metrics` | object/null | 否 | 小体量结构化指标，供后续详情使用 |
| `nodes[].cost_ms` | number/null | 否 | 节点耗时；running 时为 null |
| `nodes[].branch` | string/null | 否 | 导入多 md 分支标识（`file_title`） |
| `nodes[].error` | string/null | 否 | 失败原因，截断到 200 字符 |

### 4.3 生成规则

| 规则 | 说明 |
| --- | --- |
| 摘要长度 | 建议 ≤60 字符；超过由后端截断并加 `…` |
| 摘要内容 | 单行纯文本，不含换行/HTML/Markdown 表格 |
| 数值格式 | 分数统一两位小数（`0.83`）；数量用 `N 条/张/个/篇` |
| 空数据 | 明确表达：`无召回`、`未匹配到文档`、`未启用`、`0 条结果` |
| 顺序 | 后端按 `seq` 升序返回；前端仍应按 `seq` 排序兜底 |
| 缺失摘要 | 前端回退：running → `进行中…`，done → `完成`，failed → `失败` 或 `error` |
| 隐私 | 不传 chunk 正文、abstract、prompt、完整答案；只传标题/分数/数量 |

### 4.4 兼容矩阵

| 后端 | 前端 | 行为 |
| --- | --- | --- |
| 旧（无 `nodes`） | 旧 | 完全不变 |
| 旧（无 `nodes`） | 新 | 回退到 `done_list/running_list`，不显示摘要 |
| 新（有 `nodes`） | 旧 | 旧前端忽略未知字段，仍显示节点名 |
| 新（有 `nodes`） | 新 | 显示「节点名：摘要 + 耗时」 |

---

## 5. 后端设计

### 5.1 任务侧存储

在 `src/utils/task_utils.py` 增加第五个字典，**不改变现有四个字典的语义**：

```python
# task_id -> {run_id: node_meta}
_tasks_node_meta: dict[str, dict[int, dict]] = defaultdict(dict)


def set_node_meta(task_id: str, run_id: int, **fields) -> None:
    """合并写入一次节点执行的元数据（summary/metrics/status/cost_ms...）。"""


def get_node_meta(task_id: str) -> list[dict]:
    """按 seq 升序返回节点明细副本。"""
```

要点：

- 用 `run_id`（自增序号）作为一次节点执行的 key，**不要用节点名**：md 压缩包扇出时同一个节点会执行 N 次。
- `clear_task` 同步清理 `_tasks_node_meta`。
- 当前四个字典没有锁；新增 `seq` 自增和 meta 合并建议加 `threading.Lock`，至少在单进程内保证快照一致。
- 多 worker 限制与现状一致：仍是进程内状态；若要多 worker，需 Redis/Mongo 或单点任务服务。

### 5.2 `trace_node` 生命周期

`_task_trace` 改成「running → 执行 → done/failed」的完整生命周期，并写入 meta：

```python
def _task_trace(node_key: str, name: str, need_push: bool = False):
    def deco(func):
        @wraps(func)
        def wrapper(state, *args, **kwargs):
            task_id = _resolve_trace_id(state)  # task_id 优先，否则 session_id
            run_id = task_utils.next_run_id(task_id)
            seq = task_utils.next_seq(task_id)
            ctx = NodeContext(task_id, run_id, node_key, name, seq)
            token = _current_node.set(ctx)

            task_utils.set_node_meta(
                task_id,
                run_id,
                key=node_key,
                name=name,
                status="running",
                seq=seq,
                summary=None,
                metrics=None,
                cost_ms=None,
                branch=_branch_of(state),
            )
            add_running_node(task_id, name, need_push=need_push)

            start = time.time()
            try:
                result = func(state, *args, **kwargs)
                cost_ms = int((time.time() - start) * 1000)
                task_utils.set_node_meta(
                    task_id,
                    run_id,
                    status="done",
                    cost_ms=cost_ms,
                    finished_at=int(time.time() * 1000),
                )
                add_done_node(task_id, name, need_push=need_push)
                return result
            except Exception as e:
                cost_ms = int((time.time() - start) * 1000)
                task_utils.set_node_meta(
                    task_id,
                    run_id,
                    status="failed",
                    cost_ms=cost_ms,
                    error=str(e)[:200],
                    finished_at=int(time.time() * 1000),
                )
                # 兼容旧前端：仍进 done_list；新前端以 nodes[].status=failed 为准
                add_done_node(task_id, name, need_push=need_push)
                raise
            finally:
                _current_node.reset(token)

        return wrapper

    return deco
```

注意：

- 现有 `trace_node` 把 `description` 同时当显示名和节点标识；改造后 **`node_key = func.__name__`，`name = desc`**，两者分离。
- 耗时由 `_task_trace` 自己测量；`node_log` 继续打自己的 `耗时` 日志，二者会有毫秒级差异，可接受，避免改日志装饰器。
- 失败节点仍调用 `add_done_node` 以保持旧 UI 行为；新前端用 `nodes[].status=failed` 渲染失败态。
- `branch = state.get("file_title")` 只在导入任务有值；查询任务为 null。

### 5.3 节点上报摘要

在 `src/utils/node_utils.py` 提供轻量 API，节点在拿到数据后调用：

```python
from utils.node_utils import report_node_summary

report_node_summary(
    summary="最高得分 0.83",
    metrics={"count": 20, "max_score": 0.83},
    artifacts=[],
)
```

实现要点：

```python
_current_node: ContextVar[NodeContext | None] = ContextVar("current_node", default=None)


def report_node_summary(summary, metrics=None, artifacts=None) -> None:
    ctx = _current_node.get()
    if ctx is None:
        return
    try:
        task_utils.set_node_meta(
            ctx.task_id,
            ctx.run_id,
            summary=_clean(summary)[:60],
            metrics=_small(metrics),
            artifacts=_small(artifacts),
        )
    except Exception:
        # 摘要失败不影响业务；只记 debug
        logger.debug("节点摘要写入失败", exc_info=True)
```

- 用 `ContextVar` 是因为查询 state 没有 `task_id`，节点拿不到 trace id；`_task_trace` 在同一调用线程里设置上下文，节点内直接调用即可。
- 如果不想引入 ContextVar，也可以 `report_node_summary(state, ...)`，由 helper 自己解析 `task_id/session_id`；但节点需要多传一个参数，且 md 扇出分支仍要额外识别。二选一即可。
- 摘要应在节点 `return` 之前上报；`_task_trace` 的完成推送会带上最后一次写入的摘要。若需要在节点执行中途刷新，可给 report 增加 `push=True`，v1 不需要。
- ContextVar 只在当前线程/上下文有效；节点内部 `ThreadPoolExecutor` 的子线程不要直接调用 report，应在并发任务 join 后回到节点主线程再上报。
- 摘要构造函数建议放在各节点文件内（或 `utils/summaries.py`），保持纯函数、可单独用脚本验证。

### 5.4 各节点摘要映射

#### 查询任务

| 节点 | 摘要示例 | 数据来源 | 需要补的上报 |
| --- | --- | --- | --- |
| 意图识别 | `HAK 180 产品安全手册`；多篇 `A、B 等 3 篇`；无匹配 `未匹配到文档` | `confirm_list` + 本地 `doc_titles` | 节点内上报；`doc_titles` 是局部变量 |
| 向量化查询 | `最高得分 0.83`；空 `无召回` | 返回的 `embedding_recalls` | 节点内上报（或结果回调） |
| HyDE 搜索 | `最高得分 0.79`；关闭 `未启用` | `hyde_recalls` | 节点内上报 |
| 互联网搜索 | `4 条结果`；失败 `搜索失败，已跳过`；空 `0 条结果` | `web_matches` + 异常标记 | 需区分「失败」与「0 条」 |
| 融合排序 | `保留 3 条 · Top1 0.91` | `rerank_results` | 节点内上报 |
| 答案输出 | `生成回答 · 312 字`；早停 `未匹配到文档` | 本地 `answer` | 节点内上报；答案未写回 state |

#### 导入任务

| 节点 | 摘要示例 | 数据来源 | 需要补的上报 |
| --- | --- | --- | --- |
| 识别文档类别 | `PDF · HAK 180 产品安全手册` | 返回 state 的 `origin_file_type/file_title` | 可在结果回调里做 |
| PDF 转 Markdown | `23 页 · 转换完成` | 本地 `page_cnt` | 页数目前未打印/未进 state，需上报 |
| 处理 Markdown 独文件 | `3 张图片 · 已本地化` | 本地 `url_to_local` | 图片数需上报 |
| 处理 Markdown 压缩包 | `4 个 md 文件 · 已解压` | state 的 `markdown_file_paths` | 结果回调即可 |
| Markdown 图片识别 | `12 张图片 · 已生成摘要` | 本地 `image_info_list`/`summary_dict` | 图片数需上报 |
| 文档切分 | `87 个切片` | 本地 `chunk_list` | chunk 数目前未打印，需上报 |
| 文档嵌入入库 | `doc_id 7 · 87 个切片` | 本地 `doc_id`/`embedded` | 目前 `return {}`，需上报 |

> 这张表就是「为什么需要改 13 个节点」的答案：一半摘要能从返回值算，另一半的数据只在局部变量里，必须显式上报一次。

**改造示例（查询）**

```python
# query_processor/nodes/node_search_embedding.py
@trace_node(desc="向量化查询", need_push=True)
def node_search_embedding(state: QueryGraphState) -> QueryGraphState:
    doc_ids, rewritten_query = step_1_validate_and_get_data(state)
    if not doc_ids or not rewritten_query:
        report_node_summary("无确认文档")
        return {}

    embedding_recalls = step_2_vectorize_query(rewritten_query, doc_ids)
    top_score = max((c.get("score", 0.0) for c in embedding_recalls), default=0.0)
    report_node_summary(
        summary=f"最高得分 {top_score:.2f}" if embedding_recalls else "无召回",
        metrics={"count": len(embedding_recalls), "max_score": round(top_score, 4)},
    )
    return {"embedding_recalls": embedding_recalls}
```

**改造示例（导入）**

```python
# import_processor/nodes/node_document_split.py
chunks_list = step_2_split_markdown(md_content)
report_node_summary(
    summary=f"{len(chunks_list)} 个切片",
    metrics={"chunk_count": len(chunks_list)},
)
chunks_json_path = step_3_backup_chunks_json(md_path, file_title, chunks_list)
return {"chunks_json_path": str(chunks_json_path)}
```

这两个例子分别覆盖「结果在返回值里」和「结果只在局部变量里」两种改造方式。

### 5.5 终态与异常

| 项 | 设计 |
| --- | --- |
| 查询终态 | `query_service` 先 `set_task_status(complete)`，再 `task_push_sse`，最后 `__close__`；让最后一帧带 `complete` 和全部摘要（顺带修 G4） |
| 导入终态 | 已有 `task_push_sse`，无需改动 |
| 节点失败 | `_task_trace` 写 `status=failed`、`error`，并推送快照 |
| 任务失败 | service 现有 `error` 事件保留；`progress` 增加 `error` 字段可选 |
| 摘要异常 | 吞掉并记 debug，业务继续；前端回退到「完成」 |
| 任务总耗时 | 可选：任务快照增加 `started_at/finished_at/total_cost_ms` |

### 5.6 推送时序

```text
POST /api/query
  │
  ├─ SSE ready
  ├─ progress: status=processing, nodes=[意图识别 running]       ← 节点开始
  ├─ progress: status=processing, nodes=[意图识别 done + summary] ← 节点完成
  ├─ progress: nodes=[..., 向量化查询 running]                    ← 并行节点开始
  ├─ progress: nodes=[..., 向量化查询 done + 最高得分]             ← 并行节点完成
  ├─ ...
  ├─ delta × N
  ├─ final
  ├─ progress: status=complete, nodes=[全部 done + summary]       ← 新增终态快照
  └─ __close__
```

---

## 6. 前端设计

### 6.1 类型扩展

`web/src/types/app.ts`：

```ts
export type NodeStatus = "pending" | "running" | "done" | "failed" | "skipped";

export interface NodeProgress {
  key: string;
  name: string;
  status: NodeStatus;
  seq?: number;
  summary?: string | null;
  metrics?: Record<string, unknown> | null;
  cost_ms?: number | null;
  branch?: string | null;
  error?: string | null;
}

export interface ProgressView {
  done: string[];
  running: string[];
  status: string;
  nodes?: NodeProgress[];
  error?: string | null;
}

export interface StatusResponse {
  status: string;
  done_list?: string[];
  running_list?: string[];
  nodes?: NodeProgress[];
  answer?: string;
  error?: string;
}

// web/src/types/docs.ts 的 ImportFile 同步增加
export interface ImportFile {
  // ...原有字段
  nodes?: NodeProgress[];
}
```

> 前端类型直接沿用后端 snake_case（`cost_ms`、`branch`），避免多一层映射；如果项目后续统一 camelCase，再在 store 入口集中转换。

### 6.2 Store 映射

`chatStore.onProgress`：

```ts
patchTask({
  done: d?.done_list || [],
  running: d?.running_list || [],
  status: d?.status || "processing",
  nodes: d?.nodes,
  error: d?.error ?? null,
});
```

`docsStore.onProgress` 同理，把 `d.nodes` 写进 `ImportFile`。

要点：

- `nodes` 缺失时保留 `undefined`，不要写成 `[]`，否则前端无法区分「旧服务」和「新服务但暂无节点」。
- 旧 SSE 任务 id 校验逻辑不变。

### 6.3 渲染与回退

`QueryProgress` 的 `lines` 从两路来：

```tsx
const nodes: NodeProgress[] = progress.nodes?.length
  ? [...progress.nodes].sort((a, b) => (a.seq ?? 0) - (b.seq ?? 0))
  : [
      ...progress.done.map((name) => ({
        key: name, name, status: "done" as const, seq: 0,
      })),
      ...progress.running.map((name) => ({
        key: name, name, status: "running" as const, seq: 0,
      })),
    ];

const nodeLines: StatusLogLine[] = nodes.map((n) => ({
  id: `${n.key}-${n.branch ?? ""}`,
  kind: n.status === "failed" ? "failed" : n.status === "running" ? "running" : "done",
  text: `${n.name}：${
    n.summary ||
    (n.status === "running"
      ? "进行中…"
      : n.status === "failed"
        ? n.error || "失败"
        : "完成")
  }`,
}));
```

`ImportTaskItem` 复用同一套；有 `branch` 时在节点名后加 `（fileTitle）`，并限制最多展示 N 个分支。

`StatusLog` 小改：

- `StatusLogLine` 增加可选 `id`，`key` 用 `id ?? text`，避免多分支同文本重复 key。
- 如果希望「耗时右对齐」或「摘要弱化」，把 `text` 从 `string` 放宽到 `ReactNode`，由 `QueryProgress` 拆成 `name / summary / cost` 三段；v1 可以直接拼字符串，先跑通。

### 6.4 样式与交互

| 项 | 建议 |
| --- | --- |
| 截断 | 每行单行，`overflow: hidden; text-overflow: ellipsis; white-space: nowrap` |
| Tooltip | `title` 放完整摘要，避免长文档名撑破卡片 |
| 耗时 | 可选，右对齐弱化显示；不显示也不影响主需求 |
| 自动展开 | 运行中 `open=true`，完成后自动收起（沿用 P1 逻辑） |
| 响应式 | 390px 下节点名与摘要都要能截断；摘要可换行但最多两行 |
| 空状态 | 旧服务无 nodes 时按现有 done/running 渲染，不出现空白 |
| 无障碍 | `aria-live="polite"` 已有；节点级更新频率低，不会刷屏 |

### 6.5 多 md 分支

| 方案 | 展示 | 适用 |
| --- | --- | --- |
| 每分支一行 | `图片识别（A）：12 张` / `图片识别（B）：8 张` | 文件少（≤10） |
| 聚合一行 | `图片识别（3 个文件）：28 张` | 文件多，推荐最终形态 |
| 只显示最新分支 | `图片识别（A）：12 张` | 临时兜底，不推荐 |

v1 建议：每分支一行 + 最多 10 行 + 「等 N 个文件」；P2.1 再做服务端聚合。聚合需要节点上报可加总的 `metrics`（如 `image_count/chunk_count`），不要在前端解析摘要字符串。

---

## 7. 边界与风险

| 风险 | 说明 | 对策 |
| --- | --- | --- |
| 载荷变大 | 13 个节点约 2-3 KB；100 个 md 分支可能上百条 | 限制摘要长度、分支展示数量；必要时服务端聚合 |
| 多 worker | 现有任务字典本来就是进程内，多 worker 会不一致 | 本次不扩大问题；后续统一 Redis/Mongo |
| 同会话并发 | 查询用 `session_id` 当 trace id，两个并发查询会共享进度与 SSE 队列 | 本次沿用现状；建议同批补查询 `task_id`（G2） |
| 节点重名 | 用 `node_key` 而不是中文名做标识 | `key` + `seq` + `branch` 三元定位 |
| 摘要泄露 | 文档标题/分数一般可展示，abstract/chunk 不可 | 禁止传全文；只传标题/分数/数量 |
| 摘要生成报错 | 可能拖垮节点 | `report_node_summary` 内部 try/except，只记 debug |
| 前端旧版本 | 旧前端忽略新字段 | 保留 `done_list/running_list`；字段可选 |
| 失败节点旧 UI | 旧前端会把失败节点显示为 done | 新前端以 `nodes[].status` 为准；旧 UI 保持现状 |
| 排序 | 并行节点完成顺序不固定 | 用 `seq` 排序；seq 在节点开始时分配 |
| 终态 | 查询最后一帧可能仍是 processing | `query_service` 在 close 前补最终快照 |

---

## 8. 实施顺序与验证

### 8.1 改动文件

| 层 | 文件 | 改动 |
| --- | --- | --- |
| 后端 | `src/utils/task_utils.py` | 第五个 meta 字典、seq/run_id、快照增加 `nodes` |
| 后端 | `src/utils/node_utils.py` | `_task_trace` 生命周期、ContextVar、`report_node_summary` |
| 后端 | `query_processor/nodes/*.py`（6 个） | 各节点上报摘要/指标 |
| 后端 | `import_processor/nodes/*.py`（7 个） | 各节点上报摘要/指标 |
| 后端 | `src/service/query_service.py` | 终态补 `task_push_sse` |
| 前端 | `web/src/types/app.ts` | `NodeProgress`、`ProgressView.nodes`、`StatusResponse.nodes` |
| 前端 | `web/src/store/chatStore.ts` / `docsStore.ts` | progress 映射 `nodes` |
| 前端 | `web/src/components/chat/QueryProgress.tsx` | 节点摘要行 + 回退 |
| 前端 | `web/src/components/docs/ImportTaskItem.tsx` | 节点摘要行 + 分支 |
| 前端 | `web/src/components/ui/StatusLog.tsx` | 可选 `id`；必要时 text 支持 ReactNode |
| 前端 | `web/src/styles/chat.css` / `docs.css` | 截断、耗时、窄屏 |

### 8.2 实施顺序

1. `task_utils` + `node_utils`：先让 `progress` 能带 `nodes`，摘要为空也能跑。
2. 前端类型 + 渲染 + 回退：用假数据验证「有 nodes / 无 nodes」两条路径。
3. 查询 6 个节点逐个上报，真实查询验证。
4. `query_service` 终态快照。
5. 导入 7 个节点逐个上报，验证 PDF / md / zip 三条链路。
6. 多 md 分支展示与截断。
7. 失败、超时、断线、刷新、窄屏、暗色回归。

### 8.3 验证方式

用以下方式验证：

- 直接运行目标节点脚本，观察 loguru 日志与 state。
- 启动 API，真实发起查询/导入，用浏览器 Network 面板看 `progress.data` 是否含 `nodes`。
- 前端临时 mock 一份不带 `nodes` 的旧载荷，确认回退不空白。
- 检查 console 无报错；390/780/1280、Light/Dark 各看一次。

---

## 9. 待确认

1. **范围**：先做查询任务，还是查询 + 导入一起做？建议先查询（无分支、链路短），再导入。
2. **耗时**：是否展示每步耗时？示例里没有，但数据已有；建议先隐藏，保留字段。
3. **多 md 分支**：v1 每分支一行，还是直接做服务端聚合？
4. **摘要文案**：意图识别展示文档标题还是「重写查询」？当前示例按标题设计。
5. **失败节点**：旧前端把失败节点显示为 done，是否接受新前端修正、旧前端保持现状？

---

## 附录：v1 摘要文案速查

| 节点 | 默认摘要 | 无数据 / 异常 |
| --- | --- | --- |
| 意图识别 | 确认文档标题，最多 2 篇 + 「等 N 篇」 | `未匹配到文档` / `疑似：X` |
| 向量化查询 | `最高得分 0.83` | `无召回` |
| HyDE 搜索 | `最高得分 0.79` | `无召回` / `未启用` |
| 互联网搜索 | `4 条结果` | `0 条结果` / `搜索失败，已跳过` |
| 融合排序 | `保留 3 条 · Top1 0.91` | `无候选` |
| 答案输出 | `生成回答 · 312 字` | `未匹配到文档` / `生成失败` |
| 识别文档类别 | `PDF · HAK 180 产品安全手册` | `未知类型` |
| PDF 转 Markdown | `23 页 · 转换完成` | `转换失败` |
| 处理 Markdown 独文件 | `3 张图片 · 已本地化` | `无在线图片` |
| 处理 Markdown 压缩包 | `4 个 md 文件 · 已解压` | `未找到 md 文件` |
| Markdown 图片识别 | `12 张图片 · 已生成摘要` | `无图片` |
| 文档切分 | `87 个切片` | `无切片` |
| 文档嵌入入库 | `doc_id 7 · 87 个切片` | `入库失败` |
