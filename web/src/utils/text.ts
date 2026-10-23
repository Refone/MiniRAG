/** 文本与 URL 清洗纯函数 */

/**
 * 剥离零宽字符 (U+200B 零宽空格 / U+200C-U+200D / U+2060 / U+FEFF)。
 * LLM 输出常在图链目标前后夹带这些不可见字符 (BUG-005):
 * `![图](​/api/files/...)` → 浏览器请求 `%E2%80%8B/api/files/...` → 404 无法渲染。
 * JS 的 \s 与 trim 都不覆盖它们, 必须显式清除。
 */
export function stripZeroWidth(s: string): string {
  return String(s ?? "").replace(/[\u200B-\u200D\u2060\uFEFF]/g, "");
}

/**
 * 图片 src 统一清洗 (BUG-005 + BUG-007):
 * - 剥离零宽字符 (U+200B 等): 否则浏览器请求 %E2%80%8B/api/files/... → 404;
 * - 剥离 LLM 伪影前导 "](" (BUG-007): 模型偶发输出 ![说明](](url), CommonMark
 *   会把 src 解析成以 "]" 开头的相对路径 → 浏览器解析失败, vite dev 回退
 *   index.html (text/html) → 裂图。合法图片地址均不以 "]" 开头, 剥除安全。
 */
export function cleanImageSrc(src: string): string {
  return stripZeroWidth(src).replace(/^\]\(*/, "");
}

export function normalizeUrl(rawUrl: string): string {
  const s = String(rawUrl || '').trim();
  if (!s) return '';
  // 尽量保留原始 URL，但把空格编码，避免 img src 失败；先剥离零宽字符
  return stripZeroWidth(s).replace(/\s/g, '%20');
}

export function isImageUrl(url: string): boolean {
  try {
    const u = new URL(url);
    return /\.(png|jpe?g|gif|webp|bmp|svg)$/i.test(u.pathname);
  } catch {
    return /\.(png|jpe?g|gif|webp|bmp|svg)(\?|#|$)/i.test(url || '');
  }
}

export function dedupeKeepOrder(arr: unknown[]): string[] {
  const seen = new Set<string>();
  const out: string[] = [];
  for (const x of Array.isArray(arr) ? arr : []) {
    const v = String(x ?? '');
    if (!v || seen.has(v)) continue;
    seen.add(v);
    out.push(v);
  }
  return out;
}

export function extractUrlsLoose(text: string): string[] {
  const s = String(text || '');
  const regex = /(https?:\/\/[^\s]+)/g;
  const matches = s.match(regex) || [];
  const trimTailPunct = (u: string) => String(u || '').replace(/[)\]}'">，。,;；\]】）＞]+$/g, '');
  const trimHeadPunct = (u: string) => String(u || '').replace(/^[<([{'"]+|^[＜（【\[]+/g, '');

  const urls: string[] = [];
  for (const m of matches) {
    const u = trimHeadPunct(trimTailPunct(m));
    if (u) urls.push(u);
  }
  return dedupeKeepOrder(urls);
}
