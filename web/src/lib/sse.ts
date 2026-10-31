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
import type { ChildProgressResponse, StatusResponse } from "@/types/app";
import type { ForkResponse } from "@/types/docs";
import type { TokenUsageSnapshot } from "@/types/tokenUsage";

export interface SseHandlers {
  onOpen?: () => void;
  /** progress 事件（父任务；data 解析失败时为 null，透传原样） */
  onProgress?: (data: StatusResponse | null) => void;
  /** fork 事件（ZIP 解压校验完成，下发 md 子任务清单） */
  onFork?: (data: ForkResponse | null) => void;
  /** child-progress 事件（单个 md 子任务进度） */
  onChildProgress?: (data: ChildProgressResponse | null) => void;
  /** delta 事件（仅非空 delta 触发） */
  onDelta?: (delta: string) => void;
  /** final 事件（data 可能为 null，透传原样） */
  onFinal?: (data: StatusResponse | null) => void;
  /** usage 事件（请求结束前的 Token 统计快照；data 解析失败时为 null） */
  onUsage?: (data: TokenUsageSnapshot | null) => void;
  /** usage-delta 事件（单次模型调用的 Token 增量，调用返回即推送） */
  onUsageDelta?: (kind: string, tokens: number) => void;
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

  es.addEventListener("fork", (e) => {
    const d = parseEventData<ForkResponse>((e as MessageEvent).data);
    handlers.onFork?.(d);
  });

  es.addEventListener("child-progress", (e) => {
    const d = parseEventData<ChildProgressResponse>((e as MessageEvent).data);
    handlers.onChildProgress?.(d);
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

  es.addEventListener("usage", (e) => {
    const d = parseEventData<TokenUsageSnapshot>((e as MessageEvent).data);
    handlers.onUsage?.(d);
  });

  es.addEventListener("usage-delta", (e) => {
    const d = parseEventData<{ kind?: string; tokens?: number }>(
      (e as MessageEvent).data,
    );
    if (d?.kind && typeof d.tokens === "number" && d.tokens > 0) {
      handlers.onUsageDelta?.(d.kind, d.tokens);
    }
  });

  es.addEventListener("__close__", () => {
    handlers.onServerClose?.();
    close();
  });

  es.addEventListener("error", (e) => {
    let msg = "SSE 连接中断/失败";
    let serverError = false;
    try {
      const raw = (e as MessageEvent).data;
      if (raw) {
        serverError = true;
        msg = JSON.parse(raw).error || msg;
      }
    } catch {
      /* ignore */
    }
    handlers.onError?.(msg);
    // 服务端业务错误 (带 data) 后一定会再发 __close__（查询流与导入流已对齐）；
    // 只有原生连接错误（无 data）才立即关流
    if (!serverError) close();
  });

  return { es, close };
}
