function resolveApiBase(fallbackPort: number): string {
  const explicit = import.meta.env["VITE_API_BASE"] as string | undefined;
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

export const API_BASE = resolveApiBase(8000);

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
