/**
 * 文档管理 Store (Session-MVVM V0, 设计文档 §4.2)
 *
 * - 列表/详情/预览模式/导入任务为会话级状态, 不随 ImportPage 隐藏/卸载销毁;
 * - 上传 SSE (esMap) 生命周期=会话: 切 Tab 不再断流 (PRD 最痛点);
 * - 读接口走 requestCache; 失效点收敛在本 store 动作内 (设计 §5.2):
 *   上传完成 → invalidate("docs:list"); 删除 → invalidate("docs:list")+detail;
 * - persist 仅白名单 previewMode (设计 §4.4)。
 */
import { create } from "zustand";
import { persist } from "zustand/middleware";
import { API_BASE } from "@/lib/api/client";
import { deleteDoc, getDocsDetail, getDocsList } from "@/lib/api/docs";
import { postUpload } from "@/lib/api/upload";
import { cachedGet, invalidateCache } from "@/lib/cache/requestCache";
import { CACHE_KEY, TOAST_DURATION, TTL } from "@/lib/constants";
import { makeId } from "@/utils/id";
import type { ToastItem, ToastKind, StatusResponse } from "@/types/app";
import type {
  DocsDetailResponse,
  DocsListItem,
  ImportFile,
  PreviewMode,
} from "@/types/docs";

function parseEventData<T>(data: string): T | null {
  try {
    return JSON.parse(data || "{}") as T;
  } catch {
    return null;
  }
}

interface DocsStoreState {
  /* ---- 文档列表 ---- */
  docs: DocsListItem[];
  total: number;
  refreshing: boolean;
  /** 列表已加载幂等标记 (不持久化) */
  docsLoaded: boolean;

  /* ---- 右区预览 ---- */
  selectedId: string | null;
  detail: DocsDetailResponse | null;
  detailLoading: boolean;
  previewMode: PreviewMode;

  /* ---- 导入任务 ---- */
  files: ImportFile[];

  /* ---- toast ---- */
  toasts: ToastItem[];

  /* ---- 动作 ---- */
  loadDocs: (opts?: { force?: boolean }) => Promise<void>;
  ensureDocsLoaded: () => void;
  selectDoc: (docId: string) => Promise<void>;
  switchMode: (mode: PreviewMode) => void;
  resetPreview: () => void;
  uploadFiles: (fileList: FileList | File[]) => void;
  removeDoc: (docId: string, title: string) => Promise<boolean>;
  pushToast: (kind: ToastKind, text: string) => void;
  dismissToast: (id: number) => void;
}

/** 上传任务 SSE 连接 (fileId → EventSource; 唯一持有者, 生命周期=会话) */
const esMap: Record<string, EventSource> = {};
/** 已完成并触发过列表刷新的 taskId (避免重复刷新, 现状逻辑平移) */
const refreshedTasks = new Set<string>();
let toastIdSeq = 0;

