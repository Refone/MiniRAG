/** Token 统计 API */

import { request } from "./client";
import type { TokenUsageSnapshot } from "@/types/tokenUsage";

/** GET /api/token-usage/{sessionId} → 浏览器会话 Token 快照（三口径） */
export async function getTokenUsage(
  sessionId: string,
): Promise<TokenUsageSnapshot> {
  const res = await request(`/api/token-usage/${encodeURIComponent(sessionId)}`);
  return await res.json();
}

/** DELETE /api/token-usage/{sessionId} → 仅清零该浏览器会话统计（不动聊天历史） */
export async function resetTokenUsage(sessionId: string): Promise<void> {
  await request(`/api/token-usage/${encodeURIComponent(sessionId)}`, {
    method: "DELETE",
  });
}
