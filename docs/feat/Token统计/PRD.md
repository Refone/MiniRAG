# Token统计 PRD

<!-- docs-layout: 2026-11 -->
> 状态：已完结（历史快照） · 文中 `src/`、`web/` 为 2026-11 目录改名前的路径，当前对应 `backend/`、`frontend/`；代码现状以仓库为准。索引见 [docs/feat/README.md](../README.md)。

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

## 补充说明

- 一个会话是指浏览器端的一次会话，作为用户标识，代表一个用户的访问。故不应该说是与会话 session 对应。没有说清楚这个逻辑造成了当前 demo 一些问题：
  1. Token 消耗不仅是查询会消耗，上传文档也会消耗，所以 tpTab 里面应该是 会话总计 ｜ 查询消耗 ｜ 上传消耗。
  2. Token 统计不应该因删除会话历史而消失，应该与用户的浏览器会话绑定，保证在会话存在期间持续统计。与后端 mongodb 记录保持一致。
