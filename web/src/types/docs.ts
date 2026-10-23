/** 文档管理域类型契约（含 API 请求/响应 DTO） */

/** 文档管理页预览模式 */
export type PreviewMode = "markdown" | "chunks" | "features";

/** 导入任务状态 */
export type ImportStatus = "uploading" | "processing" | "completed" | "error";

/** 导入任务文件条目（展示态） */
export interface ImportFile {
  id: string;
  name: string;
  sizeKB: string;
  status: ImportStatus;
  /** 任务开始时刻（ms 时间戳），用于展示已消耗时间 */
  startedAt: number;
  done: string[];
  running: string[];
}

/** 上传任务响应 /api/upload */
export interface ImportUploadResponse {
  task_id: string;
  status: string;
}

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
