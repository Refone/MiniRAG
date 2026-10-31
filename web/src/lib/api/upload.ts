/** 上传 API（Session-MVVM V0: 自文档管理页收敛至此） */

import { request } from "./client";
import { getBrowserSessionId } from "@/utils/session";
import type { ImportUploadResponse } from "@/types/docs";

/**
 * POST /api/upload (multipart/form-data) → 返回 task_id,
 * 随后经 /api/upload/sse/{task_id} 推流。
 * session_id 必填（后端 400 拒绝缺失）：未显式传入时沿用 localStorage
 * 会话标识（kb_session_id），保证上传消耗计入当前浏览器会话。
 */
export async function postUpload(
  file: File,
  sessionId?: string,
): Promise<ImportUploadResponse> {
  const formData = new FormData();
  formData.append("file", file);
  formData.append("session_id", sessionId ?? getBrowserSessionId());
  const res = await request("/api/upload", {
    method: "POST",
    body: formData,
  });
  return await res.json();
}
