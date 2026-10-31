/** Token 统计域类型契约（与后端 TokenUsageSnapshot / ModelTokenUsage 字段一致） */

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
