import {
  Fragment,
  useCallback,
  useEffect,
  useMemo,
  useRef,
  useState,
  type KeyboardEvent,
  type ReactNode,
} from "react";
import { QUERY_API_BASE } from "@/lib/api";
import {
  formatTime,
  normalizeUrl,
  nowTime,
  parseAnswerWithImages,
} from "@/lib/chatUtils";
import type {
  ChatMessage,
  HistoryItem,
  ProgressView,
  QueryResponse,
  StatusResponse,
} from "@/lib/types";

const WELCOME_TEXT =
  "你好，我是智能知识库小助手。你可以直接提问，我会在“阶段进度”里展示处理过程。";
const WELCOME_HINT = "提示：可以问“如何使用万用表测量电压？”";
const SESSION_KEY = "kb_session_id";

function makeId(prefix: string): string {
  return `${prefix}-${Math.random().toString(36).slice(2)}${Date.now().toString(36)}`;
}

function getSessionId(): string {
  let id = localStorage.getItem(SESSION_KEY);
  if (!id) {
    id =
      "sess-" + Math.random().toString(36).slice(2) + Date.now().toString(36);
    localStorage.setItem(SESSION_KEY, id);
  }
  return id;
}

function parseEventData<T>(data: string): T | null {
  try {
    return JSON.parse(data || "{}") as T;
  } catch {
    return null;
  }
}

interface AnswerContentProps {
  text: string;
  images: string[];
  showPlaceholder?: boolean;
}

function AnswerContent({ text, images, showPlaceholder }: AnswerContentProps) {
  const parsed = useMemo(
    () => parseAnswerWithImages(text, images),
    [text, images],
  );
  const display =
    parsed.text.trim().length > 0
      ? parsed.text
      : showPlaceholder
        ? "（已完成，但未返回答案）"
        : "";

  return (
    <>
      {display && <div className="whitespace-pre-wrap break-words">{display}</div>}
      {parsed.images.length > 0 && (
        <div className="mt-2.5 flex flex-col gap-2.5">
          {parsed.images.map((url) => (
            <Fragment key={url}>
              <img
                src={normalizeUrl(url)}
                alt="参考图片"
                loading="lazy"
                referrerPolicy="no-referrer"
                className="block max-h-[600px] w-auto max-w-full rounded-xl border border-slate-200 bg-white shadow-lg dark:border-slate-700"
                onError={(e) => {
                  e.currentTarget.style.display = "none";
                }}
              />
              <a
                href={normalizeUrl(url)}
                target="_blank"
                rel="noopener noreferrer"
                className="text-xs text-slate-500 no-underline break-all dark:text-slate-400"
              >
                {url}
              </a>
            </Fragment>
          ))}
        </div>
      )}
    </>
  );
}

const STATUS_LABELS: Record<string, string> = {
  processing: "处理中",
  completed: "已完成",
  failed: "失败",
  pending: "等待中",
};

function ProgressDetails({ progress }: { progress: ProgressView }) {
  const status = STATUS_LABELS[progress.status] || progress.status || "unknown";
  const lines = [
    ...progress.done.map((x) => `✅ ${x}`),
    ...progress.running.map((x) => `⏳ ${x}`),
  ];

  return (
    <details className="mt-2 rounded-xl border border-dashed border-slate-300 bg-slate-50 p-2.5 dark:border-slate-600 dark:bg-slate-800/50" open>
      <summary className="cursor-pointer select-none text-xs text-slate-500 dark:text-slate-400">
        {`阶段进度（已完成${progress.done.length}，进行中${progress.running.length}，状态：${status}）`}
      </summary>
      <ul className="ml-4 mt-2">
        {lines.length === 0 ? (
          <li className="my-1 text-xs text-slate-600 dark:text-slate-400">暂无进度</li>
        ) : (
          lines.map((line, i) => (
            <li key={i} className="my-1 text-xs text-slate-600 dark:text-slate-400">
              {line}
            </li>
          ))
        )}
      </ul>
    </details>
  );
}

