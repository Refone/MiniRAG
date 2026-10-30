# Token统计 PRD

## 现状

当前用户使用整个系统，对 Token 的消耗无感知。

## 目标

在界面 NavBar 区域，设计 Token 消耗指示器，实时显示用户当前的 Token 使用情况，数字动态跳变。

分别显示 LLM、VLM、Embedding、Reranker（项目中所有在线大模型调用）的 Token 消耗情况，以及总 Token 消耗。

消耗数据跟随会话，与会话 session 对应。不同会话的消耗数据独立统计。

建立 mongodb 表 `token_usage`，记录每个会话的 Token 消耗情况，字段包括：

- `session_id`：会话 ID
- `user_ip`：用户 IP 地址
- `llm_tokens`：LLM 消耗的 Token 数
- `vlm_tokens`：VLM 消耗的 Token 数
- `embedding_tokens`：Embedding 消耗的 Token 数
- `reranker_tokens`：Reranker 消耗的 Token 数
- `total_tokens`：总 Token 消耗
- `updated_at`：记录更新时间
