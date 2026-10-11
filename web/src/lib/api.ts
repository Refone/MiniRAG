/**
 * API 基地址解析：
 * - 优先读取环境变量（VITE_QUERY_API_BASE / VITE_IMPORT_API_BASE）
 * - 生产构建（非 DEV）且由 http 提供时，回退到同源地址
 * - 开发环境回退到查询服务 8001 / 导入服务 8000 默认端口
 */
function resolveApiBase(envKey: 'VITE_QUERY_API_BASE' | 'VITE_IMPORT_API_BASE', fallbackPort: number): string {
  const explicit = import.meta.env[envKey] as string | undefined;
  if (explicit) return explicit.replace(/\/+$/, '');
  if (!import.meta.env.DEV && typeof window !== 'undefined' && window.location.origin.startsWith('http')) {
    return window.location.origin;
  }
  return `http://127.0.0.1:${fallbackPort}`;
}

/** 查询服务（对话/历史/流式输出） */
export const QUERY_API_BASE = resolveApiBase('VITE_QUERY_API_BASE', 8001);

/** 导入服务（文件上传与状态轮询） */
export const IMPORT_API_BASE = resolveApiBase('VITE_IMPORT_API_BASE', 8000);

console.log(`[api] 接口地址：查询服务 ${QUERY_API_BASE} ｜ 导入服务 ${IMPORT_API_BASE}`);
