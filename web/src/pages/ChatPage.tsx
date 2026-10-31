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
import { Toast } from "@/components/ui/Toast";
import { useApiHealth } from "@/hooks/useApiHealth";
import { useScrollRestore } from "@/hooks/useScrollRestore";
import { HEALTH_INTERVAL } from "@/lib/constants";
import { useChatStore } from "@/store/chatStore";
import { useDocsStore } from "@/store/docsStore";
import { usePreferenceStore } from "@/store/preferenceStore";

/**
 * 对话页 (Session-MVVM V0 改造后):
 * - 消息流/发送/开关/SSE 全部在 store (切 Tab 不断流);
 * - 页面仅做组合接线 + 页面私有视觉状态: input 草稿、refs、贴底跟随;
 * - 会话区与任务卡片彻底解耦：底部留白只由输入卡 + 固定卡片占位决定，
 *   卡片开合 / 存在与否都不改变滚动位置。
 */
export function ChatPage() {
  const messages = useChatStore((s) => s.messages);
  const sending = useChatStore((s) => s.sending);
  const queryTask = useChatStore((s) => s.queryTask);
  const send = useChatStore((s) => s.send);
  const dismissTask = useChatStore((s) => s.dismissTask);
  const clearHistory = useChatStore((s) => s.clearHistory);
  const toasts = useDocsStore((s) => s.toasts);
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

  // 切 Tab 的滚动位置恢复（是否贴底由 hook 按滚动位置自行判定）
  useScrollRestore(chatRef, { followBottom: true });

  /** 是否跟随最新消息：初始 / 发送 / 回到底部时开启，用户主动滚动后关闭 */
  const autoFollowRef = useRef(true);
  /** 最近一次程序化滚动到的位置：用于区分自动滚动与用户滚动 */
  const lastAutoScrollTopRef = useRef(0);
  /** 程序化滚动后的短暂窗口：内容加载引发的 scroll 事件不解除跟随 */
  const suppressAutoDisableUntilRef = useRef(0);

  /**
   * 贴到最新消息：直接滚到底部，不读取任务卡片尺寸。
   * 会话区底部留白已在 CSS 中固定（输入卡 + 收起态卡片占位），
   * 因此这里的位置与卡片开合完全无关。
   */
  const jumpToBottom = useCallback(() => {
    const el = chatRef.current;
    if (!el) return;
    el.scrollTop = el.scrollHeight;
    lastAutoScrollTopRef.current = el.scrollTop;
  }, []);

  /** 开启跟随并立即贴底（发送 / 点击回到底部） */
  const followBottomNow = useCallback(() => {
    autoFollowRef.current = true;
    setShowScrollToBottom(false);
    suppressAutoDisableUntilRef.current = performance.now() + 200;
    jumpToBottom();
  }, [jumpToBottom]);

  // 消息变化：跟随时贴底（布局阶段执行，流式输出不留空档）
  useLayoutEffect(() => {
    if (autoFollowRef.current) jumpToBottom();
  }, [messages, jumpToBottom]);

  // 图片懒加载等会话区高度变化：跟随时贴底
  useEffect(() => {
    const inner = chatRef.current?.querySelector<HTMLElement>(".chat-inner");
    if (!inner) return;
    const observer = new ResizeObserver(() => {
      if (autoFollowRef.current) jumpToBottom();
    });
    observer.observe(inner);
    return () => observer.disconnect();
  }, [jumpToBottom]);

  // 用户主动滚动（滚轮 / 触摸）立即解除跟随
  useEffect(() => {
    const el = chatRef.current;
    if (!el) return;
    const onUserScroll = () => {
      if (!autoFollowRef.current) return;
      autoFollowRef.current = false;
      setShowScrollToBottom(true);
    };
    el.addEventListener("wheel", onUserScroll, { passive: true });
    el.addEventListener("touchmove", onUserScroll, { passive: true });
    return () => {
      el.removeEventListener("wheel", onUserScroll);
      el.removeEventListener("touchmove", onUserScroll);
    };
  }, []);

  // Activity 切回：跟随时重新贴底（hook 的滚动恢复先执行）
  useLayoutEffect(() => {
    if (!autoFollowRef.current) return;
    suppressAutoDisableUntilRef.current = performance.now() + 200;
    jumpToBottom();
  }, [jumpToBottom]);

  /** 输入卡高度变化：跟随时贴底（只响应输入卡，任务卡片不触发） */
  const handleComposerResize = useCallback(() => {
    if (!autoFollowRef.current) return;
    suppressAutoDisableUntilRef.current = performance.now() + 200;
    jumpToBottom();
  }, [jumpToBottom]);

  /**
   * 会话滚动：
   * - 跟随中：位置与最近一次自动滚动不一致（拖动滚动条 / 键盘）→ 解除跟随；
   *   跟随期间隐藏「回到底部」；
   * - 跟随解除后：按离滚动底部的距离展示「回到底部」。
   */
  const handleChatScroll = useCallback(() => {
    const el = chatRef.current;
    if (!el) return;

    if (autoFollowRef.current) {
      const now = performance.now();
      if (
        now > suppressAutoDisableUntilRef.current &&
        Math.abs(el.scrollTop - lastAutoScrollTopRef.current) > 2
      ) {
        autoFollowRef.current = false;
      }
    }

    if (autoFollowRef.current) {
      setShowScrollToBottom(false);
      return;
    }

    const distance = el.scrollHeight - el.scrollTop - el.clientHeight;
    setShowScrollToBottom(distance > 20);
  }, []);

  const handleScrollToBottom = useCallback(() => {
    followBottomNow();
  }, [followBottomNow]);

  const onSend = useCallback(() => {
    const text = input.trim();
    if (!text || sending) return;
    setInput("");
    followBottomNow();
    void send(text);
  }, [input, sending, send, followBottomNow]);

  const handleClearHistory = useCallback(() => {
    if (!window.confirm("确定要清空当前会话的历史记录吗？这将无法恢复。"))
      return;
    void clearHistory().then(() => {
      // Token 统计与聊天历史独立存储，清空不影响（demo 契约文案）
      useDocsStore
        .getState()
        .pushToast("success", "已清空聊天记录，Token 统计保留在本次浏览器会话中");
    });
  }, [clearHistory]);

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
        onComposerResize={handleComposerResize}
      />
      <Toast toasts={toasts} />
    </div>
  );
}
