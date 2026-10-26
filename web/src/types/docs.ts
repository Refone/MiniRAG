/** 文档管理域类型契约（含 API 请求/响应 DTO） */

/** 文档管理页预览模式 */
export type PreviewMode = "markdown" | "chunks" | "features";

/** 父任务导入状态 */
export type ImportStatus = "uploading" | "processing" | "completed" | "error";

/** ZIP 子任务展示状态（interrupted 为前端派生，不是后端状态值） */
export type ImportChildStatus =
  | "pending"
  | "processing"
  | "completed"
  | "error"
  | "interrupted";

/** ZIP 分叉出的单个 md 子任务（展示态） */
export interface ImportChildTask {
  /** 后端 child_task_id / SSE child_id（不透明字符串） */
  id: string;
  /** md stem（不含后缀） */
  title: string;
  /** 相对解压根目录的 POSIX 路径（含后缀，用于展示 / tooltip） */
  path: string;
  /** fork 列表顺序（0-based），仅用于稳定排序 */
  index: number;
  status: ImportChildStatus;
  /** first processing 的本地到达时间；pending 为 null */
  startedAt: number | null;
  /** complete / failed / interrupted 的本地时间 */
  stoppedAt: number | null;
  done: string[];
  running: string[];
  failed: string[];
  error: string;
}

/** 导入任务文件条目（展示态） */
export interface ImportFile {
  id: string;
  name: string;
  sizeKB: string;
  status: ImportStatus;
  /** 任务开始时刻（ms 时间戳），用于展示已消耗时间 */
  startedAt: number;
  done: string[];
  failed: string[];
  running: string[];
  /** ZIP fork 状态：fork 前 children 为空 */
  forked: boolean;
  children: ImportChildTask[];
}

/** fork SSE 事件中的单个子任务描述 */
export interface ForkChild {
  child_id: string;
  title: string;
  path: string;
  index: number;
}

/** fork SSE 事件载荷 */
export interface ForkResponse {
  parent_task_id: string;
  total: number;
  children: ForkChild[];
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
