/**
 * Token 统计 Store（Token统计需求，前端动工）
 *
 * - 快照来源：GET /api/token-usage/{session_id} 与查询/上传流的 SSE usage 帧；
 * - 面板开合与口径（总计/查询/上传）是 NavBar TokenMeter 的组件态，不入 store；
 * - 静默刷新（面板打开）失败不打断已有数据展示，仅从未拿到数据时才进 error 态
 *   （对齐 demo 统计失败态 + 重试）；
 * - refreshSeq 竞态保护：过期 GET 响应与 SSE 快照互不覆盖。
 */
import { create } from "zustand";
import { getTokenUsage } from "@/lib/api/tokenUsage";
import { getBrowserSessionId } from "@/utils/session";
import type {
  TokenLoadStatus,
  TokenScope,
  TokenUsageSnapshot,
} from "@/types/tokenUsage";

interface TokenUsageStoreState {
  /** 最近一次成功快照（GET 或 SSE 帧） */
  snapshot: TokenUsageSnapshot | null;
  status: TokenLoadStatus;
  /** 最近一次快照来源口径（SSE 帧所属流），面板行闪烁用 */
  lastSource: TokenScope | null;
  /** silent：面板打开的后台刷新，不置 loading、失败不覆盖已有数据 */
  refresh: (opts?: { silent?: boolean }) => Promise<boolean>;
  /** SSE usage 帧直接落地（流结束，后端已 flush 落库） */
  applySnapshot: (snapshot: TokenUsageSnapshot, source: TokenScope) => void;
}

/** 请求序号：过期 GET 响应不得覆盖更新快照 */
let refreshSeq = 0;

export const useTokenUsageStore = create<TokenUsageStoreState>()((set, get) => ({
  snapshot: null,
  status: "idle",
  lastSource: null,

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
}));
