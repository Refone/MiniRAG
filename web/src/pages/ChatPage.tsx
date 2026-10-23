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
  const apiConnected = useApiHealth(HEALTH_INTERVAL);

  /** 聊天页容器：用于计算 composer 的动态高度上限（页面高度 50%） */
  const pageRef = useRef<HTMLDivElement>(null);
  const chatRef = useRef<HTMLDivElement>(null);

  // 滚动守卫现状语义（BUG-003 无需看护，原样平移）：切 Tab 恢复偏移 + 贴底跟随
  const { pinnedRef } = useScrollRestore(chatRef, { followBottom: true });

  // 贴底时消息变化跟随到底 (发送/流式增量)
  useEffect(() => {
    const el = chatRef.current;
    if (!el) return;
    if (pinnedRef.current) el.scrollTop = el.scrollHeight;
  }, [messages, pinnedRef]);

  const onSend = useCallback(() => {
    const text = input.trim();
    if (!text || sending) return;
    setInput("");
    void send(text);
  }, [input, sending, send]);

  const handleClearHistory = useCallback(() => {
    if (!window.confirm("确定要清空当前会话的历史记录吗？这将无法恢复。"))
      return;
    void clearHistory();
  }, [clearHistory]);

  const handleHeightChange = useCallback((h: number) => {
    if (chatRef.current) {
      chatRef.current.style.paddingBottom = `${h + 28}px`;
    }
  }, []);

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
        containerRef={pageRef}
        onHeightChange={handleHeightChange}
      />
    </div>
  );
}
