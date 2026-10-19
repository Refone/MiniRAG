import { useMemo } from "react";
import ReactMarkdown from "react-markdown";
import remarkGfm from "remark-gfm";
import { normalizeMarkdownDestinations } from "@/lib/chatUtils";

interface MarkdownContentProps {
  text: string;
}

/**
 * AI 回复的 Markdown 渲染：
 * - 使用 react-markdown + GFM（表格、删除线、任务列表、自动链接）
 * - 默认不渲染原始 HTML（安全，防 XSS）
 * - 链接统一新窗口打开
 * - 图片由 LLM 内嵌在正文中，直接内联渲染；URL 中的空格/括号先做百分号转义，
 *   避免 CommonMark 解析截断链接目标
 */
export function MarkdownContent({ text }: MarkdownContentProps) {
  const normalized = useMemo(() => normalizeMarkdownDestinations(text), [text]);

  return (
    <div className="markdown">
      <ReactMarkdown
        remarkPlugins={[remarkGfm]}
        components={{
          a: ({ node: _node, ...rest }) => (
            <a {...rest} target="_blank" rel="noopener noreferrer" />
          ),
          img: ({ node: _node, ...rest }) => (
            <img
              {...rest}
              loading="lazy"
              referrerPolicy="no-referrer"
              className="markdown-img"
            />
          ),
        }}
      >
        {normalized}
      </ReactMarkdown>
    </div>
  );
}
