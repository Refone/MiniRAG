/**
 * 站内图片 Blob 缓存 Hook（自 lib/imageCache.ts 拆出）。
 *
 * 无组件内状态 (重挂载安全, BUG-006):
 * - 渲染时同步读缓存: 已缓存立即返回 objectURL, 未缓存返回原 URL;
 * - 订阅缓存版本号: fetch 就绪 → bump → 重渲染 → 切到 objectURL;
 * - effect 仅负责在未命中时发起后台填充 (并发去重, 失败静默回退原 URL);
 * - 组件因 markdown 重解析被卸载重挂, 首帧也能直接拿到已缓存的 blob URL
 *   —— src 不会在 blob 与原 URL 之间来回跳, 消除流式输出时的剧烈闪烁。
 */
import { useEffect, useSyncExternalStore } from "react";
import {
  ensureImageCached,
  getImageUrl,
  imageCacheStore,
  isInternalImageUrl,
} from "@/lib/cache/imageCache";

export function useImageUrl(url: string | undefined): string | undefined {
  useSyncExternalStore(imageCacheStore.subscribe, imageCacheStore.getVersion);

  useEffect(() => {
    if (!url || !isInternalImageUrl(url)) return;
    ensureImageCached(url);
  }, [url]);

  return url ? getImageUrl(url) : url;
}
