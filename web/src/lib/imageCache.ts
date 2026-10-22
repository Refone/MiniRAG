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
 *   新图, 新图直接走原 URL)。
 *
 * 流式闪烁修正 (用户反馈):
 * - useImageUrl 不持有组件内状态: 渲染时同步读缓存 (getImageUrl), 新条目就绪
 *   时通过 useSyncExternalStore 订阅版本号触发重渲染。组件即使因 markdown
 *   重解析被卸载重挂, 首帧也能直接拿到已缓存的 blob URL —— src 不会在
 *   blob 与原 URL 之间来回跳, 消除流式输出时的剧烈闪烁。
 */
import { useEffect, useSyncExternalStore } from "react";
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

/** 缓存版本号 + 订阅者: 新条目就绪时通知所有 useImageUrl 组件重渲染 */
let version = 0;
const listeners = new Set<() => void>();

function bump(): void {
  version += 1;
  listeners.forEach((l) => l());
}

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
      bump();
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
 * 组件内使用 (无组件内状态, 重挂载安全):
 * - 渲染时同步读缓存: 已缓存立即返回 objectURL, 未缓存返回原 URL;
 * - 订阅缓存版本号: fetch 就绪 → bump → 重渲染 → 切到 objectURL;
 * - effect 仅负责在未命中时发起 fetch (并发去重, 失败静默回退原 URL)。
 */
export function useImageUrl(url: string | undefined): string | undefined {
  useSyncExternalStore(
    (listener) => {
      listeners.add(listener);
      return () => listeners.delete(listener);
    },
    () => version,
  );

  useEffect(() => {
    if (!url || !isInternalUrl(url)) return;
    if (!imageMap.has(url) && !inflight.has(url)) {
      void fetchAndCache(url);
    }
  }, [url]);

  return url ? getImageUrl(url) : url;
}
