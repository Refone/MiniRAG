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
 * 上传任务状态响应 /api/upload/status/{task_id}
 */
export interface UploadStatusResponse {
  task_id: string;
  status: string;
  running_nodes: string[];
  done_nodes: string[];
  result: Record<string, any>;
}

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
