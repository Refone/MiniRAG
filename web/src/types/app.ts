/** 应用级、跨域共享的类型契约 */

/** 应用页面键（App.tsx 内 PageKey 状态切换即本项目的"路由"） */
export type PageKey = "chat" | "import";

/** 任务进度视图（chat/docs 双域共享，SSE progress 事件 → 展示态） */
export interface ProgressView {
  done: string[];
  running: string[];
  status: string;
}

/** 父任务 SSE 状态事件载荷（/api/query/sse 与 /api/upload/sse 的 progress） */
export interface StatusResponse {
  status: string;
  done_list?: string[];
  running_list?: string[];
  /** 失败节点（仅失败时下发；父任务 / 旧后端可能为空） */
  failed_list?: string[];
  answer?: string;
  error?: string;
}

/** ZIP 子任务 SSE 状态事件载荷（/api/upload/sse 的 child-progress） */
export interface ChildProgressResponse {
  child_id: string;
  status: string;
  done_list?: string[];
  running_list?: string[];
  failed_list?: string[];
  error?: string;
}

/** toast 通用 UI 契约（自 docsStore 上移：保证 Toast 组件零 store 依赖） */
export type ToastKind = "info" | "success" | "error";

export interface ToastItem {
  id: number;
  kind: ToastKind;
  text: string;
}
