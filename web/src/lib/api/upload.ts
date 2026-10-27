/** 上传 API（Session-MVVM V0: 自文档管理页收敛至此） */

import { request } from "./client";
import type { ImportUploadResponse } from "@/types/docs";

/** POST /api/upload (multipart/form-data) → 返回 task_id, 随后经 /api/upload/sse/{task_id} 推流 */
export async function postUpload(file: File): Promise<ImportUploadResponse> {
  const formData = new FormData();
  formData.append("file", file);
  const res = await request("/api/upload", {
    method: "POST",
    body: formData,
  });
  return await res.json();
}
