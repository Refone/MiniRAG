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
import { API_BASE } from "@/lib/api";
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
      {display && <div className="answer-text">{display}</div>}
      {parsed.images.length > 0 && (
        <div className="answer-images">
          {parsed.images.map((url) => (
            <Fragment key={url}>
              <img
                src={normalizeUrl(url)}
                alt="参考图片"
                loading="lazy"
                referrerPolicy="no-referrer"
                onError={(e) => {
                  e.currentTarget.style.display = "none";
                }}
              />
              <a
                href={normalizeUrl(url)}
                target="_blank"
                rel="noopener noreferrer"
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
    <details className="progress" open>
      <summary>{`阶段进度（已完成${progress.done.length}，进行中${progress.running.length}，状态：${status}）`}</summary>
      <ul>
        {lines.length === 0 ? (
          <li>暂无进度</li>
        ) : (
          lines.map((line, i) => <li key={i}>{line}</li>)
        )}
      </ul>
    </details>
  );
}

function MessageBubble({ message }: { message: ChatMessage }) {
  if (message.role === "user") {
    return (
      <div className="msg user">
        <div>
          <div className="bubble">{message.text}</div>
          <div className="meta">{message.time}</div>
        </div>
        <div className="avatar">我</div>
      </div>
    );
  }

  let content: ReactNode;
  if (message.error) {
    content = (
      <>
        <div className="answer">
          抱歉，本次处理失败：{"\n"}
          {message.error}
        </div>
        {message.progress && <ProgressDetails progress={message.progress} />}
      </>
    );
  } else if (message.typing) {
    content = (
      <>
        <span className="typing">
          <span className="dot" />
          <span className="dot" />
          <span className="dot" />
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
    <div className="msg bot">
      <div className="avatar bot">🧠</div>
      <div>
        <div className="bubble">{content}</div>
        <div className="meta">{message.hint ?? message.time}</div>
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
  const [webSearch, setWebSearch] = useState(true);
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
      const res = await fetch(`${API_BASE}/health`);
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
      const res = await fetch(`${API_BASE}/history/${sessionId}`);
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
    webSearch: boolean,
  ): Promise<QueryResponse> {
    const res = await fetch(`${API_BASE}/query`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        query: text,
        session_id: session,
        web_search: webSearch,
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

    console.log(`[chat] 发送问题（网络搜索=${webSearch}，${text.length} 字）`);

    try {
      const data = await submitQuery(text, sessionId, webSearch);
      updateMessage(botId, {
        progress: { done: [], running: [], status: "pending" },
      });

      // 流式：SSE
      const { session_id } = data;
      const es = new EventSource(`${API_BASE}/query/sse/${session_id}`);
      esRef.current = es;
      es.addEventListener("open", () =>
        console.log(`[chat] SSE 已连接（/query/sse/${session_id}）`),
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
  }, [input, sending, webSearch, sessionId, updateMessage]);

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
      const res = await fetch(`${API_BASE}/history/${sessionId}`, {
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
    <div className="chat-page">
      <div className="chat-toolbar">
        <label className="stream-toggle">
          <input
            type="checkbox"
            checked={webSearch}
            onChange={(e) => setWebSearch(e.target.checked)}
          />
          网络搜索
        </label>
        <span className="pill">API: {apiConnected ? "已连接" : "未连接"}</span>
        <button type="button" className="btn" onClick={clearHistory}>
          清空对话
        </button>
      </div>

      <div className="chat" ref={chatRef}>
        <div className="dayline">今天</div>
        {messages.map((m) => (
          <MessageBubble key={m.id} message={m} />
        ))}
      </div>

      <div className="composer">
        <textarea
          ref={inputRef}
          value={input}
          onChange={(e) => setInput(e.target.value)}
          onKeyDown={onKeyDown}
          placeholder="请输入问题（Enter 发送，Shift+Enter 换行）"
        />
        <button
          type="button"
          className="send"
          onClick={onSend}
          disabled={sending}
        >
          发送
        </button>
      </div>
      <div className="hint">
        快捷键：<span className="kbd">Enter</span> 发送，
        <span className="kbd">Shift</span>+<span className="kbd">Enter</span>{" "}
        换行
      </div>
    </div>
  );
}
