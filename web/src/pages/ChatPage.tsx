import {
  useCallback,
  useEffect,
  useLayoutEffect,
  useRef,
  useState,
} from "react";
import { ChatComposer } from "@/components/chat/ChatComposer";
import { MessageBubble } from "@/components/chat/MessageBubble";
import { QueryTaskBar } from "@/components/chat/QueryTaskBar";
import { useApiHealth } from "@/hooks/useApiHealth";
import { useScrollRestore } from "@/hooks/useScrollRestore";
import { HEALTH_INTERVAL } from "@/lib/constants";
import { useChatStore } from "@/store/chatStore";
import { usePreferenceStore } from "@/store/preferenceStore";

/**
 * 对话页 (Session-MVVM V0 改造后):
 * - 消息流/发送/开关/SSE 全部在 store (切 Tab 不断流);
 * - 页面仅做组合接线 + 页面私有视觉状态: input 草稿、refs、贴底跟随。
 */
export function ChatPage() {
  const messages = useChatStore((s) => s.messages);
  const sending = useChatStore((s) => s.sending);
  const queryTask = useChatStore((s) => s.queryTask);
  const send = useChatStore((s) => s.send);
  const dismissTask = useChatStore((s) => s.dismissTask);
  const clearHistory = useChatStore((s) => s.clearHistory);
  const enableWebSearch = usePreferenceStore((s) => s.enableWebSearch);
  const enableHyde = usePreferenceStore((s) => s.enableHyde);
  const setEnableWebSearch = usePreferenceStore((s) => s.setEnableWebSearch);
  const setEnableHyde = usePreferenceStore((s) => s.setEnableHyde);

  /* ---- 页面私有状态 (Activity 保活保留) ---- */
  const [input, setInput] = useState("");
  const [showScrollToBottom, setShowScrollToBottom] = useState(false);
  const apiConnected = useApiHealth(HEALTH_INTERVAL);

  /** 聊天页容器：用于计算 composer 的动态高度上限（页面高度 50%） */
  const pageRef = useRef<HTMLDivElement>(null);
  const chatRef = useRef<HTMLDivElement>(null);

  // 滚动守卫现状语义（BUG-003 无需看护，原样平移）：切 Tab 恢复偏移 + 贴底跟随
  const { pinnedRef } = useScrollRestore(chatRef, { followBottom: true });

  /** 用户主动发送时强制贴底（即使此前上翻阅读） */
  const forceBottomRef = useRef(false);
  const scrollRafRef = useRef(0);

  /**
   * 任务卡片高度高水位（P1）：手动展开只增、手动收起不减，
   * 保证留白不缩短 → 浏览器不会因 max scrollTop 变小而钳制 scrollTop。
   * 新查询 / 终态 / 清空时归零，由卡片收起后的高度回调重新建立。
   */
  const cardHighWaterRef = useRef(0);
  /** 上一次已处理的任务 id / 终态：Activity 切回会重跑 effect，只有真正变化才重置高水位 */
  const highWaterTaskIdRef = useRef<string | null | undefined>(undefined);
  const terminalStatusRef = useRef<string | undefined>(undefined);
  const status = queryTask?.progress.status;

  /** 仅在当前处于贴底状态时跟随（流式增量 / 图片加载 / 输入卡高度变化） */
  const keepBottom = useCallback(() => {
    const el = chatRef.current;
    if (!el || !pinnedRef.current) return;
    window.cancelAnimationFrame(scrollRafRef.current);
    scrollRafRef.current = window.requestAnimationFrame(() => {
      if (pinnedRef.current) el.scrollTop = el.scrollHeight;
    });
  }, [pinnedRef]);

  /** 发送时强制贴底：先置 pinned，后续增量与图片加载继续跟随 */
  const scrollToBottom = useCallback(() => {
    pinnedRef.current = true;
    forceBottomRef.current = false;
    keepBottom();
  }, [keepBottom]);

  // 消息变化：发送时强制贴底；其余情况仅在原本贴底时跟随流式增量
  useEffect(() => {
    const el = chatRef.current;
    if (!el) return;
    if (forceBottomRef.current) {
      scrollToBottom();
      return;
    }
    if (pinnedRef.current) el.scrollTop = el.scrollHeight;
  }, [messages, pinnedRef, scrollToBottom]);

  // 图片懒加载等会改变消息区高度，贴底时持续跟随
  useEffect(() => {
    const el = chatRef.current;
    const inner = el?.querySelector<HTMLElement>(".chat-inner");
    if (!el || !inner) return;
    const observer = new ResizeObserver(() => keepBottom());
    observer.observe(inner);
    return () => observer.disconnect();
  }, [keepBottom]);

  useEffect(
    () => () => window.cancelAnimationFrame(scrollRafRef.current),
    [],
  );

  /** 消息区滚动：只要离底部超过 20px 就展示「回到底部」按钮 */
  const handleChatScroll = useCallback(() => {
    const el = chatRef.current;
    if (!el) return;
    const distance = el.scrollHeight - el.scrollTop - el.clientHeight;
    setShowScrollToBottom(distance > 20);
  }, []);

  const handleScrollToBottom = useCallback(() => {
    setShowScrollToBottom(false);
    scrollToBottom();
  }, [scrollToBottom]);

  const onSend = useCallback(() => {
    const text = input.trim();
    if (!text || sending) return;
    setInput("");
    forceBottomRef.current = true;
    setShowScrollToBottom(false);
    void send(text);
  }, [input, sending, send]);

  const handleClearHistory = useCallback(() => {
    if (!window.confirm("确定要清空当前会话的历史记录吗？这将无法恢复。"))
      return;
    void clearHistory();
  }, [clearHistory]);

  /**
   * 停靠区高度 → 会话底部留白。
   * - 高水位只增不减：卡片手动展开/收起不改变 paddingBottom，scrollTop 保持不变；
   * - 只有输入卡自身高度变化（follow=true）才继续贴底；
   * - cardH 已含卡片与输入卡之间的 8px 间距。
   */
  const handleHeightChange = useCallback(
    (anchorH: number, cardH: number, follow: boolean) => {
      const el = chatRef.current;
      if (!el) return;
      cardHighWaterRef.current = Math.max(cardHighWaterRef.current, cardH);
      const composerH = Math.max(0, anchorH - cardH);
      el.style.paddingBottom = `${composerH + 28 + cardHighWaterRef.current}px`;
      if (follow) keepBottom();
    },
    [keepBottom],
  );

  // 新查询 / 清空卡片：高水位归零，由新卡片重新积累。
  // 用 layout effect 保证先于 ResizeObserver 的高度回调，避免沿用旧卡片的高水位。
  // 用 ref 记录已处理的任务 id：Activity 切回会重跑 effect，不能把手动收起后的
  // 高水位清掉（否则切 Tab 回来留白缩短、scrollTop 被钳制）。
  useLayoutEffect(() => {
    const taskId = queryTask?.id ?? null;
    if (highWaterTaskIdRef.current === taskId) return;
    highWaterTaskIdRef.current = taskId;
    cardHighWaterRef.current = 0;
  }, [queryTask?.id]);

  // 终态：先归零，让自动收起后的卡片高度重建高水位；原本贴底时跟到答案。
  // 同样用 ref 防重：Activity 切回重跑 effect 时不再重复重置。
  useLayoutEffect(() => {
    if (status !== "completed" && status !== "failed") {
      terminalStatusRef.current = status;
      return;
    }
    if (terminalStatusRef.current === status) return;
    terminalStatusRef.current = status;
    cardHighWaterRef.current = 0;
    if (pinnedRef.current) scrollToBottom();
  }, [status, scrollToBottom, pinnedRef]);

  return (
    <div className="chat-page" ref={pageRef}>
      <div className="chat" ref={chatRef} onScroll={handleChatScroll}>
        <div className="chat-inner">
          <div className="dayline">今天</div>
          {messages.map((m) => (
            <MessageBubble key={m.id} message={m} />
          ))}
        </div>
      </div>

      <ChatComposer
        value={input}
        onChange={setInput}
        onSend={onSend}
        sending={sending}
        enableWebSearch={enableWebSearch}
        enableHyde={enableHyde}
        onToggleWebSearch={() => setEnableWebSearch(!enableWebSearch)}
        onToggleHyde={() => setEnableHyde(!enableHyde)}
        apiConnected={apiConnected}
        onClearHistory={handleClearHistory}
        showScrollToBottom={showScrollToBottom}
        onScrollToBottom={handleScrollToBottom}
        containerRef={pageRef}
        statusSlot={
          queryTask ? (
            <QueryTaskBar task={queryTask} onDismiss={dismissTask} />
          ) : undefined
        }
        onHeightChange={handleHeightChange}
      />
    </div>
  );
}
