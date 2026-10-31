/**
 * Token 统计纯函数：快照 → 口径视图 / 合计 / 增量差异。
 * 组件与 store 共用，不持有状态。
 */
import type {
  ModelTokenUsage,
  TokenKind,
  TokenScope,
  TokenUsageSnapshot,
} from "@/types/tokenUsage";

/** 四模型 token 用量的扁平形状（顶层派生字段与 query/upload 口径通用） */
export interface KindUsage {
  llm: number;
  vlm: number;
  embedding: number;
  reranker: number;
}

export const TOKEN_KIND_KEYS: readonly TokenKind[] = [
  "llm",
  "vlm",
  "embedding",
  "reranker",
];

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
 * next 相对 prev 的增量：返回有增量的模型维度与增量总和。
 * prev 为 null（首帧）或没有增量时 kinds 为空。
 */
export function usageIncreases(
  next: KindUsage,
  prev: KindUsage | null,
): { kinds: TokenKind[]; amount: number } {
  const kinds: TokenKind[] = [];
  let amount = 0;
  if (!prev) return { kinds, amount };
  for (const kind of TOKEN_KIND_KEYS) {
    const diff = next[kind] - prev[kind];
    if (diff > 0) {
      kinds.push(kind);
      amount += diff;
    }
  }
  return { kinds, amount };
}
