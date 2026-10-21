/**
 * 文档管理页（原 ImportPage 升级版，交互与视觉对照 docs/feat/文档管理页面/demo-v4.html）
 *
 * 结构：左卡片（文档列表 ⇄ 导入 横向滑动）+ 右卡片（预览：空态 / 原文 / 切块 / 特征）。
 * 后端契约见 docs/feat/文档管理页面/后端方案.md §4/§5/§6：
 *   - GET    /api/docs?offset&limit    { total, list: [{doc_id,title,type,pdf_link,chunks_link}] }
 *   - GET    /api/docs/{doc_id}        { title, markdown_text, chunks:[{content,level,title_stack}], keywords, abstract }
 *   - DELETE /api/docs/{doc_id}        { success }
 * 上传链路为两步式异步（POST /api/upload → SSE 推流 /api/upload/sse/{task_id}，
 * 机制与 ChatPage 的 /api/query/sse/{session_id} 一致），
 * 任务 complete 后自动刷新文档列表（demo-v4「导入完成 → 列表自动刷新」）。
 */

import {
  useCallback,
  useEffect,
  useMemo,
  useRef,
  useState,
  type ChangeEvent,
  type DragEvent,
} from "react";
import {
  API_BASE,
  deleteDoc,
  getDocsDetail,
  getDocsList,
  type DocsDetailResponse,
  type DocsListItem,
  type ImportUploadResponse,
} from "@/lib/api";
import type { ImportFile, ImportStatus, StatusResponse } from "@/lib/types";
import { MarkdownContent } from "@/components/Markdown";
import { CompleteIcon } from "@/components/CompleteIcon";
import { FailedIcon } from "@/components/FailedIcon";
import { LoadingIcon } from "@/components/LoadingIcon";

/* ------------------------------------------------------------------ */
/* 常量 & 小工具                                                        */
/* ------------------------------------------------------------------ */

const STATUS_LABELS: Record<ImportStatus, string> = {
  uploading: "上传中...",
  processing: "处理中...",
  completed: "已完成",
  error: "失败",
};

const STATUS_CLASSES: Record<ImportStatus, string> = {
  uploading: "status-uploading",
  processing: "status-processing",
  completed: "status-completed",
  error: "status-error",
};

function makeId(): string {
  return "file-" + Math.random().toString(36).slice(2, 11);
}

function parseEventData<T>(data: string): T | null {
  try {
    return JSON.parse(data || "{}") as T;
  } catch {
    return null;
  }
}

type PreviewMode = "markdown" | "chunks" | "features";

const MODE_ORDER: Record<PreviewMode, number> = {
  markdown: 0,
  chunks: 1,
  features: 2,
};

const MODE_LABELS: Record<PreviewMode, string> = {
  markdown: "原文",
  chunks: "切块",
  features: "特征",
};

type ToastKind = "info" | "success" | "error";

interface ToastItem {
  id: number;
  kind: ToastKind;
  text: string;
}

/* ------------------------------------------------------------------ */
/* 导入任务条目（沿用原 ImportPage 的两步式异步展示）                    */
/* ------------------------------------------------------------------ */

type LogLine = { kind: "done" | "running" | "failed"; text: string };

function ImportTaskItem({ file }: { file: ImportFile }) {
  const failed = file.status === "error";
  const failedNode =
    failed && file.done.length > 0 ? file.done[file.done.length - 1] : null;
  const doneNodes = failedNode ? file.done.slice(0, -1) : file.done;
  const lines: LogLine[] = [
    ...doneNodes.map((n) => ({ kind: "done" as const, text: n })),
    ...(failedNode ? [{ kind: "failed" as const, text: failedNode }] : []),
    ...file.running.map((n) => ({ kind: "running" as const, text: n })),
  ];

  const [now, setNow] = useState(() => Date.now());
  const active = file.status === "uploading" || file.status === "processing";
  useEffect(() => {
    if (!active) return;
    const timer = window.setInterval(() => setNow(Date.now()), 500);
    return () => window.clearInterval(timer);
  }, [active]);
  const elapsedText = `${((now - file.startedAt) / 1000).toFixed(1)}s`;

  const isOpen = file.status !== "completed";

  return (
    <div className="file-item">
      <div className="file-info">
        <span className="file-name">{file.name}</span>
        <span className="file-size">{file.sizeKB}</span>
        <details className="log-details" open={isOpen}>
          <summary>{`已耗时 ${elapsedText}，点击收起 / 展开`}</summary>
          <ul className="log-list">
            {lines.length === 0 ? (
              <li className="status-line">暂无进度</li>
            ) : (
              lines.map((line) => (
                <li key={line.text} className="status-line">
                  <span
                    className={`status-line__icon status-line__icon--${line.kind}`}
                  >
                    {line.kind === "done" ? (
                      <CompleteIcon />
                    ) : line.kind === "failed" ? (
                      <FailedIcon />
                    ) : (
                      <LoadingIcon />
                    )}
                  </span>
                  <span className="status-line__text">{line.text}</span>
                </li>
              ))
            )}
          </ul>
        </details>
      </div>
      <div className={`status-badge ${STATUS_CLASSES[file.status]}`}>
        {STATUS_LABELS[file.status]}
      </div>
    </div>
  );
}