function MessageBubble({ message }: { message: ChatMessage }) {
  if (message.role === "user") {
    return (
      <div className="flex items-end justify-end gap-2.5">
        <div className="flex min-w-0 flex-col items-end">
          <div className="inline-block max-w-[min(720px,76%)] rounded-2xl border border-transparent bg-indigo-600 px-3 py-2.5 text-sm leading-relaxed whitespace-pre-wrap break-words text-white">
            {message.text}
          </div>
          <div className="mt-1.5 text-[11px] text-indigo-100">{message.time}</div>
        </div>
        <div className="flex h-[34px] w-[34px] shrink-0 items-center justify-center rounded-xl bg-slate-200 text-sm text-slate-600 dark:bg-slate-700 dark:text-slate-300">
          我
        </div>
      </div>
    );
  }

  let content: ReactNode;
  if (message.error) {
    content = (
      <>
        <div className="whitespace-pre-wrap">
          抱歉，本次处理失败：{"\n"}
          {message.error}
        </div>
        {message.progress && <ProgressDetails progress={message.progress} />}
      </>
    );
  } else if (message.typing) {
    content = (
      <>
        <span className="inline-flex items-center gap-1.5">
          <span className="h-1.5 w-1.5 animate-bounce rounded-full bg-slate-400" />
          <span className="h-1.5 w-1.5 animate-bounce rounded-full bg-slate-400 [animation-delay:0.15s]" />
          <span className="h-1.5 w-1.5 animate-bounce rounded-full bg-slate-400 [animation-delay:0.3s]" />
        </span>
        {message.progress && <ProgressDetails progress={message.progress} />}
      </>
    );
  } else {
    content = (
      <>
        <AnswerContent
          text={message.text}
          images={message.images}
          showPlaceholder
        />
        {message.progress && <ProgressDetails progress={message.progress} />}
      </>
    );
  }

  return (
    <div className="flex items-end gap-2.5">
      <div className="flex h-[34px] w-[34px] shrink-0 items-center justify-center rounded-xl bg-gradient-to-br from-indigo-500 to-violet-500 text-sm text-white">
        🧠
      </div>
      <div className="min-w-0 flex-1">
        <div className="inline-block max-w-[min(720px,76%)] rounded-2xl border border-slate-200 bg-white px-3 py-2.5 text-sm leading-relaxed whitespace-pre-wrap break-words text-slate-900 dark:border-slate-700 dark:bg-slate-800 dark:text-slate-100">
          {content}
        </div>
        <div className="mt-1.5 text-[11px] text-slate-500 dark:text-slate-400">
          {message.hint ?? message.time}
        </div>
      </div>
    </div>
  );
}

