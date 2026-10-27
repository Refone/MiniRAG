/**
 * 文档管理 Store (Session-MVVM V0, 设计文档 §4.2)
 *
 * - 列表/详情/预览模式/导入任务为会话级状态, 不随文档管理页隐藏/卸载销毁;
 * - 上传 SSE (esMap) 生命周期=会话: 切 Tab 不再断流 (PRD 最痛点);
 * - 读接口走 requestCache; 失效点收敛在本 store 动作内 (设计 §5.2):
 *   上传完成 → invalidate("docs:list"); 删除 → invalidate("docs:list")+detail;
 * - previewMode 已迁至 preferenceStore (Phase 2), 本 store 不再持久化。
 */
import { create } from "zustand";
import { API_BASE } from "@/lib/api/client";
import { deleteDoc, getDocsDetail, getDocsList } from "@/lib/api/docs";
import { postUpload } from "@/lib/api/upload";
import { usePreferenceStore } from "@/store/preferenceStore";
import { cachedGet, invalidateCache } from "@/lib/cache/requestCache";
import { openStatusSse } from "@/lib/sse";
import { CACHE_KEY, TOAST_DURATION, TTL } from "@/lib/constants";
import { makeId } from "@/utils/id";
import type { ToastItem, ToastKind } from "@/types/app";
import type {
  DocsDetailResponse,
  DocsListItem,
  ForkChild,
  ImportChildStatus,
  ImportChildTask,
  ImportFile,
} from "@/types/docs";

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

  /* ---- 导入任务 ---- */
  files: ImportFile[];

  /* ---- toast ---- */
  toasts: ToastItem[];

  /* ---- 动作 ---- */
  loadDocs: (opts?: { force?: boolean }) => Promise<void>;
  ensureDocsLoaded: () => void;
  selectDoc: (docId: string) => Promise<void>;
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

/** 后端 child status -> 前端展示态 (interrupted 只在前端派生) */
const CHILD_STATUS_MAP: Record<string, ImportChildStatus> = {
  pending: "pending",
  processing: "processing",
  complete: "completed",
  failed: "error",
};

/** fork 事件 -> 前端子任务初始态 (默认收起由组件控制, 与 store 无关) */
function childFromFork(child: ForkChild): ImportChildTask {
  return {
    id: child.child_id,
    title: child.title,
    path: child.path,
    index: child.index,
    status: "pending",
    startedAt: null,
    stoppedAt: null,
    done: [],
    running: [],
    failed: [],
    error: "",
  };
}

/** 子任务终态判断 (父任务结束时用于冻结仍未完成的兄弟任务) */
function isChildTerminal(status: ImportChildStatus): boolean {
  return status === "completed" || status === "error" || status === "interrupted";
}

