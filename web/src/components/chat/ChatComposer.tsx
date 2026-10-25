import {
  useCallback,
  useEffect,
  useRef,
  type KeyboardEvent,
  type ReactNode,
  type RefObject,
} from "react";
import { ArrowDownIcon } from "@/components/icons/AppIcons";

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
  /** 是否显示「回到底部」按钮（消息列表未贴底时） */
  showScrollToBottom: boolean;
  onScrollToBottom: () => void;
  /** 页面容器：用于计算 textarea 动态高度上限（页面高度 50%） */
  containerRef: RefObject<HTMLDivElement | null>;
  /** 输入卡上方的任务状态卡片（无任务时为空） */
  statusSlot?: ReactNode;
  /**
   * 停靠区高度变化回调（页面据此设置会话区 paddingBottom）。
   * anchorH=停靠区总高，cardH=任务卡片高度（含 8px 间距），
   * follow 仅当输入卡自身高度变化时为 true —— 卡片展开/收起不触发贴底。
   */
  onHeightChange?: (anchorH: number, cardH: number, follow: boolean) => void;
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
  showScrollToBottom,
  onScrollToBottom,
  containerRef,
  statusSlot,
  onHeightChange,
}: ChatComposerProps) {
  const inputRef = useRef<HTMLTextAreaElement>(null);
  /** 卡片自身：测量 footer 等固定开销 */
  const composerRef = useRef<HTMLDivElement>(null);
  /** 停靠区（卡片槽位 + 输入卡）与卡片槽位：分别测量总高 / 卡片高 */
  const anchorRef = useRef<HTMLDivElement>(null);
  const taskSlotRef = useRef<HTMLDivElement>(null);
  /** 上一次输入卡高度：用于区分「输入卡变化」与「卡片变化」 */
  const lastComposerHRef = useRef<number | null>(null);

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

  // 停靠区高度上报（页面据此设置会话区 paddingBottom，保证最后一条消息可滚到输入框上方）：
  // 卡片槽位（display:flow-root）高度含卡片 8px 下边距，anchorH - cardH 即输入卡高度。
  // 只有输入卡自身高度变化才 follow → 贴底；任务卡片展开/收起只更新留白，不滚动消息区。
  useEffect(() => {
    const anchor = anchorRef.current;
    if (!anchor || !onHeightChange) return;

    const emit = () => {
      const anchorH = anchor.offsetHeight;
      const cardH = taskSlotRef.current?.offsetHeight ?? 0;
      const composerH = Math.max(0, anchorH - cardH);
      const follow =
        lastComposerHRef.current !== null &&
        lastComposerHRef.current !== composerH;
      lastComposerHRef.current = composerH;
      onHeightChange(anchorH, cardH, follow);
    };

    emit();
    const ro = new ResizeObserver(emit);
    ro.observe(anchor);
    if (taskSlotRef.current) ro.observe(taskSlotRef.current);
    if (composerRef.current) ro.observe(composerRef.current);
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
      <div className="composer-anchor" ref={anchorRef}>
        <div className="task-slot" ref={taskSlotRef}>
          {statusSlot}
        </div>

        <div className="composer-dock">
          <button
            type="button"
            className={`scroll-to-bottom${showScrollToBottom ? " visible" : ""}`}
            onClick={onScrollToBottom}
            aria-label="回到底部"
            title="回到底部"
            aria-hidden={!showScrollToBottom}
            tabIndex={showScrollToBottom ? 0 : -1}
          >
            <ArrowDownIcon />
          </button>

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
