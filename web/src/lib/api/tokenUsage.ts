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