/* ------------------------------------------------------------------ */
/* 文档列表条目                                                        */
/* ------------------------------------------------------------------ */

interface DocItemProps {
  doc: DocsListItem;
  selected: boolean;
  onSelect: () => void;
  onOpenPdf: () => void;
  onOpenChunks: () => void;
  onDelete: () => void;
}

function DocItem({
  doc,
  selected,
  onSelect,
  onOpenPdf,
  onOpenChunks,
  onDelete,
}: DocItemProps) {
  return (
    <div
      className={`doc-item${selected ? " selected" : ""}`}
      onClick={onSelect}
      role="button"
      tabIndex={0}
      onKeyDown={(e) => {
        if (e.key === "Enter") onSelect();
      }}
    >
      <div className="doc-title">{doc.title}</div>
      <div className="doc-meta-row">
        <span className="doc-type">{doc.type}</span>
        <span className="doc-actions">
          {doc.type === "pdf" && doc.pdf_link && (
            <button
              className="mini-btn pdf"
              type="button"
              onClick={(e) => {
                e.stopPropagation();
                onOpenPdf();
              }}
            >
              PDF
            </button>
          )}
          <button
            className="mini-btn"
            type="button"
            onClick={(e) => {
              e.stopPropagation();
              onOpenChunks();
            }}
          >
            切块文件
          </button>
          <button
            className="mini-btn danger"
            type="button"
            onClick={(e) => {
              e.stopPropagation();
              onDelete();
            }}
          >
            删除
          </button>
        </span>
      </div>
    </div>
  );
}

/* ------------------------------------------------------------------ */
/* 主组件                                                              */
/* ------------------------------------------------------------------ */

