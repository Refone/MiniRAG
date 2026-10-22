/**
 * 文档管理页（原 ImportPage 升级版，交互与视觉对照 docs/feat/文档管理页面/demo-v4.html）
 *
 * 结构：左卡片（文档列表 ⇄ 导入 横向滑动）+ 右卡片（预览：空态 / 原文 / 切块 / 特征）。
 * 后端契约见 docs/feat/文档管理页面/后端方案.md §4/§5/§6：
 *   - GET    /api/docs?offset&limit    { total, list: [{doc_id,title,type,pdf_link,chunks_link}] }
 *   - GET    /api/docs/{doc_id}        { title, markdown_text, chunks:[{content,level,title_stack}], keywords, abstract }
 *   - DELETE /api/docs/{doc_id}        { success }
 * 上传链路为两步式异步（POST /api/upload → SSE 推流 /api/upload/sse/{task_id}），
 * 任务 complete 后自动刷新文档列表（demo-v4「导入完成 → 列表自动刷新」）。
 *
 * Session-MVVM V0 改造：
 * - 列表/详情/预览模式/导入任务/SSE/toast 全部上移至 docsStore（切 Tab 不断流）；
 * - 页面仅保留纯视觉私有状态：view 左滑、拖拽态、删除弹窗、ChunkRail、refs。
 */

import {
  memo,
  useCallback,
  useEffect,
  useLayoutEffect,
  useMemo,
  useRef,
  useState,
  type ChangeEvent,
  type DragEvent,
} from "react";
import type { DocsListItem } from "@/lib/api";
import type { ImportFile, PreviewMode } from "@/lib/types";
import { useScrollRestore } from "@/lib/scrollRestore";
import { useDocsStore, type ToastItem } from "@/stores/docsStore";
import { MarkdownContent } from "@/components/Markdown";
import { CompleteIcon } from "@/components/CompleteIcon";
import { FailedIcon } from "@/components/FailedIcon";
import { LoadingIcon } from "@/components/LoadingIcon";

/* ------------------------------------------------------------------ */
/* 常量 & 小工具                                                        */
/* ------------------------------------------------------------------ */

const STATUS_LABELS: Record<ImportFile["status"], string> = {
  uploading: "上传中...",
  processing: "处理中...",
  completed: "已完成",
  error: "失败",
};

const STATUS_CLASSES: Record<ImportFile["status"], string> = {
  uploading: "status-uploading",
  processing: "status-processing",
  completed: "status-completed",
  error: "status-error",
};

/**
 * 剥离行内 Markdown 语法，只保留纯文本。
 * 历史数据里 title_stack 直接存了标题原文（含 **加粗**、`代码` 等标记），
 * 切块卡片头按纯文本渲染时会把这些符号原样显示出来，展示前先清洗一遍。
 */
