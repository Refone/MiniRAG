/**
 * 对话会话 Store (Session-MVVM V0, 设计文档 §4.1)
 *
 * - 消息流 / 发送为会话级状态, 不随 ChatPage 隐藏/卸载销毁;
 * - 查询 SSE (esRef) 生命周期=会话: 切 Tab 不再断流 (PRD 最痛点);
 * - 开关等偏好已迁至 preferenceStore (Phase 2), 本 store 不再持久化;
 *   sessionId 沿用 localStorage kb_session_id (现状机制)。
 * - P1 任务管理升级: 查询进度不再写消息, 改由常驻 queryTask 承载
 *   (输入框上方唯一卡片); 任务仅显示最后一次查询, 完成/失败后保留。
 */
import { create } from "zustand";
import { API_BASE } from "@/lib/api/client";
import { deleteHistory, getHistory, postQuery } from "@/lib/api/chat";
import { usePreferenceStore } from "@/store/preferenceStore";
import { useTokenUsageStore } from "@/store/tokenUsageStore";
import { cachedGet, invalidateCache } from "@/lib/cache/requestCache";
import { openStatusSse } from "@/lib/sse";
import { getBrowserSessionId } from "@/utils/session";
import {
  CACHE_KEY,
  TTL,
  WELCOME_HINT,
  WELCOME_TEXT,
} from "@/lib/constants";
import { formatTime, nowTime } from "@/utils/time";
import { parseAnswerAndImages } from "@/utils/markdown";
import { makeId } from "@/utils/id";
import type { ProgressView } from "@/types/app";
import type { ChatMessage, HistoryItem, QueryTaskView } from "@/types/chat";

function getSessionId(): string {
  return getBrowserSessionId();
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
  /** 常驻查询任务卡片（仅内存；显示最后一次查询，完成/失败后保留） */
  queryTask: QueryTaskView | null;
  /** 历史加载幂等标记 (不持久化) */
  historyLoaded: boolean;

  send: (text: string) => Promise<void>;
  /** 关闭终态任务卡片（运行中不可关闭；真正中止留给 P3） */
  dismissTask: () => void;
  clearHistory: () => Promise<void>;
  ensureHistoryLoaded: () => Promise<void>;
}

/** 查询流 SSE 连接 (唯一持有者; 生命周期=会话, 不随页面隐藏/卸载关闭) */
let esRef: EventSource | null = null;
/**
 * 当前请求的任务 id：旧 SSE 只按它校验（`sending` 是请求级状态）。
 * 与 queryTask 分离：运行中 clearHistory 清卡片后，流仍能正常收尾释放 sending。
 */
let activeTaskId: string | null = null;

