/** 时间格式化纯函数 */

export function nowTime(): string {
  return new Date().toLocaleTimeString('zh-CN', { hour: '2-digit', minute: '2-digit' });
}

export function formatTime(ts: number | null | undefined): string {
  if (!ts) return nowTime();
  const d = new Date(Number(ts) * 1000);
  if (Number.isNaN(d.getTime())) return nowTime();
  return d.toLocaleTimeString('zh-CN', { hour: '2-digit', minute: '2-digit' });
}
