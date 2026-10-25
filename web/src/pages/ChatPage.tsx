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

/** 自动跟随时，消息末尾与任务卡片顶部保留的自然间距（px） */
const AUTO_FOLLOW_GAP = 8;

/**
 * 对话页 (Session-MVVM V0 改造后):
 * - 消息流/发送/开关/SSE 全部在 store (切 Tab 不断流);
 * - 页面仅做组合接线 + 页面私有视觉状态: input 草稿、refs、贴底跟随;
 * - P1 自动跟随：用户未滚动时，消息末尾始终贴在任务卡片顶部；
 *   用户主动滚动后解除跟随，卡片高度 / 答案输出不再推动消息区。
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

  const scrollRafRef = useRef(0);

  /**
   * 任务卡片高度高水位（P1）：手动展开只增、手动收起不减，
   * 保证留白不缩短 → 浏览器不会因 max scrollTop 变小而钳制 scrollTop。
   * 新查询 / 清空时归零，由卡片收起后的高度回调重新建立。
   */
  const cardHighWaterRef = useRef(0);
  /** 上一次已处理的任务 id：Activity 切回会重跑 effect，只有真正变化才重置高水位 */
  const highWaterTaskIdRef = useRef<string | null | undefined>(undefined);

  /** 最新任务快照：供 observer / 滚动回调读取，不触发额外渲染 */
  const queryTaskRef = useRef(queryTask);
  queryTaskRef.current = queryTask;

  /** 自动跟随开关：发送 / 点击回到底部时开启；用户主动滚动后关闭 */
  const autoFollowRef = useRef(false);
  /** 最近一次自动滚动的 scrollTop：用于区分自动滚动与用户滚动 */
  const lastAutoScrollTopRef = useRef(0);
  /** 卡片 / 输入区高度变化后的短暂窗口，避免布局钳制被误判为用户滚动 */
  const suppressAutoDisableUntilRef = useRef(0);

  /** 仅在当前处于贴底状态时跟随（历史加载 / 无任务时的输入卡高度变化） */
  const keepBottom = useCallback(() => {
    const el = chatRef.current;
    if (!el || !pinnedRef.current) return;
    window.cancelAnimationFrame(scrollRafRef.current);
    scrollRafRef.current = window.requestAnimationFrame(() => {
      if (pinnedRef.current) el.scrollTop = el.scrollHeight;
    });
  }, [pinnedRef]);

  /**
   * 无交互自动跟随：把最后一条消息的底部对齐到任务卡片顶部
   * （卡片关闭 / 不存在时对齐到输入卡上方）。只改 scrollTop，
   * 留白仍用高水位，卡片变高变低不会顶动输入区或按钮。
   */
  const alignFollowNow = useCallback(() => {
    const el = chatRef.current;
    const page = pageRef.current;
    if (!el || !page || !autoFollowRef.current) return;

    const msgNodes = el.querySelectorAll<HTMLElement>(".chat-inner .msg");
    const lastMsg = msgNodes[msgNodes.length - 1];
    if (!lastMsg) return;

    const slot = page.querySelector<HTMLElement>(".task-slot");
    const composer = page.querySelector<HTMLElement>(".composer");
    const anchor = slot && slot.offsetHeight > 0 ? slot : composer;
    if (!anchor) return;

    const targetBottom = anchor.getBoundingClientRect().top - AUTO_FOLLOW_GAP;
    const lastBottom = lastMsg.getBoundingClientRect().bottom;
    const max = el.scrollHeight - el.clientHeight;
    const next = Math.min(max, Math.max(0, el.scrollTop + lastBottom - targetBottom));
    if (Math.abs(next - el.scrollTop) > 0.5) el.scrollTop = next;
    lastAutoScrollTopRef.current = el.scrollTop;
  }, []);

  /** 关闭自动跟随 */
  const disableAutoFollow = useCallback(() => {
    autoFollowRef.current = false;
    window.cancelAnimationFrame(scrollRafRef.current);
  }, []);

  /** 开启自动跟随：记录当前滚动位置作为自动滚动的起点 */
  const enableAutoFollow = useCallback(() => {
    autoFollowRef.current = true;
    const el = chatRef.current;
    if (el) lastAutoScrollTopRef.current = el.scrollTop;
  }, []);

  // 消息变化：自动跟随开启时由 layout effect 对齐卡片顶部；否则只在无任务时维持既有贴底行为
  useLayoutEffect(() => {
    if (autoFollowRef.current) alignFollowNow();
  }, [messages, alignFollowNow]);

  useEffect(() => {
    const el = chatRef.current;
    if (!el) return;
    if (autoFollowRef.current) return;
    if (queryTaskRef.current) return;
    if (pinnedRef.current) el.scrollTop = el.scrollHeight;
  }, [messages, pinnedRef]);

  // 图片懒加载等消息区高度变化：自动跟随对齐卡片；无任务时维持既有贴底
  useEffect(() => {
    const el = chatRef.current;
    const inner = el?.querySelector<HTMLElement>(".chat-inner");
    if (!el || !inner) return;
    const observer = new ResizeObserver(() => {
      if (autoFollowRef.current) alignFollowNow();
      else if (!queryTaskRef.current) keepBottom();
    });
    observer.observe(inner);
    return () => observer.disconnect();
  }, [alignFollowNow, keepBottom]);

  // 用户主动滚动（滚轮 / 触摸）立即解除自动跟随；回到底部 / 新发送时重新开启
  useEffect(() => {
    const el = chatRef.current;
    if (!el) return;
    const onUserScroll = () => {
      if (!autoFollowRef.current) return;
      disableAutoFollow();
      setShowScrollToBottom(true);
    };
    el.addEventListener("wheel", onUserScroll, { passive: true });
    el.addEventListener("touchmove", onUserScroll, { passive: true });
    return () => {
      el.removeEventListener("wheel", onUserScroll);
      el.removeEventListener("touchmove", onUserScroll);
    };
  }, [disableAutoFollow]);

  // Activity 切回：自动跟随开启时重新对齐（滚动恢复在 useScrollRestore 中先执行）
  useLayoutEffect(() => {
    if (!autoFollowRef.current) return;
    suppressAutoDisableUntilRef.current = performance.now() + 200;
    alignFollowNow();
  }, [alignFollowNow]);

  useEffect(
    () => () => window.cancelAnimationFrame(scrollRafRef.current),
    [],
  );

  /**
   * 消息区滚动：
   * - 自动跟随中：位置与最近一次自动滚动不一致（用户拖动滚动条 / 键盘滚动）→ 解除跟随；
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
        disableAutoFollow();
      }
    }

    if (autoFollowRef.current) {
      setShowScrollToBottom(false);
      return;
    }

    const distance = el.scrollHeight - el.scrollTop - el.clientHeight;
    setShowScrollToBottom(distance > 20);
  }, [disableAutoFollow]);

  const handleScrollToBottom = useCallback(() => {
    setShowScrollToBottom(false);
    enableAutoFollow();
    suppressAutoDisableUntilRef.current = performance.now() + 200;
    alignFollowNow();
  }, [alignFollowNow, enableAutoFollow]);

  const onSend = useCallback(() => {
    const text = input.trim();
    if (!text || sending) return;
    setInput("");
    enableAutoFollow();
    suppressAutoDisableUntilRef.current = performance.now() + 300;
    setShowScrollToBottom(false);
    void send(text);
  }, [input, sending, send, enableAutoFollow]);

  const handleClearHistory = useCallback(() => {
    if (!window.confirm("确定要清空当前会话的历史记录吗？这将无法恢复。"))
      return;
    void clearHistory();
  }, [clearHistory]);

  /**
   * 停靠区高度 → 会话底部留白。
   * - 留白仍用高水位，避免手动收起时 scrollTop 被钳制；
   * - 自动跟随开启时，卡片 / 输入卡高度变化后重新对齐最后一条消息与卡片顶部；
   * - 跟随解除后：仅输入卡自身高度变化（follow=true）维持既有贴底。
   */
  const handleHeightChange = useCallback(
    (anchorH: number, cardH: number, follow: boolean) => {
      const el = chatRef.current;
      if (!el) return;
      cardHighWaterRef.current = Math.max(cardHighWaterRef.current, cardH);
      const composerH = Math.max(0, anchorH - cardH);
      el.style.paddingBottom = `${composerH + 28 + cardHighWaterRef.current}px`;
      suppressAutoDisableUntilRef.current = performance.now() + 200;

      if (autoFollowRef.current) alignFollowNow();
      else if (follow) keepBottom();
    },
    [alignFollowNow, keepBottom],
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
    suppressAutoDisableUntilRef.current = performance.now() + 200;
  }, [queryTask?.id]);

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
