/**
 * Token 统计纯函数：快照 → 口径视图 / 合计 / 增量差异。
 * 组件与 store 共用，不持有状态。
 */
import type {
  ModelTokenUsage,
  TokenKind,
  TokenScope,
  TokenSource,
  TokenUsageSnapshot,
} from "@/types/tokenUsage";

/** 四模型 token 用量的扁平形状（顶层派生字段与 query/upload 口径通用） */
export interface KindUsage {
  llm: number;
  vlm: number;
  embedding: number;
  reranker: number;
}

/** 单个 SSE 通道尚未落账的增量（source 决定叠加到哪个口径） */
export interface PendingUsage {
  source: TokenSource;
  usage: KindUsage;
}

export const TOKEN_KIND_KEYS: readonly TokenKind[] = [
  "llm",
  "vlm",
  "embedding",
  "reranker",
];

export function emptyKindUsage(): KindUsage {
  return { llm: 0, vlm: 0, embedding: 0, reranker: 0 };
}

function toKindUsage(u: ModelTokenUsage): KindUsage {
  return {
    llm: u.llm_tokens,
    vlm: u.vlm_tokens,
    embedding: u.embedding_tokens,
    reranker: u.reranker_tokens,
  };
}

/** 快照 → 口径视图：total 用顶层派生字段，query/upload 用对应子对象 */
export function scopeUsage(
  snapshot: TokenUsageSnapshot,
  scope: TokenScope,
): KindUsage {
  if (scope === "query") return toKindUsage(snapshot.query);
  if (scope === "upload") return toKindUsage(snapshot.upload);
  return toKindUsage(snapshot);
}

export function kindTotal(u: KindUsage): number {
  return u.llm + u.vlm + u.embedding + u.reranker;
}

/**
 * 快照 + 未落账增量 → 展示快照（各口径与顶层派生字段同时累加）。
 * 不改动入参；updated_at 保留权威快照的落库时间。
 */
export function withPendingUsage(
  snapshot: TokenUsageSnapshot,
  pending: readonly PendingUsage[],
): TokenUsageSnapshot {
  if (pending.length === 0) return snapshot;
  const next: TokenUsageSnapshot = {
    ...snapshot,
    query: { ...snapshot.query },
    upload: { ...snapshot.upload },
  };
  for (const { source, usage } of pending) {
    const scope = source === "query" ? next.query : next.upload;
    scope.llm_tokens += usage.llm;
    scope.vlm_tokens += usage.vlm;
    scope.embedding_tokens += usage.embedding;
    scope.reranker_tokens += usage.reranker;
    scope.total_tokens += kindTotal(usage);
    next.llm_tokens += usage.llm;
    next.vlm_tokens += usage.vlm;
    next.embedding_tokens += usage.embedding;
    next.reranker_tokens += usage.reranker;
    next.total_tokens += kindTotal(usage);
  }
  return next;
}

/**
 * next 相对 prev 的逐模型增量（负值视为 0；prev 为 null（首帧）时全 0）。
 * TokenMeter 按模型拆分增量、触发面板行闪烁用。
 */
export function usageKindIncreases(
  next: KindUsage,
  prev: KindUsage | null,
): Record<TokenKind, number> {
  const increases = emptyKindUsage();
  if (!prev) return increases;
  for (const kind of TOKEN_KIND_KEYS) {
    increases[kind] = Math.max(0, next[kind] - prev[kind]);
  }
  return increases;
}
