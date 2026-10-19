import { useMemo } from "react";
import ReactMarkdown, { type Components } from "react-markdown";
import remarkGfm from "remark-gfm";
import type { Element } from "hast";
import { normalizeMarkdownDestinations } from "@/lib/chatUtils";

interface MarkdownContentProps {
  text: string;
}

/**
 * 判断一个 <p> 是否只包含图片（忽略空白文本节点）：
 * - 恰好 1 张图 → "img-single"（居中）
 * - 2 张及以上 → "img-row"（同行并列，放不下自动换行）
 * - 混有文字/其他元素或没有图片 → null（保持默认排版）
 */
function classifyImageParagraph(node: Element | undefined): string | null {
  if (!node) return null;
  const children = node.children ?? [];
  const imgs = children.filter(
    (c) => c.type === "element" && c.tagName === "img",
  );
  if (imgs.length === 0) return null;

  const hasOtherContent = children.some(
    (c) =>
      (c.type === "text" && String(c.value ?? "").trim() !== "") ||
      (c.type === "element" && c.tagName !== "img"),
  );
  if (hasOtherContent) return null;

  return imgs.length === 1 ? "img-single" : "img-row";
}

/**
 * AI 回复的 Markdown 渲染：
 * - 使用 react-markdown + GFM（表格、删除线、任务列表、自动链接）
 * - 默认不渲染原始 HTML（安全，防 XSS）
 * - 链接统一新窗口打开
 * - 图片由 LLM 内嵌在正文中，直接内联渲染；URL 中的空格/括号先做百分号转义，
 *   避免 CommonMark 解析截断链接目标
 * - 纯图片段落按张数打上 img-single / img-row 标记，由 CSS 控制居中/并排
 */
export function MarkdownContent({ text }: MarkdownContentProps) {
  const normalized = useMemo(() => normalizeMarkdownDestinations(text), [text]);

  const components: Components = {
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
    p: ({ node, children, ...rest }) => {
      const cls = classifyImageParagraph(node);
      return (
        <p {...rest} className={cls ?? undefined}>
          {children}
        </p>
      );
    },
  };

  return (
    <div className="markdown">
      <ReactMarkdown remarkPlugins={[remarkGfm]} components={components}>
        {normalized}
      </ReactMarkdown>
    </div>
  );
}