export const useChatStore = create<ChatStoreState>()((set, get) => ({
  sessionId: getSessionId(),
  messages: [welcomeMessage()],
  sending: false,
  queryTask: null,
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

    const userMsg: ChatMessage = {
      id: makeId("user"),
      role: "user",
      text,
      time: nowTime(),
      typing: false,
      streaming: false,
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
      error: null,
    };

    /* 任务实例：新查询原地顶替旧卡片并回到收起态；progress 不再写 messages */
    const taskId = makeId("task");
    const task: QueryTaskView = {
      id: taskId,
      progress: { done: [], running: [], status: "pending" },
    };
    activeTaskId = taskId;

    set((s) => ({
      messages: [...s.messages, userMsg, botMsg],
      queryTask: task,
      sending: true,
    }));

    console.log(
      `[chat] 发送问题（网络搜索=${enableWebSearch}，HyDE 搜索=${enableHyde}，${text.length} 字）`,
    );

    const patchBot = (patch: Partial<ChatMessage>) =>
      set((s) => ({ messages: patchMessage(s.messages, botId, patch) }));

    /** 旧 SSE 一律按任务 id 校验：只更新当前任务，不污染新卡片 */
    const patchTask = (progress: ProgressView) =>
      set((s) => {
        if (s.queryTask?.id !== taskId) return s;
        return { queryTask: { ...s.queryTask, progress } };
      });

    /** 终态归一：complete / failed，供卡片显示终态并出现关闭按钮；任务本身保留 */
    const finishTask = (status: "complete" | "failed") =>
      set((s) => {
        if (s.queryTask?.id !== taskId) return s;
        return {
          queryTask: {
            ...s.queryTask,
            progress: { ...s.queryTask.progress, status },
          },
        };
      });

    let finalReceived = false;

    try {
      const data = await postQuery({
        query: text,
        session_id: sessionId,
        enable_web_search: enableWebSearch,
        enable_hyde: enableHyde,
      });

      let rawAnswerText = "";
      const handle = openStatusSse(
        `${API_BASE}/api/query/sse/${data.session_id}`,
        {
          onOpen: () =>
            console.log(`[chat] SSE 已连接（/query/sse/${data.session_id}）`),

          onProgress: (d) => {
            if (activeTaskId !== taskId) return;
            patchTask({
              done: d?.done_list || [],
              running: d?.running_list || [],
              status: d?.status || "processing",
            });
          },

          onDelta: (delta) => {
            if (activeTaskId !== taskId) return;
            rawAnswerText += delta;
            patchBot({ text: rawAnswerText, typing: false });
          },

          onFinal: (d) => {
            if (activeTaskId !== taskId) return;
            finalReceived = true;
            const finalText =
              d && typeof d.answer === "string" && d.answer.trim().length > 0
                ? d.answer
                : rawAnswerText || "";
            console.log(`[chat] 回答完成（${finalText.length} 字）`);
            patchBot({ typing: false, streaming: false, text: finalText });
            set({ sending: false });
          },

          // Token 统计快照帧（后端 flush 后、__close__ 前推送，直接落地）
          onUsage: (d) => {
            if (!d) return;
            useTokenUsageStore
              .getState()
              .applySnapshot(d, "query", data.session_id);
          },

          // 单次模型调用增量帧（调用返回即推送，chip 数字实时累加）
          onUsageDelta: (kind, tokens) => {
            useTokenUsageStore
              .getState()
              .applyDelta(kind, tokens, "query", data.session_id);
          },

          // 不在 final 时关流, 等收到服务端 __close__ 信号再关闭连接
          onServerClose: () => {
            console.log(`[chat] SSE 收到 __close__，关闭连接`);
            // 未收到 usage 帧的增量不会落库，丢弃未落账计数
            useTokenUsageStore
              .getState()
              .clearPending("query", data.session_id);
            if (activeTaskId === taskId) {
              patchBot({ streaming: false });
              finishTask("complete");
              // final 缺失时也释放请求级状态，避免发送按钮永久禁用
              set({ sending: false });
            }
            if (esRef === handle.es) esRef = null;
          },

          onError: (msg) => {
            console.warn(`[chat] SSE 中断：${msg}`);
            useTokenUsageStore
              .getState()
              .clearPending("query", data.session_id);
            if (activeTaskId === taskId) {
              rawAnswerText += `\n\n（错误：${msg}）`;
              patchBot({
                typing: false,
                streaming: false,
                text: rawAnswerText,
              });
              set({ sending: false });
              finishTask(finalReceived ? "complete" : "failed");
            }
            if (esRef === handle.es) esRef = null;
          },
        },
      );
      esRef = handle.es;
    } catch (err) {
      const msg = err instanceof Error ? err.message : String(err);
      console.error("[chat] 发送问题失败", msg);
      if (activeTaskId === taskId) {
        patchBot({
          typing: false,
          streaming: false,
          error: msg,
        });
        set({ sending: false });
        finishTask("failed");
      }
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
    set((s) => ({ messages: [s.messages[0]], queryTask: null }));
  },

  dismissTask: () =>
    set((s) => {
      const progressStatus = s.queryTask?.progress.status;
      if (progressStatus !== "complete" && progressStatus !== "failed") {
        return s;
      }
      console.log("[chat] 关闭终态任务卡片");
      return { queryTask: null };
    }),
}));
