/** 应用级、跨域共享的类型契约 */

/** 应用页面键（App.tsx 内 PageKey 状态切换即本项目的"路由"） */
export type PageKey = "chat" | "import";

/** 任务进度视图（chat/docs 双域共享，SSE progress 事件 → 展示态） */
export interface ProgressView {
  done: string[];
  running: string[];
  status: string;
}

/** SSE 状态事件载荷（/api/query/sse 与 /api/upload/sse 共用） */
export interface StatusResponse {
  status: string;
  done_list?: string[];
  running_list?: string[];
  answer?: string;
  error?: string;
}

/** toast 通用 UI 契约（自 docsStore 上移：保证 Toast 组件零 store 依赖） */
export type ToastKind = "info" | "success" | "error";

export interface ToastItem {
  id: number;
  kind: ToastKind;
  text: string;
}
