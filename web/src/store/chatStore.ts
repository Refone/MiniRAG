/**
 * 对话会话 Store (Session-MVVM V0, 设计文档 §4.1)
 *
 * - 消息流 / 发送为会话级状态, 不随 ChatPage 隐藏/卸载销毁;
 * - 查询 SSE (esRef) 生命周期=会话: 切 Tab 不再断流 (PRD 最痛点);
 * - 开关等偏好已迁至 preferenceStore (Phase 2), 本 store 不再持久化;
 *   sessionId 沿用 localStorage kb_session_id (现状机制)。
 */
import { create } from "zustand";
import { API_BASE } from "@/lib/api/client";
import { deleteHistory, getHistory, postQuery } from "@/lib/api/chat";
import { usePreferenceStore } from "@/store/preferenceStore";
import { cachedGet, invalidateCache } from "@/lib/cache/requestCache";
import { openStatusSse } from "@/lib/sse";
import {
  CACHE_KEY,
  SESSION_KEY,
  TTL,
  WELCOME_HINT,
  WELCOME_TEXT,
} from "@/lib/constants";
import { formatTime, nowTime } from "@/utils/time";
import { parseAnswerAndImages } from "@/utils/markdown";
import { makeId } from "@/utils/id";
import type { ChatMessage, HistoryItem } from "@/types/chat";

function getSessionId(): string {
  let id = localStorage.getItem(SESSION_KEY);
  if (!id) {
    id =
      "sess-" + Math.random().toString(36).slice(2) + Date.now().toString(36);
    localStorage.setItem(SESSION_KEY, id);
  }
  return id;
}

function welcomeMessage(): ChatMessage {
  return {
    id: "welcome",
    role: "bot",
    text: WELCOME_TEXT,
    time: "",
    hint: WELCOME_HINT,
    typing: false,
    streaming: false,
    progress: null,
    error: null,
  };
}

/** 历史记录 → 展示态消息 (兼容旧版【图片】区块, 逻辑自 ChatPage 平移) */
function historyToMessages(items: HistoryItem[]): ChatMessage[] {
  return items
    .slice()
    .reverse()
    .map((item, idx) => {
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
        streaming: false,
        progress: null,
        error: null,
      };
    });
}

function patchMessage(
  messages: ChatMessage[],
  id: string,
  patch: Partial<ChatMessage>,
): ChatMessage[] {
  return messages.map((m) => (m.id === id ? { ...m, ...patch } : m));
}

interface ChatStoreState {
  sessionId: string;
  messages: ChatMessage[];
  sending: boolean;
  /** 历史加载幂等标记 (不持久化) */
  historyLoaded: boolean;

  send: (text: string) => Promise<void>;
  clearHistory: () => Promise<void>;
  ensureHistoryLoaded: () => Promise<void>;
}

/** 查询流 SSE 连接 (唯一持有者; 生命周期=会话, 不随页面隐藏/卸载关闭) */
let esRef: EventSource | null = null;

export const useChatStore = create<ChatStoreState>()((set, get) => ({
  sessionId: getSessionId(),
  messages: [welcomeMessage()],
  sending: false,
  historyLoaded: false,

  ensureHistoryLoaded: async () => {
        if (get().historyLoaded) return;
        set({ historyLoaded: true });
        const { sessionId } = get();
        try {
          const items = await cachedGet(
            CACHE_KEY.history(sessionId),
            () => getHistory(sessionId),
            {
              ttlMs: TTL.history,
            },
          );
          if (items.length === 0) return;
          console.log(`[chat] 已加载历史记录 ${items.length} 条`);
          const historyMessages = historyToMessages(items);
          set((s) => ({ messages: [s.messages[0], ...historyMessages] }));
        } catch {
          /* 历史加载失败静默处理 */
        }
      },

      send: async (text) => {
        if (get().sending) return;
        const { sessionId } = get();
        const { enableWebSearch, enableHyde } = usePreferenceStore.getState();
        set({ sending: true });

        const userMsg: ChatMessage = {
          id: makeId("user"),
          role: "user",
          text,
          time: nowTime(),
          typing: false,
          streaming: false,
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
          streaming: true,
          progress: { done: [], running: [], status: "pending" },
          error: null,
        };
        set((s) => ({ messages: [...s.messages, userMsg, botMsg] }));

        console.log(
          `[chat] 发送问题（网络搜索=${enableWebSearch}，HyDE 搜索=${enableHyde}，${text.length} 字）`,
        );

        const patchBot = (patch: Partial<ChatMessage>) =>
          set((s) => ({ messages: patchMessage(s.messages, botId, patch) }));

        try {
          const data = await postQuery({
            query: text,
            session_id: sessionId,
            enable_web_search: enableWebSearch,
            enable_hyde: enableHyde,
          });
          patchBot({ progress: { done: [], running: [], status: "pending" } });

          let rawAnswerText = "";
          const handle = openStatusSse(
            `${API_BASE}/api/query/sse/${data.session_id}`,
            {
              onOpen: () =>
                console.log(`[chat] SSE 已连接（/query/sse/${data.session_id}）`),

              onProgress: (d) => {
                patchBot({
                  progress: {
                    done: d?.done_list || [],
                    running: d?.running_list || [],
                    status: d?.status || "processing",
                  },
                });
                if (d?.status === "completed") {
                  patchBot({ typing: false });
                  set({ sending: false });
                }
              },

              onDelta: (delta) => {
                rawAnswerText += delta;
                patchBot({ text: rawAnswerText, typing: false });
              },

              onFinal: (d) => {
                const finalText =
                  d && typeof d.answer === "string" && d.answer.trim().length > 0
                    ? d.answer
                    : rawAnswerText || "";
                console.log(`[chat] 回答完成（${finalText.length} 字）`);
                patchBot({ typing: false, streaming: false, text: finalText });
                set({ sending: false });
              },

              // 不在 final 时关流, 等收到服务端 __close__ 信号再关闭连接
              onServerClose: () => {
                console.log(`[chat] SSE 收到 __close__，关闭连接`);
                patchBot({ streaming: false });
                if (esRef === handle.es) esRef = null;
              },

              onError: (msg) => {
                console.warn(`[chat] SSE 中断：${msg}`);
                rawAnswerText += `\n\n（错误：${msg}）`;
                patchBot({ typing: false, streaming: false, text: rawAnswerText });
                set({ sending: false });
                if (esRef === handle.es) esRef = null;
              },
            },
          );
          esRef = handle.es;
        } catch (err) {
          const msg = err instanceof Error ? err.message : String(err);
          console.error("[chat] 发送问题失败", msg);
          patchBot({
            typing: false,
            streaming: false,
            progress: null,
            error: msg,
          });
          set({ sending: false });
        }
      },

      clearHistory: async () => {
        const { sessionId } = get();
        console.log(`[chat] 清空会话历史（${sessionId}）`);
        try {
          await deleteHistory(sessionId);
        } catch (e) {
          console.error("[chat] 服务端清空失败", e);
          window.alert("服务端清空失败，仅清空本地显示");
        }
        invalidateCache(CACHE_KEY.history(sessionId));
        set((s) => ({ messages: [s.messages[0]] }));
      },
    }),
);