export const useDocsStore = create<DocsStoreState>()((set, get) => ({
  docs: [],
  total: 0,
  refreshing: false,
  docsLoaded: false,
  selectedId: null,
  detail: null,
  detailLoading: false,
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
        usePreferenceStore.getState().setPreviewMode("markdown");
        set({
          selectedId: docId,
          detail: null,
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

      resetPreview: () => {
        usePreferenceStore.getState().setPreviewMode("markdown");
        set({
          selectedId: null,
          detail: null,
          detailLoading: false,
        });
      },

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

        const updateChild = (
          fileId: string,
          childId: string,
          updater: (child: ImportChildTask) => ImportChildTask,
        ) =>
          set((s) => ({
            files: s.files.map((f) =>
              f.id === fileId
                ? {
                    ...f,
                    children: f.children.map((c) =>
                      c.id === childId ? updater(c) : c,
                    ),
                  }
                : f,
            ),
          }));

        const hasChild = (fileId: string, childId: string) =>
          get().files.some(
            (f) =>
              f.id === fileId && f.children.some((c) => c.id === childId),
          );

        /**
         * 父任务终态时冻结仍未完成的子任务。
         * - complete 但仍有非终态 child: 协议违例, 只 warn, 不伪造完成;
         * - failed / 断连: 已失败 child 保留 error, 其余置 interrupted。
         */
        const freezeChildren = (
          fileId: string,
          parentTone: "completed" | "error",
        ) => {
          const file = get().files.find((f) => f.id === fileId);
          if (!file) return;

          const stuck = file.children.filter((c) => !isChildTerminal(c.status));
          if (stuck.length === 0) return;

          if (parentTone === "completed") {
            console.warn(
              `[import] 父任务已完成但仍有 ${stuck.length} 个子任务未终态`,
              stuck.map((c) => c.id),
            );
          } else {
            console.warn(
              `[import] 父任务失败/断连，冻结 ${stuck.length} 个子任务`,
              stuck.map((c) => c.id),
            );
          }

          const stamp = Date.now();
          updateFile(fileId, {
            children: file.children.map((c) =>
              isChildTerminal(c.status)
                ? c
                : {
                    ...c,
                    status: "interrupted",
                    running: [],
                    stoppedAt: stamp,
                  },
            ),
          });
        };

        /** 上传受理成功后建立 SSE 连接, 实时接收任务进度 (对齐 chatStore 的推流机制) */
        const startSse = (taskId: string, fileId: string) => {
          let parentTerminal = false;

          const handle = openStatusSse(
            `${API_BASE}/api/upload/sse/${taskId}`,
            {
              onOpen: () =>
                console.log(`[import] SSE 已连接（/upload/sse/${taskId}）`),

              onFork: (d) => {
                if (!d || parentTerminal) return;
                if (!Array.isArray(d.children) || d.children.length === 0) {
                  console.warn(`[import] fork 事件缺少 children（task ${taskId}）`);
                  return;
                }

                set((s) => ({
                  files: s.files.map((f) => {
                    if (f.id !== fileId) return f;
                    const prevById = new Map(
                      f.children.map((c) => [c.id, c]),
                    );
                    const children = d.children.map((child) => {
                      const prev = prevById.get(child.child_id);
                      return prev
                        ? {
                            ...prev,
                            title: child.title,
                            path: child.path,
                            index: child.index,
                          }
                        : childFromFork(child);
                    });
                    return {
                      ...f,
                      forked: true,
                      children,
                      status:
                        f.status === "uploading" ? "processing" : f.status,
                    };
                  }),
                }));

                console.log(
                  `[import] fork：task ${taskId} 收到 ${d.children.length} 个 md 子任务`,
                );
              },

              onProgress: (d) => {
                if (!d || parentTerminal) return;

                const failed = d.failed_list || [];
                const done = d.done_list || [];
                const running = d.running_list || [];

                if (d.status === "complete") {
                  parentTerminal = true;
                  updateFile(fileId, {
                    status: "completed",
                    done,
                    running: [],
                    failed,
                  });
                  freezeChildren(fileId, "completed");
                  console.log(`[import] 任务 ${taskId} 处理完成`);

                  invalidateCache(CACHE_KEY.docsList);
                  // 导入完成 → 列表自动刷新（同一任务只触发一次）
                  if (!refreshedTasks.has(taskId)) {
                    refreshedTasks.add(taskId);
                    get().pushToast(
                      "info",
                      "文档列表已自动刷新（导入完成 → 后台刷新）",
                    );
                    void get().loadDocs();
                  }
                } else if (d.status === "failed") {
                  parentTerminal = true;
                  updateFile(fileId, {
                    status: "error",
                    done,
                    running: [],
                    failed,
                  });
                  freezeChildren(fileId, "error");
                  console.error(`[import] 任务 ${taskId} 处理失败`);
                } else if (
                  d.status === "processing" ||
                  d.status === "pending"
                ) {
                  updateFile(fileId, {
                    status: "processing",
                    done,
                    running,
                    failed,
                  });
                }
              },

              onChildProgress: (d) => {
                if (!d || parentTerminal) return;

                const status = CHILD_STATUS_MAP[d.status];
                if (!status) {
                  console.warn(
                    `[import] 未知子任务状态：${d.status}（child ${d.child_id}）`,
                  );
                  return;
                }
                if (!hasChild(fileId, d.child_id)) {
                  console.warn(
                    `[import] 收到未登记子任务进度，可能丢失 fork 事件：${d.child_id}`,
                  );
                  return;
                }

                const stamp = Date.now();
                updateChild(fileId, d.child_id, (c) => {
                  const done = d.done_list ?? c.done;
                  const running = d.running_list ?? c.running;
                  const failed = d.failed_list ?? c.failed;

                  if (status === "pending") {
                    return {
                      ...c,
                      status,
                      done,
                      running: [],
                      failed,
                      error: d.error ?? c.error,
                    };
                  }

                  if (status === "processing") {
                    return {
                      ...c,
                      status,
                      startedAt: c.startedAt ?? stamp,
                      stoppedAt: null,
                      done,
                      running,
                      failed,
                      error: d.error ?? c.error,
                    };
                  }

                  if (status === "completed") {
                    return {
                      ...c,
                      status,
                      startedAt: c.startedAt ?? stamp,
                      stoppedAt: stamp,
                      done,
                      running: [],
                      failed: [],
                      error: "",
                    };
                  }

                  // error
                  return {
                    ...c,
                    status,
                    startedAt: c.startedAt ?? stamp,
                    stoppedAt: stamp,
                    done,
                    running: [],
                    failed: failed.length > 0 ? failed : c.failed,
                    error: d.error || c.error || "处理失败",
                  };
                });
              },

              // 不在终态事件时关流, 等收到服务端 __close__ 信号再关闭连接
              onServerClose: () => {
                console.log(
                  `[import] SSE 收到 __close__，关闭连接（task ${taskId}）`,
                );
                if (!parentTerminal) {
                  parentTerminal = true;
                  // 服务端未给终态就关流: 按断连处理, 不伪造完成
                  updateFile(fileId, { status: "error", running: [] });
                  freezeChildren(fileId, "error");
                }
                delete esMap[fileId];
              },

              onError: (msg) => {
                // 原生连接错误与服务端 event: error 共用此回调 (后者是带 data 的 MessageEvent)
                console.warn(`[import] SSE 错误/中断：${msg}`);
                if (!parentTerminal) {
                  parentTerminal = true;
                  updateFile(fileId, { status: "error", running: [] });
                  freezeChildren(fileId, "error");
                }
                delete esMap[fileId];
              },

              // 导入流在 error 后还会发 __close__, 等它关流即可
              closeOnServerError: false,
            },
          );
          esMap[fileId] = handle.es;
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
            failed: [],
            running: [],
            forked: false,
            children: [],
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
);
