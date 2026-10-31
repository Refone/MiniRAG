/** 浏览器会话标识：localStorage kb_session_id（后端会话绑定，全仓唯一生成口径） */

import { SESSION_KEY } from "@/lib/constants";

export function getBrowserSessionId(): string {
  let id = localStorage.getItem(SESSION_KEY);
  if (!id) {
    id =
      "sess-" + Math.random().toString(36).slice(2) + Date.now().toString(36);
    localStorage.setItem(SESSION_KEY, id);
  }
  return id;
}
