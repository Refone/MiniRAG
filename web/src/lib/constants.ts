/** 集中常量（跨模块共享；模块私有常量就近保留） */

import type { PageKey } from "@/types/app";
import type { ImportStatus, PreviewMode } from "@/types/docs";

/* ==================== storage key ==================== */

/** 会话身份（后端会话绑定，沿用现状 localStorage 机制） */
export const SESSION_KEY = "kb_session_id";
/** 主题 localStorage key（现状 ThemeContext 使用；Phase 2 迁入 preferenceStore 后废弃） */
export const THEME_STORAGE_KEY = "kb_theme";

/* ==================== 页面配置 ==================== */

export const PAGE_TABS: { key: PageKey; label: string; icon: string }[] = [
  { key: "chat", label: "对话", icon: "💬" },
  { key: "import", label: "文档管理", icon: "📚" },
];

/* ==================== 对话域 ==================== */

export const WELCOME_TEXT =
  "你好，我是智能知识库小助手。你可以直接提问，我会在“阶段进度”里展示处理过程。";
export const WELCOME_HINT = "提示：可以问“如何使用万用表测量电压？”";
export const PROGRESS_STATUS_LABELS: Record<string, string> = {
  processing: "处理中",
  completed: "已完成",
  failed: "失败",
  pending: "等待中",
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

/** 导入任务状态展示（取代原 STATUS_LABELS + STATUS_CLASSES 两份映射） */
export const IMPORT_STATUS: {
  value: ImportStatus;
  label: string;
  className: string;
}[] = [
  { value: "uploading", label: "上传中...", className: "status-uploading" },
  { value: "processing", label: "处理中...", className: "status-processing" },
  { value: "completed", label: "已完成", className: "status-completed" },
  { value: "error", label: "失败", className: "status-error" },
];

/** 上传区文件类型约束 */
export const UPLOAD_ACCEPT = ".pdf,.md,.markdown,.zip";

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
