/**
 * Token 统计 Store
 *
 * - snapshot：GET /api/token-usage/{session_id} 与 SSE usage 帧的权威快照；
 * - pending：按 SSE 通道累计的未落账增量（usage-delta）；展示值 = 快照 + pending，
 *   请求运行期间 chip 数字随推送实时增长；
 * - usage 快照帧到达（该通道已落库）或流终止（增量不会落库）时清空对应通道；
 * - lastDelta：最近一次模型调用增量事件，供面板行闪烁；
 * - 面板开合与口径（总计/查询/上传）是 NavBar TokenMeter 的组件态，不入 store；
 * - 静默刷新（面板打开）失败不打断已有数据展示，仅从未拿到数据时才进 error 态
 *   （对齐 demo 统计失败态 + 重试）；
 * - refreshSeq 竞态保护：过期 GET 响应与 SSE 快照互不覆盖。
 */
import { create } from "zustand";
import { getTokenUsage } from "@/lib/api/tokenUsage";
import { getBrowserSessionId } from "@/utils/session";
import {
  TOKEN_KIND_KEYS,
  emptyKindUsage,
  type KindUsage,
  type PendingUsage,
} from "@/utils/token";
import type {
  TokenKind,
  TokenLoadStatus,
  TokenSource,
  TokenUsageSnapshot,
} from "@/types/tokenUsage";

/** 单次模型调用增量事件（SSE usage-delta） */
export interface UsageDeltaEvent {
  seq: number;
  kind: TokenKind;
  tokens: number;
  /** 增量所属流（查询 / 上传），面板行闪烁口径用 */
  source: TokenSource;
}

interface TokenUsageStoreState {
  /** 最近一次成功快照（GET 或 SSE 帧） */
  snapshot: TokenUsageSnapshot | null;
  status: TokenLoadStatus;
  /** 最近一次快照来源口径（SSE 帧所属流），面板行闪烁用 */
  lastSource: TokenSource | null;
  /** 最近一次模型调用增量（瞬时事件，TokenMeter 消费后触发行闪烁） */
  lastDelta: UsageDeltaEvent | null;
  /** 通道 key → 未落账增量（展示时叠加到快照上） */
  pending: Record<string, PendingUsage>;
  /** silent：面板打开的后台刷新，不置 loading、失败不覆盖已有数据 */
  refresh: (opts?: { silent?: boolean }) => Promise<boolean>;
  /** SSE usage 帧直接落地（请求结束，后端已 flush 落库），并清空该通道增量 */
  applySnapshot: (
    snapshot: TokenUsageSnapshot,
    source: TokenSource,
    channelId: string,
  ) => void;
  /** SSE usage-delta 帧（单次模型调用结束即推送；未知模型忽略） */
  applyDelta: (
    kind: string,
    tokens: number,
    source: TokenSource,
    channelId: string,
  ) => void;
  /** 流终止未收到 usage 帧时丢弃该通道增量（失败路径不落库） */
  clearPending: (source: TokenSource, channelId: string) => void;
}

/** 请求序号：过期 GET 响应不得覆盖更新快照 */
let refreshSeq = 0;
let deltaSeq = 0;

function channelKey(source: TokenSource, channelId: string): string {
  return `${source}:${channelId}`;
}

function withoutPending(
  pending: Record<string, PendingUsage>,
  key: string,
): Record<string, PendingUsage> {
  if (!(key in pending)) return pending;
  const next = { ...pending };
  delete next[key];
  return next;
}

export const useTokenUsageStore = create<TokenUsageStoreState>()((set, get) => ({
  snapshot: null,
  status: "idle",
  lastSource: null,
  lastDelta: null,
  pending: {},

  refresh: async (opts) => {
    const silent = opts?.silent ?? false;
    // 首次加载防重（StrictMode 双调用 / 并发触发）
    if (!silent && get().status === "loading") return false;
    const seq = ++refreshSeq;
    if (!silent) set({ status: "loading" });
    try {
      const snapshot = await getTokenUsage(getBrowserSessionId());
      if (seq !== refreshSeq) return false;
      set({ snapshot, status: "ready" });
      return true;
    } catch (err) {
      if (seq !== refreshSeq) return false;
      const msg = err instanceof Error ? err.message : String(err);
      console.warn("[token] 拉取 Token 统计失败", msg);
      if (!get().snapshot) set({ status: "error" });
      return false;
    }
  },

  applySnapshot: (snapshot, source, channelId) => {
    refreshSeq += 1;
    set((s) => ({
      snapshot,
      status: "ready",
      lastSource: source,
      pending: withoutPending(s.pending, channelKey(source, channelId)),
    }));
  },

  applyDelta: (kind, tokens, source, channelId) => {
    if (!TOKEN_KIND_KEYS.includes(kind as TokenKind)) return;
    if (typeof tokens !== "number" || tokens <= 0) return;
    const tokenKind = kind as TokenKind;
    const key = channelKey(source, channelId);
    deltaSeq += 1;
    set((s) => {
      const usage: KindUsage = { ...(s.pending[key]?.usage ?? emptyKindUsage()) };
      usage[tokenKind] += tokens;
      return {
        lastDelta: { seq: deltaSeq, kind: tokenKind, tokens, source },
        pending: { ...s.pending, [key]: { source, usage } },
      };
    });
  },

  clearPending: (source, channelId) => {
    const key = channelKey(source, channelId);
    if (!(key in get().pending)) return;
    set((s) => ({ pending: withoutPending(s.pending, key) }));
  },
}));
