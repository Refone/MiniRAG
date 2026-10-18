/**
 * 回答图片画廊排版算法（纯函数，便于单测与调参）。
 *
 * 规则摘要：
 * - 竖图（高≥宽）一行最多 4 张；横图（高<宽）一行最多 2 张；两类不混排，按原顺序在类型切换处断行。
 * - 宽高比 > FULL_ROW_AR_THRESHOLD 的图独占一行。
 * - 每行按“各图宽高比之和 + 间距”反解统一行高，使行尽量铺满容器宽；
 *   受约束时取最大合法尺寸，整行水平居中。
 * - 行内图片之间间距处处相等（GALLERY_GAP），行间间距一致。
 * - 行高不超过视口高度 30%；单图宽不超过容器宽 50%（宽图 60%）且不超过原始像素宽，只缩小不放大。
 * - 被宽度上限截断的宽图在行内垂直居中；其余图高度一致（同高即基线对齐）。
 */

// ---- 布局常量（集中定义，便于调整）----
/** 行高上限 = 视口高度 × 30% */
export const ROW_HEIGHT_MAX_RATIO = 0.3;
/** 单张图显示宽 ≤ 容器宽 50% */
export const IMG_WIDTH_MAX_RATIO = 0.5;
/** 宽高比 > 2 视为宽图 */
export const WIDE_AR_THRESHOLD = 2;
/** 宽图显示宽 ≤ 容器宽 60% */
export const WIDE_WIDTH_MAX_RATIO = 0.6;
/** 宽高比 > 3 独占一行 */
export const FULL_ROW_AR_THRESHOLD = 3;
/** 行内与行间间距（px），处处相等 */
export const GALLERY_GAP = 12;
/** 竖图每行最多张数 */
export const PORTRAIT_MAX_PER_ROW = 4;
/** 横图每行最多张数 */
export const LANDSCAPE_MAX_PER_ROW = 2;
/** 图片未加载完成时的占位宽高比 */
export const PLACEHOLDER_AR = 1;
/** 未加载时的“原始尺寸”占位（足够大，避免触发不放大约束） */
export const PLACEHOLDER_NATURAL = 4096;

export interface GalleryImageInput {
  url: string;
  /** 原始像素宽；null 表示尚未加载 */
  naturalW: number | null;
  /** 原始像素高；null 表示尚未加载 */
  naturalH: number | null;
}

export interface GalleryItem {
  url: string;
  /** 显示宽度（px） */
  width: number;
  /** 显示高度（px） */
  height: number;
  /** 宽度被上限截断（宽图）：行内垂直居中，其余图按行基线对齐 */
  capped: boolean;
}

export interface GalleryRow {
  items: GalleryItem[];
  /** 行盒高度：非受限图的高度；受限宽图在此盒内垂直居中 */
  height: number;
}

interface Measured {
  url: string;
  /** 宽高比 = w / h */
  ar: number;
  /** 用于“只缩小不放大”约束的原始宽度 */
  naturalW: number;
  /** ar > WIDE_AR_THRESHOLD */
  wide: boolean;
  /** ar > FULL_ROW_AR_THRESHOLD，独占一行 */
  fullRow: boolean;
}

function measure(img: GalleryImageInput): Measured {
  const loaded =
    img.naturalW != null &&
    img.naturalH != null &&
    img.naturalW > 0 &&
    img.naturalH > 0;
  const ar = loaded ? (img.naturalW as number) / (img.naturalH as number) : PLACEHOLDER_AR;
  return {
    url: img.url,
    ar,
    naturalW: loaded ? (img.naturalW as number) : PLACEHOLDER_NATURAL,
    wide: ar > WIDE_AR_THRESHOLD,
    fullRow: ar > FULL_ROW_AR_THRESHOLD,
  };
}

/** 按“类型切换断行 + 每类上限”贪心分行，保持原顺序。 */
function groupRows(list: Measured[]): Measured[][] {
  const rows: Measured[][] = [];
  let cur: Measured[] = [];
  let curKind: "portrait" | "landscape" | null = null;

  const flush = () => {
    if (cur.length > 0) {
      rows.push(cur);
      cur = [];
      curKind = null;
    }
  };

  for (const img of list) {
    if (img.fullRow) {
      flush();
      rows.push([img]);
      continue;
    }
    const kind: "portrait" | "landscape" =
      img.ar <= 1 ? "portrait" : "landscape";
    const maxPerRow =
      kind === "portrait" ? PORTRAIT_MAX_PER_ROW : LANDSCAPE_MAX_PER_ROW;
    if (curKind !== kind) {
      flush();
      cur = [img];
      curKind = kind;
    } else {
      cur.push(img);
      if (cur.length >= maxPerRow) flush();
    }
  }
  flush();
  return rows;
}

/** 对一行求解统一行高并计算各图显示尺寸。 */
function solveRow(row: Measured[], containerW: number, vh: number): GalleryRow {
  const n = row.length;
  const sumAr = row.reduce((s, m) => s + m.ar, 0);
  /** 恰好铺满容器宽的目标行高 */
  const hTarget = (containerW - (n - 1) * GALLERY_GAP) / sumAr;
  /** 视口高度 30% 上限 */
  const hVh = vh * ROW_HEIGHT_MAX_RATIO;

  // 行高 = min(目标行高, 视口上限, 各非宽图的宽度上限折算)
  // 宽图不压低整行高度：它们单独按宽度上限截断后在行内垂直居中
  let height = Math.min(hTarget, hVh);
  for (const m of row) {
    if (m.wide) continue;
    const capW = Math.min(m.naturalW, containerW * IMG_WIDTH_MAX_RATIO);
    height = Math.min(height, capW / m.ar);
  }
  if (height <= 0) height = 1;

  const items: GalleryItem[] = row.map((m) => {
    // 宽图适用 60% 上限（替代普通图的 50% 通用上限），普通图 50%；
    // 两者都不超过原始像素宽（只缩小不放大）
    const capW = Math.min(
      m.naturalW,
      containerW * (m.wide ? WIDE_WIDTH_MAX_RATIO : IMG_WIDTH_MAX_RATIO),
    );
    const idealW = height * m.ar;
    const width = Math.min(idealW, capW);
    return {
      url: m.url,
      width,
      height: width / m.ar,
      capped: width < idealW - 0.01,
    };
  });

  // 行盒高度 = 行内最大显示高度（全为受限宽图时不产生多余留白）
  const boxHeight = Math.max(...items.map((i) => i.height));
  return { items, height: boxHeight };
}

/** 计算画廊布局：输入图片与容器尺寸，输出分行结果。 */
export function layoutGallery(
  images: GalleryImageInput[],
  containerW: number,
  vh: number,
): GalleryRow[] {
  if (images.length === 0 || containerW <= 0) return [];
  return groupRows(images.map(measure)).map((row) =>
    solveRow(row, containerW, vh),
  );
}
