import { useRef, useState } from "react";
import { DocListItem } from "@/components/docs/DocListItem";
import { ImportTaskItem } from "@/components/docs/ImportTaskItem";
import { UploadDropzone } from "@/components/docs/UploadDropzone";
import { EmptyState } from "@/components/ui/EmptyState";
import { InboxIcon } from "@/components/icons/AppIcons";
import { useScrollRestore } from "@/hooks/useScrollRestore";
import type { DocsListItem, ImportFile } from "@/types/docs";

interface DocsSidePanelProps {
  docs: DocsListItem[];
  total: number;
  refreshing: boolean;
  selectedId: string | null;
  files: ImportFile[];
  onRefresh: () => void;
  onSelect: (docId: string) => void;
  onDeleteRequest: (doc: DocsListItem) => void;
  onUploadFiles: (list: FileList | File[]) => void;
}

/**
 * 左卡片（原 ImportPage 左面板平移）：文档列表 ⇄ 导入 横向滑动。
 * - view 状态内部自持（Activity 保活保留）
 * - 文档列表 / 导入列表滚动守卫由内部 useScrollRestore 自持（现状语义）
 */
export function DocsSidePanel({
  docs,
  total,
  refreshing,
  selectedId,
  files,
  onRefresh,
  onSelect,
  onDeleteRequest,
  onUploadFiles,
}: DocsSidePanelProps) {
  const [view, setView] = useState<"list" | "import">("list");
  const docListRef = useRef<HTMLDivElement>(null);
  const importBodyRef = useRef<HTMLDivElement>(null);
  useScrollRestore(docListRef);
  useScrollRestore(importBodyRef);

  return (
    <aside className="left-panel elevated">
      <div className={`left-stage${view === "import" ? " show-import" : ""}`}>
        <div className="stage-track">
          {/* 导入视图 */}
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
              <UploadDropzone onFiles={(list) => onUploadFiles(list)} />
              <div className="file-list">
                {files.map((f) => (
                  <ImportTaskItem key={f.id} file={f} />
                ))}
              </div>
            </div>
          </section>

          {/* 文档列表视图 */}
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
                onClick={onRefresh}
              >
                刷新
              </button>
            </header>
            <div className="doc-list-scroll" ref={docListRef}>
              {docs.length === 0 ? (
                <EmptyState
                  className="doc-list-empty"
                  icon={<InboxIcon />}
                  title="文库为空"
                  subtitle="点击左上角「添加文档」导入第一篇文档"
                />
              ) : (
                docs.map((doc) => (
                  <DocListItem
                    key={doc.doc_id}
                    doc={doc}
                    selected={doc.doc_id === selectedId}
                    onSelect={() => onSelect(doc.doc_id)}
                    onOpenPdf={() =>
                      doc.pdf_link && window.open(doc.pdf_link, "_blank")
                    }
                    onOpenChunks={() =>
                      window.open(doc.chunks_link, "_blank")
                    }
                    onDelete={() => onDeleteRequest(doc)}
                  />
                ))
              )}
            </div>
          </section>
        </div>
      </div>
    </aside>
  );
}
