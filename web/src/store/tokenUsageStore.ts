/**
 * Token 统计 Store（Token统计需求，前端动工）
 *
 * - 快照来源：GET /api/token-usage/{session_id} 与请求结束的 SSE usage 帧；
 * - lastDelta：单次模型调用的增量事件（SSE usage-delta），TokenMeter 消费
 *   后入气泡队列（+N 模型 气泡），仅瞬态提示、不参与数值累加；
 * - 面板开合与口径（总计/查询/上传）是 NavBar TokenMeter 的组件态，不入 store；
 * - 静默刷新（面板打开）失败不打断已有数据展示，仅从未拿到数据时才进 error 态
 *   （对齐 demo 统计失败态 + 重试）；
 * - refreshSeq 竞态保护：过期 GET 响应与 SSE 快照互不覆盖。
 */
import { create } from "zustand";
import { getTokenUsage } from "@/lib/api/tokenUsage";
import { getBrowserSessionId } from "@/utils/session";
import { TOKEN_KIND_KEYS } from "@/utils/token";
import type {
  TokenKind,
  TokenLoadStatus,
  TokenScope,
  TokenUsageSnapshot,
} from "@/types/tokenUsage";

/** 单次模型调用增量事件（SSE usage-delta → TokenMeter 气泡） */
export interface UsageDeltaEvent {
  seq: number;
  kind: TokenKind;
  tokens: number;
  /** 增量所属流（查询 / 上传），面板行闪烁口径用 */
  source: TokenScope;
}

interface TokenUsageStoreState {
  /** 最近一次成功快照（GET 或 SSE 帧） */
  snapshot: TokenUsageSnapshot | null;
  status: TokenLoadStatus;
  /** 最近一次快照来源口径（SSE 帧所属流），面板行闪烁用 */
  lastSource: TokenScope | null;
  /** 最近一次模型调用增量（瞬时事件，TokenMeter 消费后入气泡队列） */
  lastDelta: UsageDeltaEvent | null;
  /** silent：面板打开的后台刷新，不置 loading、失败不覆盖已有数据 */
  refresh: (opts?: { silent?: boolean }) => Promise<boolean>;
  /** SSE usage 帧直接落地（请求结束，后端已 flush 落库） */
  applySnapshot: (snapshot: TokenUsageSnapshot, source: TokenScope) => void;
  /** SSE usage-delta 帧（单次模型调用结束即推送；未知模型忽略） */
  applyDelta: (kind: string, tokens: number, source: TokenScope) => void;
}

/** 请求序号：过期 GET 响应不得覆盖更新快照 */
let refreshSeq = 0;
let deltaSeq = 0;

export const useTokenUsageStore = create<TokenUsageStoreState>()((set, get) => ({
  snapshot: null,
  status: "idle",
  lastSource: null,
  lastDelta: null,

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

  applySnapshot: (snapshot, source) => {
    refreshSeq += 1;
    set({ snapshot, status: "ready", lastSource: source });
  },

  applyDelta: (kind, tokens, source) => {
    if (!TOKEN_KIND_KEYS.includes(kind as TokenKind)) return;
    if (typeof tokens !== "number" || tokens <= 0) return;
    deltaSeq += 1;
    set({
      lastDelta: {
        seq: deltaSeq,
        kind: kind as TokenKind,
        tokens,
        source,
      },
    });
  },
}));