function stripInlineMarkdown(s: string): string {
  return s
    .replace(/!\[([^\]]*)\]\([^)]*\)/g, "$1")
    .replace(/\[([^\]]+)\]\([^)]*\)/g, "$1")
    .replace(/`+([^`]*)`+/g, "$1")
    .replace(/(?<![A-Za-z0-9])(\*\*|__)(?=\S)(.+?)(?<=\S)\1(?![A-Za-z0-9])/g, "$2")
    .replace(/(?<![A-Za-z0-9])(\*|_)(?=\S)(.+?)(?<=\S)\1(?![A-Za-z0-9])/g, "$2")
    .replace(/~~(?=\S)(.+?)(?<=\S)~~/g, "$1")
    .replace(/<[^>]+>/g, "")
    .trim();
}

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

/* ------------------------------------------------------------------ */
/* 导入任务条目（沿用原 ImportPage 的两步式异步展示）                    */
/* ------------------------------------------------------------------ */

type LogLine = { kind: "done" | "running" | "failed"; text: string };

/** 导入任务条目。memo 剪枝: 父级进度更新时仅重渲染受影响的条目 (测试反馈 #3) */
const ImportTaskItem = memo(function ImportTaskItem({ file }: { file: ImportFile }) {
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
});

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

const DocItem = memo(function DocItem({
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
});

/* ------------------------------------------------------------------ */
/* 主组件                                                              */
/* ------------------------------------------------------------------ */

export function ImportPage() {
  /* ---- docsStore 订阅 ---- */
  const docs = useDocsStore((s) => s.docs);
  const total = useDocsStore((s) => s.total);
  const refreshing = useDocsStore((s) => s.refreshing);
  const selectedId = useDocsStore((s) => s.selectedId);
  const detail = useDocsStore((s) => s.detail);
  const detailLoading = useDocsStore((s) => s.detailLoading);
  const previewMode = useDocsStore((s) => s.previewMode);
  const files = useDocsStore((s) => s.files);
  const toasts = useDocsStore((s) => s.toasts);
  const loadDocs = useDocsStore((s) => s.loadDocs);
  const ensureDocsLoaded = useDocsStore((s) => s.ensureDocsLoaded);
  const selectDoc = useDocsStore((s) => s.selectDoc);
  const switchMode = useDocsStore((s) => s.switchMode);
  const uploadFiles = useDocsStore((s) => s.uploadFiles);
  const removeDoc = useDocsStore((s) => s.removeDoc);

  /* ---- 页面私有状态（Activity 保活保留） ---- */
  const [view, setView] = useState<"list" | "import">("list");
  const [dragging, setDragging] = useState(false);
  const [deleting, setDeleting] = useState<DocsListItem | null>(null);
  const [deletingBusy, setDeletingBusy] = useState(false);
  const fileInputRef = useRef<HTMLInputElement>(null);

  /* ---- ChunkRail ---- */
  const previewScrollRef = useRef<HTMLDivElement>(null);
  const [railActive, setRailActive] = useState(-1);
  const railFrameRef = useRef(0);
  const [railTip, setRailTip] = useState<{
    text: string;
    left: number;
    top: number;
  } | null>(null);

  /* ---- 滚动守卫 (测试反馈 #4): 三个独立列表各自保存/恢复 ---- */
  const docListRef = useRef<HTMLDivElement>(null);
  const importBodyRef = useRef<HTMLDivElement>(null);
  useScrollRestore(docListRef);
  useScrollRestore(importBodyRef);
  useScrollRestore(previewScrollRef);

  // Activity 切回后重算 ChunkRail 高亮 (滚动位置恢复后保持一致)
  useLayoutEffect(() => {
    const container = previewScrollRef.current;
    if (!container) return;
    const cards = container.querySelectorAll<HTMLElement>("[data-chunk-index]");
    if (!cards.length) return;
    const containerTop = container.getBoundingClientRect().top;
    let index = 0;
    cards.forEach((el, i) => {
      if (el.getBoundingClientRect().top <= containerTop + 8) index = i;
    });
    setRailActive(index);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  /* ================================================================== */
  /* 初始化与联动                                                        */
  /* ================================================================== */

  // 进入页面自动拉取一次（store 内幂等，重复挂载不重复请求）
  useEffect(() => {
    ensureDocsLoaded();
  }, [ensureDocsLoaded]);

  // 切换文档/预览模式时重置 ChunkRail 高亮。
  // 同 ChatPage 滚动守卫: <Activity> 切回会重建 effects, 用 ref 记录上一次
  // 键值, 仅在真正切换时重置, 切回 Tab 时保留原高亮 (与保留的滚动位置一致)。
  const prevSelKeyRef = useRef<string | null>(null);
  useEffect(() => {
    const key = `${selectedId ?? ""}:${previewMode}`;
    if (prevSelKeyRef.current !== key) {
      prevSelKeyRef.current = key;
      setRailActive(-1);
    }
  }, [selectedId, previewMode]);

  const handleSelectDoc = useCallback(
    (docId: string) => {
      void selectDoc(docId);
    },
    [selectDoc],
  );

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
  /* 导入 / 删除                                                         */
  /* ================================================================== */

  const handleFiles = (fileList: FileList | null) => {
    if (!fileList) return;
    uploadFiles(fileList);
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

  const confirmDelete = async () => {
    if (!deleting || deletingBusy) return;
    setDeletingBusy(true);
    await removeDoc(deleting.doc_id, deleting.title);
    setDeletingBusy(false);
    setDeleting(null);
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
              <div className="import-body" ref={importBodyRef}>
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
                  onClick={() => void loadDocs({ force: true })}
                >
                  刷新
                </button>
              </header>
              <div className="doc-list-scroll" ref={docListRef}>
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
                      onSelect={() => handleSelectDoc(doc.doc_id)}
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
                    .map((t) => stripInlineMarkdown(String(t)))
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
        {toasts.map((t: ToastItem) => (
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
