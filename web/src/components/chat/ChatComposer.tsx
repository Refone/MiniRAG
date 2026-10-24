import {
  useCallback,
  useEffect,
  useRef,
  type KeyboardEvent,
  type RefObject,
} from "react";

interface ChatComposerProps {
  value: string;
  onChange: (v: string) => void;
  onSend: () => void;
  sending: boolean;
  enableWebSearch: boolean;
  enableHyde: boolean;
  onToggleWebSearch: () => void;
  onToggleHyde: () => void;
  apiConnected: boolean;
  onClearHistory: () => void;
  /** 页面容器：用于计算 textarea 动态高度上限（页面高度 50%） */
  containerRef: RefObject<HTMLDivElement | null>;
  /** 卡片实际高度变化回调（页面据此设置会话区 paddingBottom） */
  onHeightChange?: (h: number) => void;
}

/**
 * 悬浮输入卡片（自 ChatPage 内联 JSX 原样平移）：
 * - textarea 高度随内容动态伸缩（上限 = 页面高度 50% - 卡内固定开销）
 * - 挂载自动聚焦；Enter 发送 / Shift+Enter 换行
 * - 工具开关（网络搜索 / HyDE）、服务状态点、清空历史、发送按钮
 */
export function ChatComposer({
  value,
  onChange,
  onSend,
  sending,
  enableWebSearch,
  enableHyde,
  onToggleWebSearch,
  onToggleHyde,
  apiConnected,
  onClearHistory,
  containerRef,
  onHeightChange,
}: ChatComposerProps) {
  const inputRef = useRef<HTMLTextAreaElement>(null);
  /** 卡片自身：测量 footer 等固定开销 */
  const composerRef = useRef<HTMLDivElement>(null);

  // 自动聚焦输入框（原 ChatPage effect 平移）
  useEffect(() => {
    const timer = setTimeout(() => inputRef.current?.focus(), 200);
    return () => clearTimeout(timer);
  }, []);

  const autoResize = useCallback(() => {
    const ta = inputRef.current;
    const page = containerRef.current;
    const composer = composerRef.current;
    if (!ta || !page || !composer) return;
    ta.style.height = "auto";
    // 卡内除 textarea 外的固定开销（内边距/gap/footer）
    const chrome = composer.clientHeight - ta.clientHeight;
    const maxH = Math.max(80, Math.round(page.clientHeight * 0.5) - chrome);
    ta.style.maxHeight = `${maxH}px`;
    ta.style.height = `${Math.min(ta.scrollHeight, maxH)}px`;
  }, [containerRef]);

  // 内容变化（输入/发送清空）时重算高度
  useEffect(() => {
    autoResize();
  }, [value, autoResize]);

  // 窗口尺寸变化时重算上限
  useEffect(() => {
    window.addEventListener("resize", autoResize);
    return () => window.removeEventListener("resize", autoResize);
  }, [autoResize]);

  // 卡片高度上报（页面据此设置会话区 paddingBottom，保证最后一条消息可滚到输入框上方）
  useEffect(() => {
    const composer = composerRef.current;
    if (!composer || !onHeightChange) return;
    const update = () => onHeightChange(composer.offsetHeight);
    update();
    const ro = new ResizeObserver(update);
    ro.observe(composer);
    return () => ro.disconnect();
  }, [onHeightChange]);

  const onKeyDown = (e: KeyboardEvent<HTMLTextAreaElement>) => {
    if (e.key === "Enter" && !e.shiftKey) {
      e.preventDefault();
      onSend();
    }
  };

  return (
    <div className="composer-wrap">
      <div className="composer" ref={composerRef}>
        <textarea
          ref={inputRef}
          value={value}
          onChange={(e) => {
            onChange(e.target.value);
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
            onClick={onToggleWebSearch}
            aria-pressed={enableWebSearch}
            title="开启后回答会结合网络搜索结果"
          >
            网络搜索
          </button>

          <button
            type="button"
            className={`tool-pill${enableHyde ? " active" : ""}`}
            onClick={onToggleHyde}
            aria-pressed={enableHyde}
            title="开启后先由模型生成假设性回答，再据此在知识库中检索"
          >
            HyDE 搜索
          </button>

          <div className="composer-actions">
            <span className="api-status" title="查询服务连接状态">
              <span className={`api-dot${apiConnected ? " ok" : " bad"}`} />
              {apiConnected ? "服务已连接" : "服务未连接"}
            </span>

            <button
              type="button"
              className="composer-clear"
              onClick={onClearHistory}
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
      </div>

      <div className="hint">
        快捷键：<span className="kbd">Enter</span> 发送，
        <span className="kbd">Shift</span>+<span className="kbd">Enter</span>{" "}
        换行
      </div>
    </div>
  );
}
