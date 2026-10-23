/** 会话页 API（Session-MVVM V0: 自 ChatPage 收敛至此） */

import { request } from "./client";
import type { HistoryItem, QueryPayload, QueryResponse } from "@/types/chat";

/** POST /api/query → 返回 session_id (SSE 推流入口) */
export async function postQuery(payload: QueryPayload): Promise<QueryResponse> {
  const res = await request("/api/query", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(payload),
  });
  return await res.json();
}

/** GET /api/history/{sessionId} → 历史消息列表 (后端格式 { status, history: HistoryItem[] }) */
export async function getHistory(sessionId: string): Promise<HistoryItem[]> {
  const res = await request(`/api/history/${encodeURIComponent(sessionId)}`);
  const data = await res.json();
  return Array.isArray(data.history) ? data.history : [];
}

/** DELETE /api/history/{sessionId} (清空会话历史) */
export async function deleteHistory(sessionId: string): Promise<void> {
  await request(`/api/history/${encodeURIComponent(sessionId)}`, { method: "DELETE" });
}