export function ChatPage() {
  const [messages, setMessages] = useState<ChatMessage[]>([
    {
      id: "welcome",
      role: "bot",
      text: WELCOME_TEXT,
      time: "",
      hint: WELCOME_HINT,
      images: [],
      typing: false,
      progress: null,
      error: null,
    },
  ]);
  const [input, setInput] = useState("");
  const [isStream, setIsStream] = useState(true);
  const [apiConnected, setApiConnected] = useState(false);
  const [sending, setSending] = useState(false);
  const [sessionId] = useState(getSessionId);

  const chatRef = useRef<HTMLDivElement>(null);
  const inputRef = useRef<HTMLTextAreaElement>(null);
  const esRef = useRef<EventSource | null>(null);
  /** 上一次的健康检查结果：只在「已连接/不可用」变化时打日志，否则 5 秒一次会刷屏 */
  const healthRef = useRef<boolean | null>(null);

  const updateMessage = useCallback(
    (id: string, patch: Partial<ChatMessage>) => {
      setMessages((prev) =>
        prev.map((m) => (m.id === id ? { ...m, ...patch } : m)),
      );
    },
    [],
  );

  // 自动滚动到底部
  useEffect(() => {
    const el = chatRef.current;
    if (el) el.scrollTop = el.scrollHeight;
  }, [messages]);

  // 健康检查（30 秒轮询）
  const checkHealth = useCallback(async () => {
    let connected = false;
    let failure: unknown = null;
    try {
      const res = await fetch(`${QUERY_API_BASE}/health`);
      if (!res.ok) throw new Error(`health 返回 ${res.status}`);
      connected = true;
    } catch (err) {
      failure = err;
    }
    if (healthRef.current !== connected) {
      healthRef.current = connected;
      if (connected) console.log("[chat] 查询服务已连接");
      else console.warn("[chat] 查询服务不可用", failure);
    }
    setApiConnected(connected);
  }, []);

  useEffect(() => {
    checkHealth();
    const timer = setInterval(checkHealth, 30000);
    return () => clearInterval(timer);
  }, [checkHealth]);

  // 加载历史记录
  const loadHistory = useCallback(async () => {
    try {
      const res = await fetch(`${QUERY_API_BASE}/history/${sessionId}`);
      if (!res.ok) return;
      const data = await res.json();
      const items: HistoryItem[] = Array.isArray(data.items) ? data.items : [];
      if (items.length === 0) return;
      console.log(`[chat] 已加载历史记录 ${items.length} 条`);

      const historyMessages: ChatMessage[] = items
        .slice()
        .reverse()
        .map((item, idx) => ({
          id: `hist-${idx}-${item.ts ?? Date.now()}`,
          role: item.role === "user" ? "user" : "bot",
          text: item.text || "",
          time: formatTime(item.ts),
          images: item.image_urls || [],
          typing: false,
          progress: null,
          error: null,
        }));

      setMessages((prev) => [prev[0], ...historyMessages]);
    } catch {
      /* 历史加载失败静默处理 */
    }
  }, [sessionId]);

  useEffect(() => {
    loadHistory();
  }, [loadHistory]);

  // 自动聚焦输入框
  useEffect(() => {
    const timer = setTimeout(() => inputRef.current?.focus(), 200);
    return () => clearTimeout(timer);
  }, []);

  // 卸载时关闭 EventSource
  useEffect(() => {
    return () => esRef.current?.close();
  }, []);

  async function submitQuery(
    text: string,
    session: string,
    stream: boolean,
  ): Promise<QueryResponse> {
    const res = await fetch(`${QUERY_API_BASE}/query`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        query: text,
        session_id: session,
        is_stream: stream,
      }),
    });
    if (!res.ok) {
      const msg = await res.text();
      throw new Error(msg || "请求失败");
    }
    return await res.json();
  }

  const onSend = useCallback(async () => {
    const text = input.trim();
    if (!text || sending) return;
    setInput("");
    setSending(true);

    const userMsg: ChatMessage = {
      id: makeId("user"),
      role: "user",
      text,
      time: nowTime(),
      images: [],
      typing: false,
      progress: null,
      error: null,
    };
    const botId = makeId("bot");
    const botMsg: ChatMessage = {
      id: botId,
      role: "bot",
      text: "",
      time: nowTime(),
      images: [],
      typing: true,
      progress: { done: [], running: [], status: "pending" },
      error: null,
    };
    setMessages((prev) => [...prev, userMsg, botMsg]);

    const stream = isStream;
    console.log(
      `[chat] 发送问题（${stream ? "流式" : "非流式"}，${text.length} 字）`,
    );

    try {
      const data = await submitQuery(text, sessionId, stream);
      updateMessage(botId, {
        progress: { done: [], running: [], status: "pending" },
      });

      if (!stream) {
        // 非流式：直接拿到结果
        updateMessage(botId, {
          progress: {
            done: data.done_list || [],
            running: [],
            status: "completed",
          },
          typing: false,
          text: data.answer || "",
          images: data.image_urls || [],
          error: (data.error || "").trim() || null,
        });
        setSending(false);
        return;
      }

      // 流式：SSE
      const { session_id } = data;
      const es = new EventSource(`${QUERY_API_BASE}/stream/${session_id}`);
      esRef.current = es;
      es.addEventListener("open", () =>
        console.log(`[chat] SSE 已连接（/stream/${session_id}）`),
      );
      let rawAnswerText = "";
      let closed = false;

      const close = () => {
        if (!closed) {
          closed = true;
          es.close();
        }
      };

      es.addEventListener("progress", (e) => {
        const d = parseEventData<StatusResponse>((e as MessageEvent).data);
        updateMessage(botId, {
          progress: {
            done: d?.done_list || [],
            running: d?.running_list || [],
            status: d?.status || "processing",
          },
        });
        if (d?.status === "completed") {
          updateMessage(botId, { typing: false });
          setSending(false);
        }
      });

      es.addEventListener("delta", (e) => {
        const d = parseEventData<{ delta?: string }>((e as MessageEvent).data);
        const delta = d?.delta || "";
        if (delta) {
          rawAnswerText += delta;
          updateMessage(botId, { text: rawAnswerText });
        }
      });

      const finalize = (finalText: string, imageUrls: string[]) => {
        console.log(
          `[chat] 回答完成（${finalText.length} 字，${imageUrls.length} 张图）`,
        );
        updateMessage(botId, {
          typing: false,
          text: finalText,
          images: imageUrls,
        });
        setSending(false);
        close();
      };

      es.addEventListener("final", (e) => {
        const d = parseEventData<StatusResponse>((e as MessageEvent).data);
        const finalText =
          d && typeof d.answer === "string" && d.answer.trim().length > 0
            ? d.answer
            : rawAnswerText || "";
        finalize(finalText, d?.image_urls || []);
      });

      es.addEventListener("final_answer", (e) => {
        const d = parseEventData<StatusResponse>((e as MessageEvent).data);
        const finalText =
          d && typeof d.answer === "string" && d.answer.trim().length > 0
            ? d.answer
            : rawAnswerText || "";
        finalize(finalText, d?.image_urls || []);
      });

      es.addEventListener("error", (e) => {
        let msg = "SSE 连接中断/失败";
        try {
          const raw = (e as MessageEvent).data;
          if (raw) msg = JSON.parse(raw).error || msg;
        } catch {
          /* ignore */
        }
        console.warn(`[chat] SSE 中断：${msg}`);
        rawAnswerText += `\n\n（错误：${msg}）`;
        updateMessage(botId, { typing: false, text: rawAnswerText });
        setSending(false);
        close();
      });
    } catch (err) {
      const msg = err instanceof Error ? err.message : String(err);
      console.error("[chat] 发送问题失败", msg);
      updateMessage(botId, { typing: false, progress: null, error: msg });
      setSending(false);
    }
  }, [input, sending, isStream, sessionId, updateMessage]);

  const onKeyDown = (e: KeyboardEvent<HTMLTextAreaElement>) => {
    if (e.key === "Enter" && !e.shiftKey) {
      e.preventDefault();
      onSend();
    }
  };

  const clearHistory = useCallback(async () => {
    if (!window.confirm("确定要清空当前会话的历史记录吗？这将无法恢复。"))
      return;

    try {
      console.log(`[chat] 清空会话历史（${sessionId}）`);
      const res = await fetch(`${QUERY_API_BASE}/history/${sessionId}`, {
        method: "DELETE",
      });
      if (!res.ok) {
        console.error("[chat] 服务端清空失败，状态码:", res.status);
        window.alert("服务端清空失败，仅清空本地显示");
      }
    } catch (e) {
      console.error("[chat] 服务端清空失败", e);
      window.alert("服务端清空失败，仅清空本地显示");
    }

    setMessages((prev) => prev.slice(0, 1));
  }, [sessionId]);

  return (
    <div className="mx-auto flex min-h-0 w-full max-w-4xl flex-col overflow-hidden rounded-2xl border border-slate-200 bg-white shadow-lg dark:border-slate-800 dark:bg-slate-900">
      <div className="flex items-center gap-3 border-b border-slate-200 bg-slate-50 px-4 py-3 dark:border-slate-800 dark:bg-slate-800/50">
        <label className="flex cursor-pointer select-none items-center gap-1 text-xs text-slate-500 dark:text-slate-400">
          <input
            type="checkbox"
            className="cursor-pointer accent-indigo-600"
            checked={isStream}
            onChange={(e) => setIsStream(e.target.checked)}
          />
          流式输出
        </label>
        <span className="ml-auto rounded-full border border-slate-200 bg-white px-2.5 py-1.5 text-xs text-slate-500 dark:border-slate-700 dark:bg-slate-800 dark:text-slate-400">
          API: {apiConnected ? "已连接" : "未连接"}
        </span>
        <button
          type="button"
          className="rounded-lg bg-indigo-600 px-3 py-2 text-xs text-white transition hover:bg-indigo-500"
          onClick={clearHistory}
        >
          清空对话
        </button>
      </div>

      <div className="min-h-0 flex-1 overflow-y-auto px-3.5 py-4" ref={chatRef}>
        <div className="mb-3.5 mt-1.5 text-center text-xs text-slate-500 dark:text-slate-400">
          今天
        </div>
        {messages.map((m) => (
          <MessageBubble key={m.id} message={m} />
        ))}
      </div>

      <div className="flex items-end gap-2.5 border-t border-slate-200 bg-white p-3.5 dark:border-slate-800 dark:bg-slate-900">
        <textarea
          ref={inputRef}
          value={input}
          onChange={(e) => setInput(e.target.value)}
          onKeyDown={onKeyDown}
          placeholder="请输入问题（Enter 发送，Shift+Enter 换行）"
          className="min-h-[44px] max-h-[140px] flex-1 resize-none rounded-xl border border-slate-200 bg-white px-3 py-2.5 text-sm leading-6 text-slate-900 outline-none transition focus:border-indigo-500 focus:ring-2 focus:ring-indigo-500/20 dark:border-slate-700 dark:bg-slate-800 dark:text-slate-100"
        />
        <button
          type="button"
          className="h-11 w-[88px] rounded-xl bg-indigo-600 text-sm text-white transition hover:bg-indigo-500 disabled:cursor-not-allowed disabled:opacity-60"
          onClick={onSend}
          disabled={sending}
        >
          发送
        </button>
      </div>
      <div className="bg-white px-3.5 pb-3 text-xs text-slate-500 dark:bg-slate-900 dark:text-slate-400">
        快捷键：<span className="rounded-md border border-slate-200 bg-slate-50 px-1.5 py-0.5 font-mono text-slate-600 dark:border-slate-700 dark:bg-slate-800 dark:text-slate-300">Enter</span> 发送，
        <span className="rounded-md border border-slate-200 bg-slate-50 px-1.5 py-0.5 font-mono text-slate-600 dark:border-slate-700 dark:bg-slate-800 dark:text-slate-300">Shift</span>+
        <span className="rounded-md border border-slate-200 bg-slate-50 px-1.5 py-0.5 font-mono text-slate-600 dark:border-slate-700 dark:bg-slate-800 dark:text-slate-300">Enter</span>{" "}
        换行
      </div>
    </div>
  );
}
