/** 应用级、跨域共享的类型契约 */

/** 应用页面键（App.tsx 内 PageKey 状态切换即本项目的"路由"） */
export type PageKey = "chat" | "docs";

/**
 * 任务状态（与后端 `common.events.task_manager.TaskStatus` 1:1，禁止自造同义词）。
 * 前端本地态另见 `ImportStatus` 的 uploading 与 `ImportChildStatus` 的 interrupted。
 */
export type TaskStatus = "pending" | "processing" | "complete" | "failed";

/** 任务进度视图（chat/docs 双域共享，SSE progress 事件 → 展示态） */
export interface ProgressView {
  done: string[];
  running: string[];
  status: TaskStatus;
}

/** 节点内进度（后端 progress / child-progress 的可选 detail） */
export interface ProgressDetail {
  /** 与 running_list 中的节点显示名对齐 */
  node: string;
  /** 单行文案，由后端生成 */
  text: string;
  /** 进度指标：stage / done / total / chunks ... */
  metrics?: Record<string, string | number>;
}

/** 父任务 SSE 状态事件载荷（/api/query/sse 与 /api/upload/sse 的 progress） */
export interface StatusResponse {
  status: TaskStatus;
  done_list?: string[];
  running_list?: string[];
  /** 失败节点（仅失败时下发；父任务 / 旧后端可能为空） */
  failed_list?: string[];
  /** 节点内进度（旧后端无此字段） */
  detail?: ProgressDetail;
  answer?: string;
  error?: string;
}

/** ZIP 子任务 SSE 状态事件载荷（/api/upload/sse 的 child-progress） */
export interface ChildProgressResponse {
  child_id: string;
  status: TaskStatus;
  done_list?: string[];
  running_list?: string[];
  failed_list?: string[];
  /** 节点内进度（旧后端无此字段） */
  detail?: ProgressDetail;
  error?: string;
}

/** toast 通用 UI 契约（自 docsStore 上移：保证 Toast 组件零 store 依赖） */
export type ToastKind = "info" | "success" | "error";

export interface ToastItem {
  id: number;
  kind: ToastKind;
  text: string;
}
