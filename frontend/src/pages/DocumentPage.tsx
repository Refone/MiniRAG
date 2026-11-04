/**
 * 文档管理页（交互与视觉对照 docs/feat/文档管理页面/demo-v4.html）
 *
 * 结构：左卡片（文档列表 ⇄ 导入 横向滑动）+ 右卡片（预览：空态 / 原文 / 切块 / 特征）。
 * 后端契约见 docs/feat/文档管理页面/后端方案.md §4/§5/§6。
 * 上传链路为两步式异步（POST /api/upload → SSE 推流 /api/upload/sse/{task_id}）。
 *
 * Session-MVVM V0 改造：
 * - 列表/详情/预览模式/导入任务/SSE/toast 全部上移至 store（切 Tab 不断流）；
 * - 页面仅做组合接线 + 页面私有视觉状态：删除弹窗、预览区滚动守卫 ref。
 */
import { useCallback, useMemo, useRef, useState } from "react";
import { DocPreviewPanel } from "@/components/docs/DocPreviewPanel";
import { DocsSidePanel } from "@/components/docs/DocsSidePanel";
import { ConfirmModal } from "@/components/ui/ConfirmModal";
import { Toast } from "@/components/ui/Toast";
import { useScrollRestore } from "@/hooks/useScrollRestore";
import { useDocsStore } from "@/store/docsStore";
import { usePreferenceStore } from "@/store/preferenceStore";
import type { DocsListItem } from "@/types/docs";

export function DocumentPage() {
  /* ---- docsStore 订阅 ---- */
  const docs = useDocsStore((s) => s.docs);
  const total = useDocsStore((s) => s.total);
  const refreshing = useDocsStore((s) => s.refreshing);
  const selectedId = useDocsStore((s) => s.selectedId);
  const detail = useDocsStore((s) => s.detail);
  const detailLoading = useDocsStore((s) => s.detailLoading);
  const files = useDocsStore((s) => s.files);
  const toasts = useDocsStore((s) => s.toasts);
  const loadDocs = useDocsStore((s) => s.loadDocs);
  const selectDoc = useDocsStore((s) => s.selectDoc);
  const uploadFiles = useDocsStore((s) => s.uploadFiles);
  const removeDoc = useDocsStore((s) => s.removeDoc);
  const previewMode = usePreferenceStore((s) => s.previewMode);
  const setPreviewMode = usePreferenceStore((s) => s.setPreviewMode);

  /* ---- 页面私有状态（Activity 保活保留） ---- */
  const [deleting, setDeleting] = useState<DocsListItem | null>(null);
  const [deletingBusy, setDeletingBusy] = useState(false);

  /* ---- 滚动守卫 (测试反馈 #4, 现状语义):
     - 文档列表 / 导入列表由 DocsSidePanel 内部 useScrollRestore 自持;
     - 预览区以"文档:模式"为内容身份键: 切 Tab 键不变 → 恢复原偏移;
       切换文档 / 切换模式键变化 → 偏移归 0 (BUG-003 已处理, 无需看护)。 */
  const previewScrollRef = useRef<HTMLDivElement>(null);
  useScrollRestore(previewScrollRef, {
    resetKey: `${selectedId ?? ""}:${previewMode}`,
  });

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

  const confirmDelete = async () => {
    if (!deleting || deletingBusy) return;
    setDeletingBusy(true);
    await removeDoc(deleting.doc_id, deleting.title);
    setDeletingBusy(false);
    setDeleting(null);
  };

  return (
    <div className="docs-page">
      <DocsSidePanel
        docs={docs}
        total={total}
        refreshing={refreshing}
        selectedId={selectedId}
        files={files}
        onRefresh={() => void loadDocs({ force: true })}
        onSelect={handleSelectDoc}
        onDeleteRequest={setDeleting}
        onUploadFiles={uploadFiles}
      />

      <DocPreviewPanel
        title={detail?.title ?? selectedDoc?.title ?? "未选择文档"}
        hasSelection={!!selectedId}
        detail={detail}
        loading={detailLoading}
        mode={previewMode}
        onModeChange={setPreviewMode}
        scrollRef={previewScrollRef}
        resetKey={`${selectedId ?? ""}:${previewMode}`}
      />

      {/* 删除确认弹窗 */}
      {deleting && (
        <ConfirmModal
          title="删除文档？"
          busy={deletingBusy}
          busyText="删除中..."
          onCancel={() => setDeleting(null)}
          onConfirm={() => void confirmDelete()}
        >
          <span className="modal-doc-title">《{deleting.title}》</span>
          <p>
            删除后该文档的 Milvus 索引（docs / chunks）与 MinIO
            制品（原始文件 / markdown / chunks.json）将被一并移除，
            <b>不可恢复</b>。
          </p>
        </ConfirmModal>
      )}

      {/* toast（左下角） */}
      <Toast toasts={toasts} />
    </div>
  );
}
