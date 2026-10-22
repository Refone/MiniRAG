/**
 * session-global 图片 Blob 缓存 (Session-MVVM V0, 设计文档 §5.3)
 *
 * - 站内图片 (/api/files/**, 含 API_BASE 绝对形态): fetch → blob →
 *   URL.createObjectURL 入缓存, 组件重挂/切 Tab 后直接复用解码结果;
 * - 外部 http(s) 图片: 多数无 CORS 不可 fetch, 原样返回, 交给浏览器 HTTP 缓存;
 * - LRU 上限 200 条 / 200MB; 仅回收未被任何 <img> 使用的条目
 *   (refs 引用计数), 回收时 revokeObjectURL。
 */
import { useEffect, useState } from "react";
import { API_BASE } from "@/lib/api";

interface ImageEntry {
  objectUrl: string;
  bytes: number;
  lastUsed: number;
  /** 当前被多少个已挂载 <img> 使用 */
  refs: number;
}

const MAX_ENTRIES = 200;
const MAX_BYTES = 200 * 1024 * 1024;

const imageMap = new Map<string, ImageEntry>();
const inflight = new Map<string, Promise<ImageEntry>>();
let totalBytes = 0;

function isInternalUrl(url: string): boolean {
  return (
    url.startsWith("/api/files/") || url.startsWith(`${API_BASE}/api/files/`)
  );
}

/** 回收 refs===0 的最久未用条目, 直到不超限或无可回收 */
function evictIfNeeded(): void {
  while (imageMap.size > MAX_ENTRIES || totalBytes > MAX_BYTES) {
    let oldestKey: string | null = null;
    let oldestTime = Infinity;
    for (const [key, entry] of imageMap) {
      if (entry.refs === 0 && entry.lastUsed < oldestTime) {
        oldestTime = entry.lastUsed;
        oldestKey = key;
      }
    }
    if (oldestKey === null) return; // 全部在用: 显示中的图片本就受 DOM 约束, 不再缓存新条目
    const entry = imageMap.get(oldestKey);
    if (!entry) return;
    URL.revokeObjectURL(entry.objectUrl);
    totalBytes -= entry.bytes;
    imageMap.delete(oldestKey);
  }
}

function fetchAndCache(url: string): Promise<ImageEntry> {
  const existing = inflight.get(url);
  if (existing) return existing;

  const p = fetch(url)
    .then((res) => {
      if (!res.ok) throw new Error(`图片请求失败 ${res.status}`);
      return res.blob();
    })
    .then((blob) => {
      const objectUrl = URL.createObjectURL(blob);
      evictIfNeeded();
      const entry: ImageEntry = {
        objectUrl,
        bytes: blob.size,
        lastUsed: Date.now(),
        refs: 0,
      };
      imageMap.set(url, entry);
      totalBytes += blob.size;
      return entry;
    })
    .finally(() => {
      inflight.delete(url);
    });
  inflight.set(url, p);
  return p;
}

/** 同步读缓存 (无 fetch): 命中返回 objectURL, 未命中返回原 URL */
export function getImageUrl(url: string): string {
  const hit = imageMap.get(url);
  if (hit) {
    hit.lastUsed = Date.now();
    return hit.objectUrl;
  }
  return url;
}

/**
 * 组件内使用: 命中立即返回 objectURL; 未命中先返回原 URL 渲染,
 * 异步 fetch→blob→缓存, 就绪后切换到 objectURL (并发去重, 失败静默回退原 URL)。
 * 挂载期间持有引用计数, 防止正在展示的图片被 LRU 回收。
 */
export function useImageUrl(url: string | undefined): string | undefined {
  const [objectUrl, setObjectUrl] = useState<string | null>(null);

  useEffect(() => {
    if (!url || !isInternalUrl(url)) {
      setObjectUrl(null);
      return;
    }

    let cancelled = false;
    let entry: ImageEntry | null = null;
    const adopt = (e: ImageEntry) => {
      if (cancelled) return;
      entry = e;
      e.refs += 1;
      e.lastUsed = Date.now();
      setObjectUrl(e.objectUrl);
    };

    const hit = imageMap.get(url);
    if (hit) {
      adopt(hit);
      return () => {
        cancelled = true;
        if (entry) {
          entry.refs -= 1;
          if (entry.refs <= 0) evictIfNeeded();
        }
      };
    }

    setObjectUrl(null); // 首次先走原 URL, blob 就绪后切换
    fetchAndCache(url)
      .then(adopt)
      .catch(() => {
        /* 失败静默回退原 URL */
      });

    return () => {
      cancelled = true;
      if (entry) {
        entry.refs -= 1;
        if (entry.refs <= 0) evictIfNeeded();
      }
    };
  }, [url]);

  return objectUrl ?? url;
}
