import { useCallback, useEffect, useRef, useState } from "react";
import { ChatComposer } from "@/components/chat/ChatComposer";
import { MessageBubble } from "@/components/chat/MessageBubble";
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
  const send = useChatStore((s) => s.send);
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

  // 图片懒加载 / progress 展开等会改变消息区高度，贴底时持续跟随
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

  const handleHeightChange = useCallback(
    (h: number) => {
      if (!chatRef.current) return;
      chatRef.current.style.paddingBottom = `${h + 28}px`;
      keepBottom();
    },
    [keepBottom],
  );

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
        onHeightChange={handleHeightChange}
      />
    </div>
  );
}
