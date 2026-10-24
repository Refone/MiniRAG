import type { RefObject } from "react";
import { MarkdownContent } from "@/components/markdown/Markdown";
import { ChunkCard } from "@/components/docs/ChunkCard";
import { ChunkRail } from "@/components/docs/ChunkRail";
import { FeaturePanel } from "@/components/docs/FeaturePanel";
import { EmptyState } from "@/components/ui/EmptyState";
import { FileIcon } from "@/components/icons/AppIcons";
import { SegmentedControl } from "@/components/ui/SegmentedControl";
import { Skeleton } from "@/components/ui/Skeleton";
import { PREVIEW_MODES } from "@/lib/constants";
import type { DocsDetailResponse, PreviewMode } from "@/types/docs";

interface DocPreviewPanelProps {
  title: string;
  hasSelection: boolean;
  detail: DocsDetailResponse | null;
  loading: boolean;
  mode: PreviewMode;
  onModeChange: (m: PreviewMode) => void;
  scrollRef: RefObject<HTMLDivElement | null>;
  /** `${selectedId}:${previewMode}`：内容身份键（滚动守卫与 ChunkRail 复位共用） */
  resetKey: string;
}

/**
 * 右卡片（原 ImportPage 右预览区平移）：
 * 分段开关 + 空态/骨架/原文/切块/特征 渲染 + ChunkRail（chunks 模式）。
 * 预览区滚动守卫由页面 useScrollRestore 持有（resetKey 语义），ChunkRail 自行监听高亮。
 */
export function DocPreviewPanel({
  title,
  hasSelection,
  detail,
  loading,
  mode,
  onModeChange,
  scrollRef,
  resetKey,
}: DocPreviewPanelProps) {
  return (
    <section className="preview-panel elevated">
      <header className="preview-header">
        <span className={`ph-title${hasSelection ? "" : " empty"}`}>{title}</span>
        <SegmentedControl
          options={PREVIEW_MODES}
          value={mode}
          onChange={onModeChange}
          disabled={!hasSelection}
          ariaLabel="预览模式"
        />
      </header>
      <div className="preview-body">
        <div className="preview-scroll" ref={scrollRef}>
          {!hasSelection ? (
            <EmptyState
              className="preview-empty"
              icon={<FileIcon />}
              title="在左侧选择一篇文档"
              subtitle="选中后此处将渲染文档内容，右上角开关切换视图"
            />
          ) : loading || !detail ? (
            <Skeleton />
          ) : mode === "markdown" ? (
            <div className="preview-inner">
              <div className="markdown">
                <MarkdownContent text={detail.markdown_text} allowHtml />
              </div>
            </div>
          ) : mode === "features" ? (
            <FeaturePanel
              keywords={detail.keywords}
              abstract={detail.abstract}
            />
          ) : (
            <div className="preview-inner">
              {detail.chunks.map((chunk, idx) => (
                <ChunkCard
                  key={idx}
                  index={idx}
                  chunk={chunk}
                  showSplit={idx < detail.chunks.length - 1}
                />
              ))}
            </div>
          )}
        </div>
        <ChunkRail
          containerRef={scrollRef}
          chunks={detail?.chunks ?? []}
          resetKey={resetKey}
          hidden={!hasSelection || mode !== "chunks"}
        />
      </div>
    </section>
  );
}
