/**
 * session-global 图片 Blob 缓存 (Session-MVVM V0, 设计 §5.3 + 测试反馈 #2 修正)
 *
 * 站内图片 (/api/files/**, 含 API_BASE 绝对形态): fetch → blob →
 * URL.createObjectURL 入缓存, 组件重挂/切 Tab 后直接复用解码结果;
 * 外部 http(s) 图片: 多数无 CORS 不可 fetch, 原样返回, 交给浏览器 HTTP 缓存。
 *
 * 测试反馈 #2 修正说明 (对比初版实现):
 * - 初版带 LRU 淘汰 + revoke + 引用计数。但 <Activity> 隐藏会销毁 effects,
 *   引用计数在隐藏时被误降为 0, 触发淘汰并 revoke 仍在 DOM 中的 <img> 所指向
 *   的 blob URL —— 切回时图片断裂、回退原 URL 重新请求并闪烁。
 * - 现改为: 已缓存条目【绝不淘汰】(会话内存, 条目数/字节数封顶, 满后不再缓存
 *   新图, 新图直接走原 URL); 未命中时保留同一 URL 上一次的 objectURL,
 *   避免切回/重挂瞬间闪回原 URL。
 */
import { useEffect, useState } from "react";
import { API_BASE } from "@/lib/api";

interface ImageEntry {
  objectUrl: string;
  bytes: number;
}

const MAX_ENTRIES = 300;
const MAX_BYTES = 300 * 1024 * 1024;

const imageMap = new Map<string, ImageEntry>();
const inflight = new Map<string, Promise<ImageEntry | null>>();
let totalBytes = 0;

function isInternalUrl(url: string): boolean {
  return (
    url.startsWith("/api/files/") || url.startsWith(`${API_BASE}/api/files/`)
  );
}

function hasCapacity(blobSize: number): boolean {
  return (
    imageMap.size < MAX_ENTRIES && totalBytes + blobSize <= MAX_BYTES
  );
}

function fetchAndCache(url: string): Promise<ImageEntry | null> {
  const existing = inflight.get(url);
  if (existing) return existing;

  const p = fetch(url)
    .then((res) => {
      if (!res.ok) throw new Error(`图片请求失败 ${res.status}`);
      return res.blob();
    })
    .then((blob) => {
      const objectUrl = URL.createObjectURL(blob);
      if (!hasCapacity(blob.size)) {
        // 容量封顶: 不缓存, 立即回收本次临时 objectURL
        URL.revokeObjectURL(objectUrl);
        return null;
      }
      const entry: ImageEntry = { objectUrl, bytes: blob.size };
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
  if (hit) return hit.objectUrl;
  return url;
}

/**
 * 组件内使用: 命中立即返回 objectURL; 未命中先返回原 URL 渲染,
 * 异步 fetch→blob→缓存, 就绪后切换到 objectURL (并发去重, 失败静默回退原 URL)。
 * 同一 URL 的重复 effect (Activity 切回/组件重挂) 保留既有 objectURL, 防止闪回。
 */
export function useImageUrl(url: string | undefined): string | undefined {
  const [resolved, setResolved] = useState<{
    url: string;
    objectUrl: string | null;
  } | null>(null);

  useEffect(() => {
    if (!url || !isInternalUrl(url)) {
      setResolved(null);
      return;
    }

    const hit = imageMap.get(url);
    if (hit) {
      setResolved({ url, objectUrl: hit.objectUrl });
      return;
    }

    // 同一 URL 未命中重跑 (切回/重挂): 保留既有 objectURL, 避免闪回原 URL
    setResolved((prev) =>
      prev && prev.url === url ? prev : { url, objectUrl: null },
    );

    let cancelled = false;
    fetchAndCache(url)
      .then((entry) => {
        if (!cancelled && entry) {
          setResolved({ url, objectUrl: entry.objectUrl });
        }
      })
      .catch(() => {
        /* 失败静默回退原 URL */
      });

    return () => {
      cancelled = true;
    };
  }, [url]);

  return resolved && resolved.url === url ? resolved.objectUrl ?? url : url;
}
