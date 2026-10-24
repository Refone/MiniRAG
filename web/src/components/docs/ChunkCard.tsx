import { MarkdownContent } from "@/components/markdown/Markdown";
import { ScissorsIcon } from "@/components/icons/AppIcons";
import { stripInlineMarkdown } from "@/utils/markdown";
import type { DocsChunkItem } from "@/types/docs";

interface ChunkCardProps {
  index: number;
  chunk: DocsChunkItem;
  /** 渲染其后 split 标记（非最后一块） */
  showSplit: boolean;
}

/** 切块卡片（原 ImportPage chunks 渲染平移）：badge/标题栈/级别/字数 + markdown 正文 */
export function ChunkCard({ index, chunk, showSplit }: ChunkCardProps) {
  const title = (chunk.title_stack || [])
    .filter(Boolean)
    .map((t) => stripInlineMarkdown(String(t)))
    .join(" › ");
  const level = Number.isFinite(chunk.level) ? chunk.level : 0;

  return (
    <div>
      <div className="chunk-card" data-chunk-index={index}>
        <div className="chunk-card-head">
          <span className="chunk-badge">Chunk {index + 1}</span>
          {title && (
            <span className="chunk-title-stack" title={title}>
              {title}
            </span>
          )}
          <span className="chunk-level">{level > 0 ? "H" + level : "top"}</span>
          <span className="chunk-size-note">
            {chunk.content.length.toLocaleString()} chars
          </span>
        </div>
        <div className="chunk-card-body markdown">
          <MarkdownContent text={chunk.content} allowHtml />
        </div>
      </div>
      {showSplit && (
        <div className="split-marker">
          <ScissorsIcon /> split {index + 1} → {index + 2}
        </div>
      )}
    </div>
  );
}
