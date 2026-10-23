/** 对话域类型契约 */

import type { ProgressView } from "./app";

/** 对话页消息（展示态，chatStore 唯一持有） */
export interface ChatMessage {
  id: string;
  role: "user" | "bot";
  text: string;
  time: string;
  hint?: string;
  typing: boolean;
  /** 是否处于 SSE 流式输出中：用于图片语法未写完时的占位截流 */
  streaming: boolean;
  progress: ProgressView | null;
  error: string | null;
}

/** 后端历史记录单条（GET /api/history/{sessionId} → history[]） */
export interface HistoryItem {
  role: string;
  text: string;
  timestamp: number;
}

/** POST /api/query 响应 */
export interface QueryResponse {
  session_id: string;
  answer?: string;
  done_list?: string[];
  error?: string;
  message?: string;
}

/** POST /api/query 请求体（两步式第一步，随后经 /api/query/sse/{session_id} 推流） */
export interface QueryPayload {
  query: string;
  session_id: string;
  enable_web_search: boolean;
  enable_hyde: boolean;
}