export function ImportPage() {
  /* ---- 左区视图 ---- */
  const [view, setView] = useState<"list" | "import">("list");

  /* ---- 文档列表 ---- */
  const [docs, setDocs] = useState<DocsListItem[]>([]);
  const [total, setTotal] = useState(0);
  const [refreshing, setRefreshing] = useState(false);

  /* ---- 右区预览 ---- */
  const [selectedId, setSelectedId] = useState<string | null>(null);
  const [detail, setDetail] = useState<DocsDetailResponse | null>(null);
  const [detailLoading, setDetailLoading] = useState(false);
  const [previewMode, setPreviewMode] = useState<PreviewMode>("markdown");

  /* ---- 删除 ---- */
  const [deleting, setDeleting] = useState<DocsListItem | null>(null);
  const [deletingBusy, setDeletingBusy] = useState(false);

  /* ---- toast ---- */
  const [toasts, setToasts] = useState<ToastItem[]>([]);
  const toastIdRef = useRef(0);
  const pushToast = useCallback((kind: ToastKind, text: string) => {
    toastIdRef.current += 1;
    const id = toastIdRef.current;
    setToasts((prev) => [...prev, { id, kind, text }]);
    window.setTimeout(() => {
      setToasts((prev) => prev.filter((t) => t.id !== id));
    }, 3200);
  }, []);

  /* ---- 导入 ---- */
  const [files, setFiles] = useState<ImportFile[]>([]);
  const [dragging, setDragging] = useState(false);
  const fileInputRef = useRef<HTMLInputElement>(null);
  /** 每个进行中任务的 SSE 连接（fileId → EventSource） */
  const esRef = useRef<Record<string, EventSource>>({});
  /** 已完成并触发过列表刷新的任务, 避免重复刷新 */
  const refreshedTasksRef = useRef<Set<string>>(new Set());

  /* ---- ChunkRail ---- */
  const previewScrollRef = useRef<HTMLDivElement>(null);
  const [railActive, setRailActive] = useState(-1);
  const railFrameRef = useRef(0);
  const [railTip, setRailTip] = useState<{
    text: string;
    left: number;
    top: number;
  } | null>(null);

  /* ================================================================== */
  /* 文档列表                                                             */
  /* ================================================================== */

  const loadDocs = useCallback(async () => {
    setRefreshing(true);
    try {
      const data = await getDocsList(0, 100);
      setDocs(data.list);
      setTotal(data.total);
    } catch (e) {
      console.error("[docs] 拉取文档列表失败", e);
      pushToast("error", `文档列表加载失败: ${(e as Error).message}`);
    } finally {
      setRefreshing(false);
    }
  }, [pushToast]);

  // 进入页面自动拉取一次
  useEffect(() => {
    loadDocs();
  }, [loadDocs]);

  /* ================================================================== */
  /* 右区预览                                                             */
  /* ================================================================== */

  const resetPreview = useCallback(() => {
    setSelectedId(null);
    setDetail(null);
    setDetailLoading(false);
    setPreviewMode("markdown");
    setRailActive(-1);
  }, []);

  const selectDoc = useCallback(
    (docId: string) => {
      setSelectedId(docId);
      setDetail(null);
      setPreviewMode("markdown");
      setRailActive(-1);
      setDetailLoading(true);
      getDocsDetail(docId)
        .then((data) => setDetail(data))
        .catch((e) => {
          console.error("[docs] 拉取文档详情失败", e);
          pushToast("error", `文档加载失败: ${(e as Error).message}`);
          setSelectedId(null);
        })
        .finally(() => setDetailLoading(false));
    },
    [pushToast],
  );

  const switchMode = useCallback((mode: PreviewMode) => {
    setPreviewMode(mode);
    setRailActive(-1);
  }, []);

  const selectedDoc = useMemo(
    () => docs.find((d) => d.doc_id === selectedId) ?? null,
    [docs, selectedId],
  );

  /* ---- ChunkRail 尺寸与滚动联动 ---- */

  const railSizes = useMemo(
    () => (detail?.chunks ?? []).map((c) => c.content.length),
    [detail],
  );
  const railMax = useMemo(
    () => railSizes.reduce((m, n) => Math.max(m, n), 0) || 1,
    [railSizes],
  );

  const onPreviewScroll = useCallback(() => {
    setRailTip(null);
    if (!railSizes.length || railFrameRef.current) return;
    railFrameRef.current = window.requestAnimationFrame(() => {
      railFrameRef.current = 0;
      const container = previewScrollRef.current;
      if (!container) return;
      const cards = container.querySelectorAll<HTMLElement>(
        "[data-chunk-index]",
      );
      if (!cards.length) return;
      const containerTop = container.getBoundingClientRect().top;
      let index = 0;
      cards.forEach((el, i) => {
        if (el.getBoundingClientRect().top <= containerTop + 8) index = i;
      });
      setRailActive(index);
    });
  }, [railSizes]);

  const scrollToChunk = useCallback((index: number) => {
    const container = previewScrollRef.current;
    if (!container) return;
    const el = container.querySelector<HTMLElement>(
      `[data-chunk-index="${index}"]`,
    );
    if (!el) return;
    const top =
      el.getBoundingClientRect().top -
      container.getBoundingClientRect().top +
      container.scrollTop -
      12;
    container.scrollTo({ top: Math.max(0, top), behavior: "smooth" });
    setRailActive(index);
  }, []);

  const showRailTip = useCallback(
    (index: number, e: React.MouseEvent<HTMLButtonElement>) => {
      const n = railSizes[index] ?? 0;
      const r = (e.target as HTMLElement).getBoundingClientRect();
      setRailTip({
        text: `Chunk ${index + 1} · ${n.toLocaleString("zh-CN")} chars`,
        left: r.left,
        top: r.top + r.height / 2,
      });
    },
    [railSizes],
  );

  /* ================================================================== */
  /* 导入（两步式异步 + SSE 推流）                                        */
  /* ================================================================== */

  const updateFile = (id: string, patch: Partial<ImportFile>) => {
    setFiles((prev) => prev.map((f) => (f.id === id ? { ...f, ...patch } : f)));
  };

  // 卸载时关闭所有 SSE 连接
  useEffect(() => {
    const sources = esRef.current;
    return () => {
      Object.values(sources).forEach((es) => es.close());
    };
  }, []);

  /** 上传受理成功后建立 SSE 连接, 实时接收任务进度 (对齐 ChatPage 的推流机制) */
  const startSseStream = (taskId: string, fileId: string) => {
    const es = new EventSource(`${API_BASE}/api/upload/sse/${taskId}`);
    esRef.current[fileId] = es;
    let closed = false;
    let terminal = false;

    const close = () => {
      if (closed) return;
      closed = true;
      es.close();
      delete esRef.current[fileId];
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
        // demo-v4: 导入完成 → 列表自动刷新（同一任务只触发一次）
        if (!refreshedTasksRef.current.has(taskId)) {
          refreshedTasksRef.current.add(taskId);
          pushToast("info", "文档列表已自动刷新（导入完成 → 后台刷新）");
          loadDocs();
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

  const uploadFile = async (file: File) => {
    const id = makeId();
    const newFile: ImportFile = {
      id,
      name: file.name,
      sizeKB: (file.size / 1024).toFixed(2) + " KB",
      status: "uploading",
      startedAt: Date.now(),
      done: [],
      running: [],
    };
    setFiles((prev) => [newFile, ...prev]);
    console.log(`[import] 开始上传：${file.name}（${newFile.sizeKB}）`);

    const formData = new FormData();
    formData.append("file", file);

    try {
      const response = await fetch(`${API_BASE}/api/upload`, {
        method: "POST",
        body: formData,
      });
      if (!response.ok) throw new Error("Upload failed");
      const result: ImportUploadResponse = await response.json();
      const taskId = result.task_id;
      console.log(`[import] 上传成功：${file.name} → 任务 ${taskId}，建立 SSE 推流`);
      updateFile(id, { status: "processing" });
      startSseStream(taskId, id);
    } catch (error) {
      console.error(`[import] 上传失败：${file.name}`, error);
      updateFile(id, { status: "error" });
    }
  };

  const handleFiles = (fileList: FileList | null) => {
    if (!fileList) return;
    Array.from(fileList).forEach(uploadFile);
  };

  const onDrop = (e: DragEvent<HTMLDivElement>) => {
    e.preventDefault();
    setDragging(false);
    handleFiles(e.dataTransfer.files);
  };

  const onInputChange = (e: ChangeEvent<HTMLInputElement>) => {
    handleFiles(e.target.files);
    e.target.value = "";
  };

  /* ================================================================== */
  /* 删除                                                                 */
  /* ================================================================== */

  const confirmDelete = async () => {
    if (!deleting || deletingBusy) return;
    setDeletingBusy(true);
    try {
      await deleteDoc(deleting.doc_id);
      pushToast("success", `已删除《${deleting.title}》`);
      setDocs((prev) => prev.filter((d) => d.doc_id !== deleting.doc_id));
      setTotal((t) => Math.max(0, t - 1));
      if (selectedId === deleting.doc_id) resetPreview();
    } catch (e) {
      console.error("[docs] 删除失败", e);
      pushToast("error", `删除失败: ${(e as Error).message}`);
    } finally {
      setDeletingBusy(false);
      setDeleting(null);
    }
  };

  /* ================================================================== */
  /* 渲染                                                                 */
  /* ================================================================== */

  const segIndex = selectedId ? MODE_ORDER[previewMode] : 0;

  return (
    <div className="docs-page">
      {/* 左卡片：列表 ⇄ 导入 横向滑动 */}
      <aside className="left-panel elevated">
        <div
          className={`left-stage${view === "import" ? " show-import" : ""}`}
        >
          <div className="stage-track">
            {/* 文档列表视图 */}
            <section className="view view-import">
              <header className="panel-header">
                <button
                  className="pill"
                  type="button"
                  onClick={() => setView("list")}
                >
                  文档列表
                </button>
                <div className="head-title">
                  <h2>添加文档</h2>
                  <span className="head-sub">
                    支持 PDF / Markdown / Markdown ZIP
                  </span>
                </div>
              </header>
              <div className="import-body">
                <div
                  className={`upload-area${dragging ? " dragging" : ""}`}
                  onClick={() => fileInputRef.current?.click()}
                  onDragOver={(e) => {
                    e.preventDefault();
                    setDragging(true);
                  }}
                  onDragLeave={() => setDragging(false)}
                  onDrop={onDrop}
                >
                  <div className="upload-icon">☁️</div>
                  <p>点击或拖拽文件到此处 (PDF / MD / ZIP)</p>
                  <p className="sub">
                    ZIP 为 markdown 合集，包内每个 md 将成为一篇独立文档
                  </p>
                  <input
                    ref={fileInputRef}
                    type="file"
                    className="file-input"
                    multiple
                    accept=".pdf,.md,.markdown,.zip"
                    onChange={onInputChange}
                  />
                </div>
                <div className="file-list">
                  {files.map((f) => (
                    <ImportTaskItem key={f.id} file={f} />
                  ))}
                </div>
              </div>
            </section>

            {/* 导入视图 */}
            <section className="view view-list">
              <header className="panel-header">
                <button
                  className="pill primary"
                  type="button"
                  onClick={() => setView("import")}
                >
                  添加文档
                </button>
                <div className="head-title">
                  <h2>文档列表</h2>
                  <span className="head-sub">
                    <span className={refreshing ? "shimmer" : ""}>
                      {refreshing ? "正在刷新..." : `当前文档总数: ${total}`}
                    </span>
                  </span>
                </div>
                <button
                  className="pill"
                  type="button"
                  disabled={refreshing}
                  onClick={loadDocs}
                >
                  刷新
                </button>
              </header>
              <div className="doc-list-scroll">
                {docs.length === 0 ? (
                  <div className="doc-list-empty">
                    📭 文库为空
                    <br />
                    点击左上角「添加文档」导入第一篇文档
                  </div>
                ) : (
                  docs.map((doc) => (
                    <DocItem
                      key={doc.doc_id}
                      doc={doc}
                      selected={doc.doc_id === selectedId}
                      onSelect={() => selectDoc(doc.doc_id)}
                      onOpenPdf={() => doc.pdf_link && window.open(doc.pdf_link, "_blank")}
                      onOpenChunks={() =>
                        window.open(doc.chunks_link, "_blank")
                      }
                      onDelete={() => setDeleting(doc)}
                    />
                  ))
                )}
              </div>
            </section>
          </div>
        </div>
      </aside>

      {/* 右卡片：预览 */}
      <section className="preview-panel elevated">
        <header className="preview-header">
          <span className={`ph-title${selectedId ? "" : " empty"}`}>
            {detail?.title ?? selectedDoc?.title ?? "未选择文档"}
          </span>
          <div
            className={`segmented${selectedId ? "" : " disabled"}`}
            role="group"
            aria-label="预览模式"
          >
            <div
              className="seg-thumb"
              style={{ transform: `translateX(${segIndex * 100}%)` }}
            />
            {(Object.keys(MODE_ORDER) as PreviewMode[]).map((mode) => (
              <button
                key={mode}
                className={`seg-btn${previewMode === mode ? " active" : ""}`}
                type="button"
                disabled={!selectedId}
                onClick={() => switchMode(mode)}
              >
                {MODE_LABELS[mode]}
              </button>
            ))}
          </div>
        </header>
        <div className="preview-body">
          <div
            className="preview-scroll"
            ref={previewScrollRef}
            onScroll={onPreviewScroll}
          >
            {!selectedId ? (
              <div className="preview-empty">
                <div className="preview-empty-icon">📄</div>
                <p className="preview-empty-title">在左侧选择一篇文档</p>
                <p className="preview-empty-sub">
                  选中后此处将渲染文档内容，右上角开关切换视图
                </p>
              </div>
            ) : detailLoading || !detail ? (
              <div className="preview-inner">
                <div className="skeleton sk-line w60" />
                <div className="skeleton sk-line" />
                <div className="skeleton sk-line" />
                <div className="skeleton sk-line w80" />
                <div className="skeleton sk-line w40" />
              </div>
            ) : previewMode === "markdown" ? (
              <div className="preview-inner">
                <div className="markdown">
                  <MarkdownContent text={detail.markdown_text} allowHtml />
                </div>
              </div>
            ) : previewMode === "features" ? (
              <div className="preview-inner">
                <div className="feature-card">
                  <h3 className="feature-title">关键词</h3>
                  <div className="feature-chips">
                    {detail.keywords
                      .split(/[,，]/)
                      .map((k) => k.trim())
                      .filter(Boolean)
                      .map((k, i) => (
                        <span className="kw-chip" key={`${k}-${i}`}>
                          {k}
                        </span>
                      ))}
                    {detail.keywords.split(/[,，]/).filter((k) => k.trim())
                      .length === 0 && (
                      <span className="doc-type">—</span>
                    )}
                  </div>
                </div>
                <div className="feature-card">
                  <h3 className="feature-title">摘要</h3>
                  <p className="feature-abstract">
                    {detail.abstract || "（无摘要）"}
                  </p>
                </div>
              </div>
            ) : (
              /* chunks 模式 */
              <div className="preview-inner">
                {detail.chunks.map((chunk, idx) => {
                  const title = (chunk.title_stack || [])
                    .filter(Boolean)
                    .join(" › ");
                  const level = Number.isFinite(chunk.level) ? chunk.level : 0;
                  return (
                    <div key={idx}>
                      <div className="chunk-card" data-chunk-index={idx}>
                        <div className="chunk-card-head">
                          <span className="chunk-badge">Chunk {idx + 1}</span>
                          {title && (
                            <span className="chunk-title-stack" title={title}>
                              {title}
                            </span>
                          )}
                          <span className="chunk-level">
                            {level > 0 ? "H" + level : "top"}
                          </span>
                          <span className="chunk-size-note">
                            {chunk.content.length.toLocaleString()} chars
                          </span>
                        </div>
                        <div className="chunk-card-body markdown">
                          <MarkdownContent text={chunk.content} allowHtml />
                        </div>
                      </div>
                      {idx < detail.chunks.length - 1 && (
                        <div className="split-marker">
                          <span className="scissors">✂</span> split {idx + 1} →{" "}
                          {idx + 2}
                        </div>
                      )}
                    </div>
                  );
                })}
              </div>
            )}
          </div>
          <aside
            className="chunk-rail"
            aria-label="Chunk 长度分布"
            hidden={!selectedId || previewMode !== "chunks"}
          >
            <div className="rail-caption">total: {railSizes.length}</div>
            {railSizes.map((n, i) => {
              const pct = Math.max(5, (n / railMax) * 100);
              return (
                <div className="rail-row" key={i}>
                  <button
                    className={`rail-bar${railActive === i ? " active" : ""}`}
                    type="button"
                    data-index={i}
                    aria-label={`Chunk ${i + 1}, ${n} chars`}
                    style={{ width: `${pct.toFixed(2)}%` }}
                    onClick={() => scrollToChunk(i)}
                    onMouseEnter={(e) => showRailTip(i, e)}
                    onMouseLeave={() => setRailTip(null)}
                  />
                  <span className="rail-num">{i + 1}</span>
                </div>
              );
            })}
          </aside>
        </div>
      </section>

      {/* 删除确认弹窗 */}
      {deleting && (
        <div className="modal-mask">
          <div className="modal">
            <h3>删除文档？</h3>
            <span className="modal-doc-title">《{deleting.title}》</span>
            <p>
              删除后该文档的 Milvus 索引（docs / chunks）与 MinIO
              制品（原始文件 / markdown / chunks.json）将被一并移除，
              <b>不可恢复</b>。
            </p>
            <div className="modal-actions">
              <button
                className="btn"
                type="button"
                disabled={deletingBusy}
                onClick={() => setDeleting(null)}
              >
                取消
              </button>
              <button
                className="btn primary"
                type="button"
                disabled={deletingBusy}
                onClick={confirmDelete}
              >
                {deletingBusy ? "删除中..." : "确认删除"}
              </button>
            </div>
          </div>
        </div>
      )}

      {/* toast（左下角） */}
      <div className="toast-wrap">
        {toasts.map((t) => (
          <div
            key={t.id}
            className={`toast${
              t.kind === "success"
                ? " success"
                : t.kind === "error"
                  ? " error"
                  : ""
            }`}
          >
            <span className="toast-dot" />
            <span>{t.text}</span>
          </div>
        ))}
      </div>

      {/* ChunkRail 悬停提示 */}
      {railTip && (
        <div
          className="rail-tip"
          role="tooltip"
          style={{ left: railTip.left, top: railTip.top }}
        >
          {railTip.text}
        </div>
      )}
    </div>
  );
}
