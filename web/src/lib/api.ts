function resolveApiBase(
  envKey: "VITE_QUERY_API_BASE" | "VITE_IMPORT_API_BASE",
  fallbackPort: number,
): string {
  const explicit = import.meta.env[envKey] as string | undefined;
  if (explicit) return explicit.replace(/\/+$/, "");
  if (
    !import.meta.env.DEV &&
    typeof window !== "undefined" &&
    window.location.origin.startsWith("http")
  ) {
    return window.location.origin;
  }
  return `http://127.0.0.1:${fallbackPort}`;
}

/** 查询服务（对话/历史/流式输出） */
export const QUERY_API_BASE = resolveApiBase("VITE_QUERY_API_BASE", 8000);

/** 导入服务（文件上传与状态轮询） */
export const IMPORT_API_BASE = resolveApiBase("VITE_IMPORT_API_BASE", 8000);

/**
 * 上传任务状态响应 /import/upload/status/{task_id}
 */
export interface UploadStatusResponse {
  task_id: string;
  status: string;
  running_nodes: string[];
  done_nodes: string[];
  result: Record<string, any>;
}

/**
 * 上传任务响应 /import/upload
 */
export interface ImportUploadResponse {
  task_id: string;
  status: string;
}
