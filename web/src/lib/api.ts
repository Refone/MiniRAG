import type { HistoryItem, QueryResponse } from "@/lib/types";

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

/**
 * 后端全部路由统一挂载 /api 前缀 (见 docs/feat/文档管理页面/后端方案.md V1-4)。
 * 下方所有请求路径均以 /api 开头:
 * - dev: API_BASE=http://127.0.0.1:8000 直连 (CORS 放开)
 * - prod: API_BASE=origin, 经 nginx /api/ 反代
 */
export const API_BASE = resolveApiBase(8000);

/**
 * 上传任务响应 /api/upload
 */
export interface ImportUploadResponse {
  task_id: string;
  status: string;
}

/* ------------------------------------------------------------------ */
/* 文档管理页 API (后端方案 §4 / §5 / §6)                                */
/* ------------------------------------------------------------------ */

/** GET /api/docs 列表单条 */
export interface DocsListItem {
  /** Milvus auto_id, string 传输避免 JS 精度丢失 */
  doc_id: string;
  title: string;
  /** "pdf" | "markdown" */
  type: string;
  /** 相对代理路径, 仅 type=pdf 时非空 */
  pdf_link: string | null;
  /** 相对代理路径 */
  chunks_link: string;
}

/** GET /api/docs 响应 */
export interface DocsListResponse {
  total: number;
  list: DocsListItem[];
}

/** GET /api/docs/{doc_id} 详情中的单个切块 */
export interface DocsChunkItem {
  content: string;
  level: number;
  title_stack: (string | null)[];
}

/** GET /api/docs/{doc_id} 响应 */
export interface DocsDetailResponse {
  title: string;
  markdown_text: string;
  chunks: DocsChunkItem[];
  /** 入库原始字符串, 前端按 /[,，]/ 拆分 */
  keywords: string;
  abstract: string;
}

/** DELETE /api/docs/{doc_id} 响应 */
export interface DocsDeleteResponse {
  success: boolean;
  detail?: string;
}

/** 非 2xx 时抛出带后端 detail 的 Error */
async function throwOnError(res: Response): Promise<Response> {
  if (!res.ok) {
    let detail = "";
    try {
      const data = await res.json();
      detail = data?.detail ?? JSON.stringify(data);
    } catch {
      detail = await res.text().catch(() => "");
    }
    throw new Error(detail || `请求失败 (${res.status})`);
  }
  return res;
}

/** 文档列表 (分页, 按 id 降序) */
export async function getDocsList(
  offset = 0,
  limit = 100,
): Promise<DocsListResponse> {
  const res = await fetch(`${API_BASE}/api/docs?offset=${offset}&limit=${limit}`);
  await throwOnError(res);
  return await res.json();
}

/** 文档详情 (markdown 原文 / 切块 / keywords / abstract) */
export async function getDocsDetail(docId: string): Promise<DocsDetailResponse> {
  const res = await fetch(`${API_BASE}/api/docs/${encodeURIComponent(docId)}`);
  await throwOnError(res);
  return await res.json();
}

/** 删除文档 (级联删除 Milvus docs/chunks 与 MinIO 制品) */
export async function deleteDoc(docId: string): Promise<DocsDeleteResponse> {
  const res = await fetch(`${API_BASE}/api/docs/${encodeURIComponent(docId)}`, {
    method: "DELETE",
  });
  await throwOnError(res);
  return await res.json();
}

/* ------------------------------------------------------------------ */
/* 会话页 API (Session-MVVM V0: 自 ChatPage 收敛至此)                    */
/* ------------------------------------------------------------------ */

/** POST /api/query 请求体 (两步式第一步, 随后经 /api/query/sse/{session_id} 推流) */
export interface QueryPayload {
  query: string;
  session_id: string;
  enable_web_search: boolean;
  enable_hyde: boolean;
}

/** POST /api/query → 返回 session_id (SSE 推流入口) */
export async function postQuery(payload: QueryPayload): Promise<QueryResponse> {
  const res = await fetch(`${API_BASE}/api/query`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(payload),
  });
  await throwOnError(res);
  return await res.json();
}

/** GET /api/history/{sessionId} → 历史消息列表 (后端格式 { status, history: HistoryItem[] }) */
export async function getHistory(sessionId: string): Promise<HistoryItem[]> {
  const res = await fetch(
    `${API_BASE}/api/history/${encodeURIComponent(sessionId)}`,
  );
  await throwOnError(res);
  const data = await res.json();
  return Array.isArray(data.history) ? data.history : [];
}

/** DELETE /api/history/{sessionId} (清空会话历史) */
export async function deleteHistory(sessionId: string): Promise<void> {
  const res = await fetch(
    `${API_BASE}/api/history/${encodeURIComponent(sessionId)}`,
    { method: "DELETE" },
  );
  await throwOnError(res);
}

/* ------------------------------------------------------------------ */
/* 上传 (Session-MVVM V0: 自 ImportPage 收敛至此)                       */
/* ------------------------------------------------------------------ */

/** POST /api/upload (multipart/form-data) → 返回 task_id, 随后经 /api/upload/sse/{task_id} 推流 */
export async function postUpload(file: File): Promise<ImportUploadResponse> {
  const formData = new FormData();
  formData.append("file", file);
  const res = await fetch(`${API_BASE}/api/upload`, {
    method: "POST",
    body: formData,
  });
  await throwOnError(res);
  return await res.json();
}
