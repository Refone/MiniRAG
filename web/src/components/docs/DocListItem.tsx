import { memo } from "react";
import type { DocsListItem } from "@/types/docs";

interface DocListItemProps {
  doc: DocsListItem;
  selected: boolean;
  onSelect: () => void;
  onOpenPdf: () => void;
  onOpenChunks: () => void;
  onDelete: () => void;
}

/** 文档列表条目（文档管理页 DocItem 原样平移）；memo 剪枝 (BUG-004) */
export const DocListItem = memo(function DocListItem({
  doc,
  selected,
  onSelect,
  onOpenPdf,
  onOpenChunks,
  onDelete,
}: DocListItemProps) {
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
