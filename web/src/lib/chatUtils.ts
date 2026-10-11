/** 对话页相关纯函数（从 chat.html 移植）。 */

export function nowTime(): string {
  return new Date().toLocaleTimeString('zh-CN', { hour: '2-digit', minute: '2-digit' });
}

export function formatTime(ts: number | null | undefined): string {
  if (!ts) return nowTime();
  const d = new Date(Number(ts) * 1000);
  if (Number.isNaN(d.getTime())) return nowTime();
  return d.toLocaleTimeString('zh-CN', { hour: '2-digit', minute: '2-digit' });
}

export function isImageUrl(url: string): boolean {
  try {
    const u = new URL(url);
    return /\.(png|jpe?g|gif|webp|bmp|svg)$/i.test(u.pathname);
  } catch {
    return /\.(png|jpe?g|gif|webp|bmp|svg)(\?|#|$)/i.test(url || '');
  }
}

export function normalizeUrl(rawUrl: string): string {
  const s = String(rawUrl || '').trim();
  if (!s) return '';
  // 尽量保留原始 URL，但把空格编码，避免 img src 失败
  return s.replace(/\s/g, '%20');
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

  // 优先按“每行一个 URL”的方式解析，允许 URL 中包含空格
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

export interface ParsedAnswer {
  text: string;
  images: string[];
}

/** 汇总“文本 + 图片”：Block 显式标记 ∪ 后端候选 ∪ 文本宽松提取。 */
export function parseAnswerWithImages(answerText: string, candidateImageUrls: string[] = []): ParsedAnswer {
  const { text, images: imagesFromBlock } = parseAnswerAndImages(answerText);
  const candidates = (candidateImageUrls || []).map(normalizeUrl).filter(isImageUrl);
  const looseImages = extractUrlsLoose(answerText).map(normalizeUrl).filter(isImageUrl);

  const allImages = new Set<string>([
    ...(imagesFromBlock.length > 0 ? imagesFromBlock : []),
    ...candidates,
    ...looseImages,
  ]);

  return { text, images: Array.from(allImages) };
}
