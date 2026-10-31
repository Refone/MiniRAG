/** Token 统计域类型契约（与后端 TokenUsageSnapshot / ModelTokenUsage 字段一致） */

/** 四类在线大模型维度 */
export type TokenKind = "llm" | "vlm" | "embedding" | "reranker";

/** 统计口径（demo 三 tab）：会话总计 ｜ 查询消耗 ｜ 上传消耗 */
export type TokenScope = "total" | "query" | "upload";

/** 前端快照加载状态（idle 为未触发首次拉取） */
export type TokenLoadStatus = "idle" | "loading" | "ready" | "error";

/** 单一口径（查询 / 上传）的四模型 token 用量 */
export interface ModelTokenUsage {
  llm_tokens: number;
  vlm_tokens: number;
  embedding_tokens: number;
  reranker_tokens: number;
  total_tokens: number;
}

/** GET /api/token-usage/{sessionId} 响应：会话总计（四模型派生字段）+ 查询 / 上传两口径 */
export interface TokenUsageSnapshot {
  session_id: string;
  user_ip: string;
  /** 无任何记录时为 null（空统计态） */
  updated_at: number | null;
  llm_tokens: number;
  vlm_tokens: number;
  embedding_tokens: number;
  reranker_tokens: number;
  total_tokens: number;
  query: ModelTokenUsage;
  upload: ModelTokenUsage;
}
