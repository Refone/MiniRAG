/**
 * 会话级请求响应缓存 (Session-MVVM V0, 设计文档 §5.2)
 *
 * - 缓存 GET 类接口的原始响应, 避免页面重挂/切 Tab 时重复请求;
 * - 并发去重: 同一 key 的进行中请求共享同一个 Promise;
 * - TTL 仅作安全网 (防多浏览器 Tab 互相改动造成脏读), 主失效机制是
 *   store 动作内的手动 invalidateCache (收敛为 3 处, 见 docsStore/chatStore)。
 */

interface CacheEntry<T> {
  data: T;
  ts: number;
}

const dataCache = new Map<string, CacheEntry<unknown>>();
const inflight = new Map<string, Promise<unknown>>();

export interface CachedGetOptions {
  /** 缓存有效期 (毫秒), 默认 60s */
  ttlMs?: number;
  /** 强制绕过缓存重新请求 */
  force?: boolean;
}

export async function cachedGet<T>(
  key: string,
  fetcher: () => Promise<T>,
  opts: CachedGetOptions = {},
): Promise<T> {
  const { ttlMs = 60_000, force = false } = opts;

  if (!force) {
    const hit = dataCache.get(key);
    if (hit && Date.now() - hit.ts < ttlMs) return hit.data as T;
  }

  const existing = inflight.get(key);
  if (existing) return existing as Promise<T>;

  const p = fetcher()
    .then((data) => {
      dataCache.set(key, { data, ts: Date.now() });
      return data;
    })
    .finally(() => {
      inflight.delete(key);
    });
  inflight.set(key, p);
  return p;
}

/** 按前缀清除缓存 (如 "docs:list"、"docs:detail:123"、"history:xxx") */
export function invalidateCache(keyPrefix: string): void {
  for (const key of dataCache.keys()) {
    if (key.startsWith(keyPrefix)) dataCache.delete(key);
  }
}