export const useDocsStore = create<DocsStoreState>()(
  persist(
    (set, get) => ({
      docs: [],
      total: 0,
      refreshing: false,
      docsLoaded: false,
      selectedId: null,
      detail: null,
      detailLoading: false,
      previewMode: "markdown",
      files: [],
      toasts: [],

      dismissToast: (id) =>
        set((s) => ({ toasts: s.toasts.filter((t) => t.id !== id) })),

      pushToast: (kind, text) => {
        toastIdSeq += 1;
        const id = toastIdSeq;
        set((s) => ({ toasts: [...s.toasts, { id, kind, text }] }));
        window.setTimeout(() => get().dismissToast(id), TOAST_DURATION);
      },

      loadDocs: async (opts) => {
        const force = opts?.force ?? false;
        set({ refreshing: true });
        try {
          const data = await cachedGet(CACHE_KEY.docsList, () => getDocsList(0, 100), {
            ttlMs: TTL.docsList,
            force,
          });
          set({ docs: data.list, total: data.total, docsLoaded: true });
        } catch (e) {
          console.error("[docs] 拉取文档列表失败", e);
          get().pushToast("error", `文档列表加载失败: ${(e as Error).message}`);
        } finally {
          set({ refreshing: false });
        }
      },

      ensureDocsLoaded: () => {
        if (!get().docsLoaded) void get().loadDocs();
      },

      selectDoc: async (docId) => {
        set({
          selectedId: docId,
          detail: null,
          previewMode: "markdown",
          detailLoading: true,
        });
        try {
          const data = await cachedGet(
            CACHE_KEY.docsDetail(docId),
            () => getDocsDetail(docId),
            { ttlMs: TTL.docsDetail },
          );
          // 竞态保护: 快速连续切换文档时, 旧请求结果不得覆盖新选择
          if (get().selectedId === docId) set({ detail: data });
        } catch (e) {
          console.error("[docs] 拉取文档详情失败", e);
          get().pushToast("error", `文档加载失败: ${(e as Error).message}`);
          if (get().selectedId === docId) set({ selectedId: null });
        } finally {
          if (get().selectedId === docId) set({ detailLoading: false });
        }
      },

      switchMode: (mode) => set({ previewMode: mode }),

      resetPreview: () =>
        set({
          selectedId: null,
          detail: null,
          detailLoading: false,
          previewMode: "markdown",
        }),

      removeDoc: async (docId, title) => {
        try {
          await deleteDoc(docId);
          invalidateCache(CACHE_KEY.docsList);
          invalidateCache(CACHE_KEY.docsDetail(docId));
          set((s) => ({
            docs: s.docs.filter((d) => d.doc_id !== docId),
            total: Math.max(0, s.total - 1),
          }));
          if (get().selectedId === docId) get().resetPreview();
          get().pushToast("success", `已删除《${title}》`);
          return true;
        } catch (e) {
          console.error("[docs] 删除失败", e);
          get().pushToast("error", `删除失败: ${(e as Error).message}`);
          return false;
        }
      },

      uploadFiles: (fileList) => {
        const list = Array.from(fileList ?? []);
        if (list.length === 0) return;

        const updateFile = (id: string, patch: Partial<ImportFile>) =>
          set((s) => ({
            files: s.files.map((f) => (f.id === id ? { ...f, ...patch } : f)),
          }));

        /** 上传受理成功后建立 SSE 连接, 实时接收任务进度 (对齐 chatStore 的推流机制) */
        const startSse = (taskId: string, fileId: string) => {
          const es = new EventSource(`${API_BASE}/api/upload/sse/${taskId}`);
          esMap[fileId] = es;
          let closed = false;
          let terminal = false;

          const close = () => {
            if (closed) return;
            closed = true;
            es.close();
            delete esMap[fileId];
          };

          es.addEventListener("open", () =>
            console.log(`[import] SSE 已连接（/upload/sse/${taskId}）`),
          );

          es.addEventListener("progress", (e) => {
            const d = parseEventData<StatusResponse>((e as MessageEvent).data);
            if (!d) return;
            updateFile(fileId, {
              done: d.done_list || [],
              running: d.running_list || [],
            });
            if (d.status === "complete") {
              console.log(`[import] 任务 ${taskId} 处理完成`);
              terminal = true;
              updateFile(fileId, { status: "completed" });
              invalidateCache(CACHE_KEY.docsList);
              // 导入完成 → 列表自动刷新（同一任务只触发一次）
              if (!refreshedTasks.has(taskId)) {
                refreshedTasks.add(taskId);
                get().pushToast("info", "文档列表已自动刷新（导入完成 → 后台刷新）");
                void get().loadDocs();
              }
            } else if (d.status === "failed") {
              console.error(`[import] 任务 ${taskId} 处理失败`);
              terminal = true;
              updateFile(fileId, { status: "error" });
            } else if (d.status === "processing" || d.status === "pending") {
              updateFile(fileId, { status: "processing" });
            }
          });

          // 不在终态事件时关流, 等收到服务端 __close__ 信号再关闭连接
          es.addEventListener("__close__", () => {
            console.log(`[import] SSE 收到 __close__，关闭连接（task ${taskId}）`);
            close();
          });

          es.addEventListener("error", (e) => {
            // 原生连接错误与服务端 event: error 共用此回调 (后者是带 data 的 MessageEvent)
            let msg = "SSE 连接中断/失败";
            try {
              const raw = (e as MessageEvent).data;
              if (raw) msg = JSON.parse(raw).error || msg;
            } catch {
              /* ignore */
            }
            console.warn(`[import] SSE 中断：${msg}`);
            if (!terminal) updateFile(fileId, { status: "error" });
            close();
          });
        };

        list.forEach(async (file) => {
          const id = makeId("file");
          const newFile: ImportFile = {
            id,
            name: file.name,
            sizeKB: (file.size / 1024).toFixed(2) + " KB",
            status: "uploading",
            startedAt: Date.now(),
            done: [],
            running: [],
          };
          set((s) => ({ files: [newFile, ...s.files] }));
          console.log(`[import] 开始上传：${file.name}（${newFile.sizeKB}）`);

          try {
            const result = await postUpload(file);
            const taskId = result.task_id;
            console.log(
              `[import] 上传成功：${file.name} → 任务 ${taskId}，建立 SSE 推流`,
            );
            updateFile(id, { status: "processing" });
            startSse(taskId, id);
          } catch (error) {
            console.error(`[import] 上传失败：${file.name}`, error);
            updateFile(id, { status: "error" });
          }
        });
      },
    }),
    {
      name: "kb-docs-store",
      version: 1,
      partialize: (s) => ({ previewMode: s.previewMode }),
    },
  ),
);
