/**
 * 会话全局预留 Store (PRD 未来项, V0 仅骨架, 设计文档 §4.3/§4.5.6)
 *
 * - tokens 消耗 (session global)
 * - 任务运行状态统一视图 (query / upload)
 *
 * V1 挂载点:
 * - chatStore/docsStore 的 SSE 终态事件将来同步写入 tasks;
 * - 刷新后断点重连 (调研 R6) 依据 tasks 中的 taskId/sessionId;
 * - 分页 cursor (V1 分页化) 另预留于 chatStore/docsStore 状态对象。
 */
import { create } from "zustand";

/** 预留: tokens 消耗 */
export interface TokensUsage {
  total: number;
  byTask: Record<string, number>;
}

/** 预留: 统一任务运行状态快照 */
export interface TaskSnapshot {
  id: string;
  kind: "query" | "upload";
  status: string; // pending / processing / completed / failed
  startedAt: number;
}

interface SessionStoreState {
  tokens: TokensUsage;
  tasks: Record<string, TaskSnapshot>;
}

export const useSessionStore = create<SessionStoreState>()(() => ({
  tokens: { total: 0, byTask: {} },
  tasks: {},
}));
