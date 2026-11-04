/** 集中常量（跨模块共享；模块私有常量就近保留） */

import type { PageKey, TaskStatus } from "@/types/app";
import type { ImportChildStatus, ImportStatus, PreviewMode } from "@/types/docs";
import type { TokenKind, TokenScope } from "@/types/tokenUsage";

/* ==================== storage key ==================== */

/** 会话身份（后端会话绑定，沿用现状 localStorage 机制） */
export const SESSION_KEY = "kb_session_id";
/** 偏好持久层 persist 名（全新 key 起步，不迁移；旧 key 由 tools/clean_web_cache.py 清理） */
export const PREFERENCE_STORE_NAME = "kb-preferences";

/* ==================== 页面配置 ==================== */

export const PAGE_TABS: { key: PageKey; label: string }[] = [
  { key: "chat", label: "对话" },
  { key: "docs", label: "文档管理" },
];

/* ==================== 对话域 ==================== */

export const WELCOME_TEXT =
  "你好，我是智能知识库小助手。你可以直接提问，我会在“阶段进度”里展示处理过程。";
export const WELCOME_HINT = "提示：可以问“如何使用万用表测量电压？”";
/** 任务状态文案（与后端 TaskStatus 1:1；查询卡片与导入卡片共用） */
export const TASK_STATUS_LABELS: Record<TaskStatus, string> = {
  pending: "等待中",
  processing: "处理中",
  complete: "已完成",
  failed: "失败",
};
/** 查询服务健康检查轮询间隔（ms） */
export const HEALTH_INTERVAL = 60_000;

/* ==================== 文档域 ==================== */

/** 预览模式顺序即分段开关顺序（取代原 MODE_ORDER + MODE_LABELS 两份映射） */
export const PREVIEW_MODES: { value: PreviewMode; label: string }[] = [
  { value: "markdown", label: "原文" },
  { value: "chunks", label: "切块" },
  { value: "features", label: "特征" },
];

export interface StatusMeta {
  label: string;
  /** 仅样式用；className 里的 completed / error 是历史 CSS 名，与状态值无关 */
  className: string;
}

/** 导入任务状态展示（Record 覆盖全部取值，不再需要 find + 兜底） */
export const IMPORT_STATUS_META: Record<ImportStatus, StatusMeta> = {
  uploading: { label: "上传中...", className: "status-uploading" },
  pending: { label: "等待中", className: "status-pending" },
  processing: { label: "处理中...", className: "status-processing" },
  complete: { label: "已完成", className: "status-completed" },
  failed: { label: "失败", className: "status-error" },
};

/** ZIP 子任务状态展示（interrupted 为前端派生态） */
export const IMPORT_CHILD_STATUS_META: Record<ImportChildStatus, StatusMeta> = {
  pending: { label: "等待中", className: "status-pending" },
  processing: { label: "处理中...", className: "status-processing" },
  complete: { label: "已完成", className: "status-completed" },
  failed: { label: "失败", className: "status-error" },
  interrupted: { label: "未完成", className: "status-interrupted" },
};

/** 上传区文件类型约束 */
export const UPLOAD_ACCEPT = ".pdf,.md,.markdown,.zip";

/* ==================== Token 统计域 ==================== */

/** 四模型展示行（顺序即面板行顺序；model 为后端配置的真实模型名） */
export const TOKEN_KINDS: { key: TokenKind; label: string; model: string }[] = [
  { key: "llm", label: "LLM", model: "deepseek-v4.1-flash" },
  { key: "vlm", label: "VLM", model: "qwen3-vl-plus" },
  { key: "embedding", label: "Embedding", model: "text-embedding-v4" },
  { key: "reranker", label: "Reranker", model: "qwen3.7-text-rerank" },
];

/** 统计口径 tab 顺序（与 demo 一致：会话总计 ｜ 查询消耗 ｜ 上传消耗） */
export const TOKEN_SCOPE_OPTIONS: { value: TokenScope; label: string }[] = [
  { value: "total", label: "会话总计" },
  { value: "query", label: "查询消耗" },
  { value: "upload", label: "上传消耗" },
];

export const TOKEN_SCOPE_LABELS: Record<TokenScope, string> = {
  total: "会话总计",
  query: "查询消耗",
  upload: "上传消耗",
};

/** 各口径空态文案（demo 文案原样） */
export const TOKEN_SCOPE_EMPTY: Record<TokenScope, string> = {
  total: "本次访问还没有消耗 Token，发送消息或上传文档后开始统计。",
  query: "本次访问还没有查询消耗，发送一条消息后开始统计。",
  upload: "本次访问还没有上传消耗，上传文档后开始统计。",
};

/* ==================== 缓存 key 与 TTL ==================== */

export const CACHE_KEY = {
  docsList: "docs:list",
  docsDetail: (docId: string) => `docs:detail:${docId}`,
  history: (sessionId: string) => `history:${sessionId}`,
} as const;

export const TTL = {
  history: 30_000,
  docsList: 30_000,
  docsDetail: 300_000,
} as const;

/** toast 自动消失时长（ms） */
export const TOAST_DURATION = 3200;
