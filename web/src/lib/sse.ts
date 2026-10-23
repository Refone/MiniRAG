/**
 * 统一 SSE 生命周期封装（合并 chatStore 查询流与 docsStore 上传流的重复块）：
 * - closed 守卫：close 幂等；
 * - progress/delta/final 事件统一 parseEventData；
 * - 不在终态事件时关流, 等收到服务端 __close__ 信号再关闭连接；
 * - error 统一消息提取（原生连接错误与服务端 event: error 共用回调）。
 *
 * 返回 handle：{ es } 供调用方持有连接引用（生命周期=会话，切 Tab 不断流），
 * { close } 手动关闭（内部已幂等）。
 */
import type { StatusResponse } from "@/types/app";

export interface SseHandlers {
  onOpen?: () => void;
  /** progress 事件（data 解析失败时为 null，透传原样） */
  onProgress?: (data: StatusResponse | null) => void;
  /** delta 事件（仅非空 delta 触发） */
  onDelta?: (delta: string) => void;
  /** final 事件（data 可能为 null，透传原样） */
  onFinal?: (data: StatusResponse | null) => void;
  /** 连接中断/失败（消息已提取） */
  onError?: (message: string) => void;
  /** 收到服务端 __close__ 信号 */
  onServerClose?: () => void;
}

export interface SseHandle {
  es: EventSource;
  close: () => void;
}

function parseEventData<T>(data: string): T | null {
  try {
    return JSON.parse(data || "{}") as T;
  } catch {
    return null;
  }
}

export function openStatusSse(url: string, handlers: SseHandlers): SseHandle {
  const es = new EventSource(url);
  let closed = false;

  const close = () => {
    if (closed) return;
    closed = true;
    es.close();
  };

  es.addEventListener("open", () => handlers.onOpen?.());

  es.addEventListener("progress", (e) => {
    const d = parseEventData<StatusResponse>((e as MessageEvent).data);
    handlers.onProgress?.(d);
  });

  es.addEventListener("delta", (e) => {
    const d = parseEventData<{ delta?: string }>((e as MessageEvent).data);
    const delta = d?.delta || "";
    if (delta) handlers.onDelta?.(delta);
  });

  es.addEventListener("final", (e) => {
    const d = parseEventData<StatusResponse>((e as MessageEvent).data);
    handlers.onFinal?.(d);
  });

  es.addEventListener("__close__", () => {
    handlers.onServerClose?.();
    close();
  });

  es.addEventListener("error", (e) => {
    let msg = "SSE 连接中断/失败";
    try {
      const raw = (e as MessageEvent).data;
      if (raw) msg = JSON.parse(raw).error || msg;
    } catch {
      /* ignore */
    }
    handlers.onError?.(msg);
    close();
  });

  return { es, close };
}
