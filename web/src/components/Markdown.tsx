import { memo, useMemo } from "react";
import ReactMarkdown, { type Components } from "react-markdown";
import remarkGfm from "remark-gfm";
import rehypeRaw from "rehype-raw";
import type { Element, Root } from "hast";
import { useImageUrl } from "@/lib/imageCache";
import {
  cleanImageSrc,
  findPendingImage,
  normalizeMarkdownDestinations,
} from "@/lib/chatUtils";

interface MarkdownContentProps {
  text: string;
  /** 是否为流式输出中间态：开启时会把未写完的图片语法截下，显示占位 */
  streaming?: boolean;
  /**
   * 是否渲染原始 HTML（如 MinerU 输出的 <table> 等）。
   * 聊天页默认关闭（LLM 输出不信任原始 HTML，防 XSS）；
   * 文档管理页开启（内容来自用户自己导入的文档，需要与 demo-v4 一致地
   * 渲染 HTML 表格等）。
   */
  allowHtml?: boolean;
}

/** 段落是否只含图片（允许空白文本节点） */
function isImageOnlyParagraph(node: Element): boolean {
  if (node.tagName !== "p") return false;
  const children = node.children ?? [];
  let hasImg = false;
  for (const c of children) {
    if (c.type === "text") {
      if (String(c.value ?? "").trim() !== "") return false;
    } else if (c.type === "element" && c.tagName === "img") {
      hasImg = true;
    } else {
      return false;
    }
  }
  return hasImg;
}

/** 段落中图片数量 */
function imageCountInParagraph(node: Element): number {
  return (node.children ?? []).filter(
    (c) => c.type === "element" && c.tagName === "img",
  ).length;
}

/**
 * rehype 插件：给纯图片段落打类名，并把"连续的图片段落"合并成一行。
 * - 单个图片段落 → img-single（居中）
 * - 同一段落多图，或连续多个图片段落（LLM 输出时中间隔了空行也有效）→
 *   合并为一个 img-row（并排）
 * - 图文混排段落 → 保持默认
 */
function rehypeGroupImageParagraphs() {
  return (tree: Root) => {
    const children = tree.children ?? [];
    for (let i = 0; i < children.length; i++) {
      const node = children[i];
      if (node.type !== "element" || !isImageOnlyParagraph(node)) continue;

      // 向后收集连续的图片段落 (跳过段落间的空白文本节点)
      const group: Element[] = [node];
      let j = i + 1;
      while (j < children.length) {
        const next = children[j];
        if (next.type === "text") {
          if (String(next.value ?? "").trim() === "") {
            j++;
            continue;
          }
          break;
        }
        if (next.type === "element" && isImageOnlyParagraph(next)) {
          group.push(next);
          j++;
          continue;
        }
        break;
      }

      if (group.length === 1 && imageCountInParagraph(node) === 1) {
        node.properties = { ...node.properties, className: ["img-single"] };
      } else {
        const merged: Element = {
          type: "element",
          tagName: "p",
          properties: { className: ["img-row"] },
          children: group.flatMap((n) => n.children ?? []),
        };
        children.splice(i, j - i, merged);
      }
    }
  };
}

/** 流式输出中图片语法未写完时的 shimmer 文字占位 */
function ImagePlaceholder() {
  return (
    <span className="img-placeholder" role="status">
      图片渲染中…
    </span>
  );
}

/**
 * 图片渲染 (模块级组件, 类型稳定 —— 关键):
 * 若 components 在渲染内联创建, 每次 markdown 重解析 (流式 delta) 都会把 img
 * 当作新组件类型卸载重挂, 引起 src 在 blob 与原 URL 间来回跳的剧烈闪烁。
 * 稳定类型 + useImageUrl 无状态同步读缓存 → 重渲染/重挂载均不闪。
 */
const MarkdownImg: Components["img"] = ({ node: _node, src, alt, ...rest }) => {
  // 统一清洗 src (BUG-005/BUG-007): 零宽字符 + 前导 "](" 伪影
  const cleanSrc = typeof src === "string" ? cleanImageSrc(src) : src;
  const resolved = useImageUrl(cleanSrc);
  const imgEl = (
    <img
      src={resolved}
      alt={alt}
      {...rest}
      loading="lazy"
      referrerPolicy="no-referrer"
      className="markdown-img"
    />
  );
  // 图片可点击: 新标签页打开原图
  if (typeof cleanSrc !== "string" || cleanSrc.length === 0) return imgEl;
  return (
    <a
      href={cleanSrc}
      target="_blank"
      rel="noopener noreferrer"
      className="markdown-img-link"
    >
      {imgEl}
    </a>
  );
};

/** 链接统一新窗口打开 (模块级, 同上理由) */
const MarkdownAnchor: Components["a"] = ({ node: _node, ...rest }) => (
  <a {...rest} target="_blank" rel="noopener noreferrer" />
);

/** 模块级 components: 保证跨渲染类型稳定, 避免 react-markdown 重挂载子树 */
const markdownComponents: Components = {
  a: MarkdownAnchor,
  img: MarkdownImg,
};

/**
 * AI 回复的 Markdown 渲染：
 * - 使用 react-markdown + GFM（表格、删除线、任务列表、自动链接）
 * - 默认不渲染原始 HTML（安全，防 XSS）
 * - 链接统一新窗口打开
 * - 图片由 LLM 内嵌在正文中，直接内联渲染；URL 中的空格/括号先做百分号转义，
 *   避免 CommonMark 解析截断链接目标
 * - 纯图片段落由 rehype 插件归类：单图居中，连续多图合并为一行并排
 * - 流式输出时，未写完的图片语法（![说明](URL…）不渲染，代之以 shimmer 文字占位，
 *   等语法闭合后再渲染图片
 *
 * 性能 (测试反馈 #3/#4): 用 memo 包裹 —— 进度等不改变 text 的更新不再触发
 * markdown 重解析与整段 DOM 重渲染。
 */
export const MarkdownContent = memo(function MarkdownContent({
  text,
  streaming = false,
  allowHtml = false,
}: MarkdownContentProps) {
  const normalized = useMemo(() => normalizeMarkdownDestinations(text), [text]);
  const pending = useMemo(
    () => (streaming ? findPendingImage(normalized) : null),
    [streaming, normalized],
  );

  const renderText = pending ? pending.before : normalized;

  return (
    <div className="markdown">
      <ReactMarkdown
        remarkPlugins={[remarkGfm]}
        rehypePlugins={
          allowHtml
            ? // rehype-raw 需在图片分组插件之前, 先把原始 HTML 解析为元素
              [rehypeRaw, rehypeGroupImageParagraphs]
            : [rehypeGroupImageParagraphs]
        }
        components={markdownComponents}
      >
        {renderText}
      </ReactMarkdown>
      {pending && <ImagePlaceholder />}
    </div>
  );
});
