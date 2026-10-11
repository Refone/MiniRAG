export type PageKey = 'chat' | 'import';

export interface ProgressView {
  done: string[];
  running: string[];
  status: string;
}

export interface ChatMessage {
  id: string;
  role: 'user' | 'bot';
  text: string;
  time: string;
  hint?: string;
  images: string[];
  typing: boolean;
  progress: ProgressView | null;
  error: string | null;
}

export interface HistoryItem {
  role: string;
  text: string;
  ts: number;
  image_urls?: string[];
}

export interface QueryResponse {
  session_id: string;
  answer?: string;
  done_list?: string[];
  error?: string;
  image_urls?: string[];
  message?: string;
}

export interface StatusResponse {
  status: string;
  done_list?: string[];
  running_list?: string[];
  answer?: string;
  error?: string;
  image_urls?: string[];
}

export interface UploadResponse {
  task_ids: string[];
}

export type ImportStatus = 'uploading' | 'processing' | 'completed' | 'error';

export interface ImportFile {
  id: string;
  name: string;
  sizeKB: string;
  status: ImportStatus;
  progress: number;
  done: string[];
  running: string[];
}
