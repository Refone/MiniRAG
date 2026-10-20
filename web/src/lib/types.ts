export type PageKey = "chat" | "import";

export interface ProgressView {
  done: string[];
  running: string[];
  status: string;
}

export interface ChatMessage {
  id: string;
  role: "user" | "bot";
  text: string;
  time: string;
  hint?: string;
  typing: boolean;
  /** 是否处于 SSE 流式输出中：用于图片语法未写完时的占位截流 */
  streaming: boolean;
  progress: ProgressView | null;
  error: string | null;
}

export interface HistoryItem {
  role: string;
  text: string;
  timestamp: number;
}

export interface QueryResponse {
  session_id: string;
  answer?: string;
  done_list?: string[];
  error?: string;
  message?: string;
}

export type ImportStatus = "uploading" | "processing" | "completed" | "error";

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

export interface StatusResponse {
  status: string;
  done_list?: string[];
  running_list?: string[];
  answer?: string;
  error?: string;
}
