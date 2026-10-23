/**
 * API 客户端基础设施 —— 只做"配置 + 传输"，不含任何业务语义。
 *
 * 后端全部路由统一挂载 /api 前缀 (见 docs/feat/文档管理页面/后端方案.md V1-4):
 * - dev: API_BASE=http://127.0.0.1:8000 直连 (CORS 放开)
 * - prod: API_BASE=origin, 经 nginx /api/ 反代
 */

function resolveApiBase(fallbackPort: number): string {
  const explicit = import.meta.env["VITE_API_BASE"] as string | undefined;
  if (explicit) return explicit.replace(/\/+$/, "");
  if (
    !import.meta.env.DEV &&
    typeof window !== "undefined" &&
    window.location.origin.startsWith("http")
  ) {
    return window.location.origin;
  }
  return `http://127.0.0.1:${fallbackPort}`;
}

export const API_BASE = resolveApiBase(8000);

/** 非 2xx 时抛出带后端 detail 的 Error */
async function throwOnError(res: Response): Promise<Response> {
  if (!res.ok) {
    let detail = "";
    try {
      const data = await res.json();
      detail = data?.detail ?? JSON.stringify(data);
    } catch {
      detail = await res.text().catch(() => "");
    }
    throw new Error(detail || `请求失败 (${res.status})`);
  }
  return res;
}

/** 统一 fetch 封装：拼接 API_BASE、统一错误处理。path 以 /api 开头。 */
export async function request(path: string, init?: RequestInit): Promise<Response> {
  const res = await fetch(`${API_BASE}${path}`, init);
  await throwOnError(res);
  return res;
}
