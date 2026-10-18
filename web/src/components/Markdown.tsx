import ReactMarkdown from "react-markdown";
import remarkGfm from "remark-gfm";

interface MarkdownContentProps {
  text: string;
}

/**
 * AI 回复的 Markdown 渲染：
 * - 使用 react-markdown + GFM（表格、删除线、任务列表、自动链接）
 * - 默认不渲染原始 HTML（安全，防 XSS）
 * - 链接统一新窗口打开
 * - 图片不在此内联渲染：由消息下方的画廊统一展示，避免重复
 */
export function MarkdownContent({ text }: MarkdownContentProps) {
  return (
    <div className="markdown">
      <ReactMarkdown
        remarkPlugins={[remarkGfm]}
        components={{
          a: ({ node: _node, ...rest }) => (
            <a {...rest} target="_blank" rel="noopener noreferrer" />
          ),
          img: () => null,
        }}
      >
        {text}
      </ReactMarkdown>
    </div>
  );
}
