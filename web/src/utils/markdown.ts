/** Markdown 文本处理纯函数 */

import { extractUrlsLoose, isImageUrl, normalizeUrl, stripZeroWidth } from "./text";

export function findLastImageMarkerIndex(raw: string): { idx: number; len: number } {
  const s = String(raw || '');
  // 支持多种写法：【图片】、【 图片 】、[图片]、[ 图片 ]
  const re = /【\s*图片\s*】|\[\s*图片\s*\]/g;
  let m: RegExpExecArray | null;
  let lastIdx = -1;
  let lastLen = 0;
  while ((m = re.exec(s)) !== null) {
    lastIdx = m.index;
    lastLen = m[0].length;
  }
  return { idx: lastIdx, len: lastLen };
}

export function parseAnswerAndImages(text: string): { text: string; images: string[] } {
  const raw = String(text || '');
  const { idx, len } = findLastImageMarkerIndex(raw);
  if (idx === -1) return { text: raw, images: [] };

  const before = raw.slice(0, idx).trimEnd();
  const after = raw.slice(idx + len).trim();
  const urls: string[] = [];

  // 优先按"每行一个 URL"的方式解析，允许 URL 中包含空格
  const lines = after.split(/\r?\n/).map((l) => l.trim()).filter(Boolean);
  for (const line of lines) {
    if (line.startsWith('http://') || line.startsWith('https://')) {
      urls.push(line);
    } else {
      urls.push(...extractUrlsLoose(line));
    }
  }

  // 去重保序 + 过滤图片链接
  const seen = new Set<string>();
  const images: string[] = [];
  for (const u of urls) {
    const normalized = normalizeUrl(u);
    if (!isImageUrl(normalized) || seen.has(normalized)) continue;
    seen.add(normalized);
    images.push(normalized);
  }
  return { text: before, images };
}

/**
 * 修复 Markdown 链接/图片目标中的空格与括号。
 * 参考内容中的图片 URL 可能包含空格或括号 (如目录名 "用户指南-(YTGZ,zh-cn)")，
 * LLM 原样内嵌为 ![说明](url) 时，CommonMark 会把第一个 ")" 当作链接终点，
 * 导致 react-markdown 解析出的 URL 被截断、图片 404。
 * 这里按括号配平扫描出完整 URL，再把空格/括号做百分号转义。
 */
export function normalizeMarkdownDestinations(text: string): string {
  const s = String(text || "");
  const re = /(!?)\[([^\]]*)\]\(/g;
  let out = "";
  let last = 0;
  let m: RegExpExecArray | null;

  const escapeUrl = (url: string): string =>
    stripZeroWidth(String(url || ""))
      .replace(/\s/g, "%20")
      .replace(/\(/g, "%28")
      .replace(/\)/g, "%29");

  while ((m = re.exec(s)) !== null) {
    const destStart = m.index + m[0].length;
    out += s.slice(last, destStart);

    const rest = s.slice(destStart);
    // BUG-007: LLM 偶发输出 ![说明](](url) —— 目标前多一个 "](" 伪影。
    // 扫描前先剥掉前导 "]" (及紧跟的 "("), 否则 url 以 "]" 开头、浏览器解析失败。
    // 合法 URL 不可能以 "]" 开头, 剥除无副作用。
    const leadArtifact = rest.match(/^\]\(*/)?.[0] ?? "";
    const head = rest.slice(leadArtifact.length);
    let url = "";
    let consumed = leadArtifact.length;
    let complete = false;

    if (head.startsWith("<")) {
      // 尖括号形式 <url>: 括号/空格可在内部出现, 取到闭合的 ">"
      const close = head.indexOf(">");
      if (close !== -1) {
        url = head.slice(1, close);
        consumed += close + 1;
        complete = true;
      }
    }

    if (!complete) {
      // 普通形式: 括号配平扫描, 直到配平的 ")"
      let depth = 0;
      let i = 0;
      for (; i < head.length; i++) {
        const c = head[i];
        if (c === "(") {
          depth++;
        } else if (c === ")") {
          if (depth === 0) {
            complete = true;
            break;
          }
          depth--;
        }
      }
      url = head.slice(0, i).trim();
      consumed += i;
    }

    if (complete) {
      out += escapeUrl(url);
      last = destStart + consumed;
    } else {
      // 未闭合的图片/链接语法 (流式输出中间态或异常截断): 原样保留, 不做转义,
      // 避免把后续文字 (如错误提示) 一起当成 URL 转义
      out += rest;
      last = s.length;
      break;
    }
  }

  return out + s.slice(last);
}

/**
 * 检测流式文本末尾是否有未写完的图片语法（如 ![说明](URL 还没闭合）。
 * 返回 { before, pending }：before 是可安全渲染的部分，pending 是截下的未完成部分；
 * 没有未闭合图片时返回 null。
 */
export function findPendingImage(
  text: string,
): { before: string; pending: string } | null {
  const s = String(text || "");
  const idx = s.lastIndexOf("![");
  if (idx === -1) return null;

  const tail = s.slice(idx);
  const openIdx = tail.indexOf("](");
  if (openIdx === -1) {
    // 已出现闭合的 "]" 但后面不是 "(": 视为普通文本 (如 "![重要]"), 不截流
    if (tail.indexOf("]") !== -1) return null;
    return { before: s.slice(0, idx), pending: tail };
  }

  // 括号配平扫描: 找到深度 0 的 ")" 即图片语法完整
  const rest = tail.slice(openIdx + 2);
  let depth = 0;
  for (let i = 0; i < rest.length; i++) {
    const c = rest[i];
    if (c === "(") {
      depth++;
    } else if (c === ")") {
      if (depth === 0) return null;
      depth--;
    }
  }
  return { before: s.slice(0, idx), pending: tail };
}

/**
 * 剥离行内 Markdown 语法，只保留纯文本。
 * 历史数据里 title_stack 直接存了标题原文（含 **加粗**、`代码` 等标记），
 * 切块卡片头按纯文本渲染时会把这些符号原样显示出来，展示前先清洗一遍。
 */
export function stripInlineMarkdown(s: string): string {
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
