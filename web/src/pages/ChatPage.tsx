import {
  memo,
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
import { useScrollRestore } from "@/lib/scrollRestore";
import { useChatStore } from "@/stores/chatStore";
import type { ChatMessage, ProgressView } from "@/lib/types";

interface AnswerContentProps {
  text: string;
  streaming?: boolean;
  showPlaceholder?: boolean;
}

function AnswerContent({
  text,
  streaming = false,
  showPlaceholder,
}: AnswerContentProps) {
  const display =
    text.trim().length > 0
      ? text
      : showPlaceholder
        ? "（已完成，但未返回答案）"
        : "";

  return (
    <>{display && <MarkdownContent text={display} streaming={streaming} />}</>
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

const MessageBubble = memo(function MessageBubble({
  message,
}: {
  message: ChatMessage;
}) {
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
          streaming={message.streaming}
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
});

/**
 * 对话页 (Session-MVVM V0 改造后):
 * - 消息流/发送/开关/SSE 全部在 chatStore (切 Tab 不断流);
 * - 页面仅保留纯视觉私有状态: input 草稿、健康检查、refs、滚动/自适应。
 */
export function ChatPage() {
  const messages = useChatStore((s) => s.messages);
  const sending = useChatStore((s) => s.sending);
  const enableWebSearch = useChatStore((s) => s.enableWebSearch);
  const enableHyde = useChatStore((s) => s.enableHyde);
  const setEnableWebSearch = useChatStore((s) => s.setEnableWebSearch);
  const setEnableHyde = useChatStore((s) => s.setEnableHyde);
  const send = useChatStore((s) => s.send);
  const clearHistory = useChatStore((s) => s.clearHistory);

  /* ---- 页面私有状态 (Activity 保活保留) ---- */
  const [input, setInput] = useState("");
  const [apiConnected, setApiConnected] = useState(false);

  const chatRef = useRef<HTMLDivElement>(null);
  const inputRef = useRef<HTMLTextAreaElement>(null);
  /** 聊天页容器：用于计算 composer 的动态高度上限（页面高度 50%） */
  const pageRef = useRef<HTMLDivElement>(null);
  /** composer 卡片：测量 footer 等固定开销 */
  const composerRef = useRef<HTMLDivElement>(null);
  /** 上一次的健康检查结果：只在「已连接/不可用」变化时打日志，否则 5 秒一次会刷屏 */
  const healthRef = useRef<boolean | null>(null);

  // 滚动守卫 + 贴底跟随模式 (测试反馈 #4/#2):
  // - DOM 由 <Activity> 完整保留, 不做"记录偏移 + 事后滑动";
  // - 浏览器可能重置 display:none 容器的 scrollTop, useScrollRestore 持续被动
  //   记录并在切回时于 paint 前恢复, 无可见跳动;
  // - 贴底 (pinnedRef) 时消息变化跟随到底: 发送/流式增量跟随, 用户上翻阅读后
  //   不再强制滚动, 切回 Tab 保持原位置。
  const { pinnedRef } = useScrollRestore(chatRef, { followBottom: true });

  // 贴底时消息变化跟随到底 (发送/流式增量)
  useEffect(() => {
    const el = chatRef.current;
    if (!el) return;
    if (pinnedRef.current) el.scrollTop = el.scrollHeight;
  }, [messages, pinnedRef]);

  // 健康检查（60 秒轮询）。保留在页面: Activity 隐藏时 effect 销毁、轮询暂停,
  // 恢复时重建 (设计文档 §4.1 决策)。
  const checkHealth = useCallback(async () => {
    let connected = false;
    let failure: unknown = null;
    try {
      const res = await fetch(`${API_BASE}/api/health`);
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
    const timer = setInterval(checkHealth, 60000);
    return () => clearInterval(timer);
  }, [checkHealth]);

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

  const onSend = useCallback(() => {
    const text = input.trim();
    if (!text || sending) return;
    setInput("");
    void send(text);
  }, [input, sending, send]);

  const onKeyDown = (e: KeyboardEvent<HTMLTextAreaElement>) => {
    if (e.key === "Enter" && !e.shiftKey) {
      e.preventDefault();
      onSend();
    }
  };

  const handleClearHistory = useCallback(() => {
    if (!window.confirm("确定要清空当前会话的历史记录吗？这将无法恢复。"))
      return;
    void clearHistory();
  }, [clearHistory]);

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
              className={`tool-pill${enableWebSearch ? " active" : ""}`}
              onClick={() => setEnableWebSearch(!enableWebSearch)}
              aria-pressed={enableWebSearch}
              title="开启后回答会结合网络搜索结果"
            >
              网络搜索
            </button>

            <button
              type="button"
              className={`tool-pill${enableHyde ? " active" : ""}`}
              onClick={() => setEnableHyde(!enableHyde)}
              aria-pressed={enableHyde}
              title="开启后先由模型生成假设性回答，再据此在知识库中检索"
            >
              HyDE 搜索
            </button>

            <span className="api-status" title="查询服务连接状态">
              <span className={`api-dot${apiConnected ? " ok" : " bad"}`} />
              {apiConnected ? "服务已连接" : "服务未连接"}
            </span>

            <button
              type="button"
              className="composer-clear"
              onClick={handleClearHistory}
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
