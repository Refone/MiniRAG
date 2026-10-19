import {
  useCallback,
  useEffect,
  useRef,
  useState,
  type KeyboardEvent,
  type ReactNode,
} from "react";
import { CompleteIcon } from "@/components/CompleteIcon";
import { LoadingIcon } from "@/components/LoadingIcon";
import { MarkdownContent } from "@/components/Markdown";
import { API_BASE } from "@/lib/api";
import {
  formatTime,
  nowTime,
  parseAnswerAndImages,
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
  showPlaceholder?: boolean;
}

function AnswerContent({ text, showPlaceholder }: AnswerContentProps) {
  const display =
    text.trim().length > 0
      ? text
      : showPlaceholder
        ? "（已完成，但未返回答案）"
        : "";

  return <>{display && <MarkdownContent text={display} />}</>;
}

const STATUS_LABELS: Record<string, string> = {
  processing: "处理中",
  completed: "已完成",
  failed: "失败",
  pending: "等待中",
};

function ProgressDetails({ progress }: { progress: ProgressView }) {
  const status = STATUS_LABELS[progress.status] || progress.status || "unknown";
  const items = [
    ...progress.done.map((text) => ({ kind: "done" as const, text })),
    ...progress.running.map((text) => ({ kind: "running" as const, text })),
  ];

  return (
    <details className="progress" open>
      <summary>{`阶段进度（已完成${progress.done.length}，进行中${progress.running.length}，状态：${status}）`}</summary>
      <ul>
        {items.length === 0 ? (
          <li>暂无进度</li>
        ) : (
          items.map((item) => (
            <li key={item.text} className="status-line">
              <span
                className={`status-line__icon status-line__icon--${item.kind}`}
              >
                {item.kind === "done" ? <CompleteIcon /> : <LoadingIcon />}
              </span>
              <span className="status-line__text">{item.text}</span>
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
      <div className="msg user">
        <div className="user-row">
          <div className="bubble">{message.text}</div>
          <div className="meta">{message.time}</div>
        </div>
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
          showPlaceholder
        />
        {message.progress && <ProgressDetails progress={message.progress} />}
      </>
    );
  }

  return (
    <div className="msg bot">
      <div className="avatar bot" aria-hidden="true">
        🧠
      </div>
      <div className="bot-body">
        {content}
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
  /** 聊天页容器：用于计算 composer 的动态高度上限（页面高度 50%） */
  const pageRef = useRef<HTMLDivElement>(null);
  /** composer 卡片：测量 footer 等固定开销 */
  const composerRef = useRef<HTMLDivElement>(null);
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
      // 返回格式见 src/api/main.py
      // { status: string, history: HistoryItem[] }
      const items: HistoryItem[] = Array.isArray(data.history)
        ? data.history
        : [];
      if (items.length === 0) return;
      console.log(`[chat] 已加载历史记录 ${items.length} 条`);

      const historyMessages: ChatMessage[] = items
        .slice()
        .reverse()
        .map((item, idx) => {
          // 兼容旧记录: 旧版图片放在结尾【图片】区块、经独立 image_urls 通道展示。
          // 现在图片一律内嵌正文, 这里把区块 URL 转成 Markdown 内嵌图片 (与正文已有 URL 去重)。
          const { text, images } = parseAnswerAndImages(item.text || "");
          const legacyImages = images.filter((u) => !text.includes(u));
          const displayText =
            legacyImages.length > 0
              ? `${text}\n\n${legacyImages.map((u) => `![参考图片](${u})`).join("\n\n")}`
              : text;
          return {
            id: `hist-${idx}-${item.timestamp ?? Date.now()}`,
            role: item.role === "user" ? "user" : "bot",
            text: displayText,
            time: formatTime(item.timestamp),
            typing: false,
            progress: null,
            error: null,
          };
        });

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

  // textarea 高度随内容动态伸缩：composer 总高上限为页面高度的 50%
  const autoResize = useCallback(() => {
    const ta = inputRef.current;
    const page = pageRef.current;
    const composer = composerRef.current;
    if (!ta || !page || !composer) return;
    ta.style.height = "auto";
    // 卡内除 textarea 外的固定开销（内边距/gap/footer）
    const chrome = composer.clientHeight - ta.clientHeight;
    const maxH = Math.max(80, Math.round(page.clientHeight * 0.5) - chrome);
    ta.style.maxHeight = `${maxH}px`;
    ta.style.height = `${Math.min(ta.scrollHeight, maxH)}px`;
  }, []);

  // 内容变化（输入/发送清空）时重算高度
  useEffect(() => {
    autoResize();
  }, [input, autoResize]);

  // 窗口尺寸变化时重算上限
  useEffect(() => {
    window.addEventListener("resize", autoResize);
    return () => window.removeEventListener("resize", autoResize);
  }, [autoResize]);

  // 会话区底部留白跟随 composer 实际高度，保证最后一条消息能滚到输入框上方
  useEffect(() => {
    const composer = composerRef.current;
    const chat = chatRef.current;
    if (!composer || !chat) return;
    const update = () => {
      chat.style.paddingBottom = `${composer.offsetHeight + 28}px`;
    };
    update();
    const ro = new ResizeObserver(update);
    ro.observe(composer);
    return () => ro.disconnect();
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
          updateMessage(botId, { text: rawAnswerText, typing: false });
        }
      });

      es.addEventListener("final", (e) => {
        const d = parseEventData<StatusResponse>((e as MessageEvent).data);
        const finalText =
          d && typeof d.answer === "string" && d.answer.trim().length > 0
            ? d.answer
            : rawAnswerText || "";
        console.log(`[chat] 回答完成（${finalText.length} 字）`);
        updateMessage(botId, {
          typing: false,
          text: finalText,
        });
        setSending(false);
      });

      // 不在 final 时关流，等收到服务端 __close__ 信号再关闭连接
      es.addEventListener("__close__", () => {
        console.log(`[chat] SSE 收到 __close__，关闭连接`);
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
    <div className="chat-page" ref={pageRef}>
      <div className="chat" ref={chatRef}>
        <div className="chat-inner">
          <div className="dayline">今天</div>
          {messages.map((m) => (
            <MessageBubble key={m.id} message={m} />
          ))}
        </div>
      </div>

      <div className="composer-wrap">
        <div className="composer" ref={composerRef}>
          <textarea
            ref={inputRef}
            value={input}
            onChange={(e) => {
              setInput(e.target.value);
              // 同步重算，避免出现一帧滚动条闪烁
              autoResize();
            }}
            onKeyDown={onKeyDown}
            placeholder="给智能知识库小助手发送消息"
          />

          <div className="composer-footer">
            <button
              type="button"
              className={`tool-pill${webSearch ? " active" : ""}`}
              onClick={() => setWebSearch(!webSearch)}
              aria-pressed={webSearch}
              title="开启后回答会结合网络搜索结果"
            >
              网络搜索
            </button>

            <span className="api-status" title="查询服务连接状态">
              <span className={`api-dot${apiConnected ? " ok" : " bad"}`} />
              {apiConnected ? "服务已连接" : "服务未连接"}
            </span>

            <button
              type="button"
              className="composer-clear"
              onClick={clearHistory}
            >
              清空历史会话
            </button>

            <button
              type="button"
              className="send"
              onClick={onSend}
              disabled={sending}
              aria-label="发送"
              title="发送（Enter）"
            >
              <svg
                width="18"
                height="18"
                viewBox="0 0 24 24"
                fill="none"
                aria-hidden="true"
              >
                <path
                  d="M12 19V5M5 12l7-7 7 7"
                  stroke="currentColor"
                  strokeWidth="2.2"
                  strokeLinecap="round"
                  strokeLinejoin="round"
                />
              </svg>
            </button>
          </div>
        </div>

        <div className="hint">
          快捷键：<span className="kbd">Enter</span> 发送，
          <span className="kbd">Shift</span>+<span className="kbd">Enter</span>{" "}
          换行
        </div>
      </div>
    </div>
  );
}
