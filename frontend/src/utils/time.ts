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

/** 精确到秒的时钟文案（Token 面板「HH:MM:SS 更新」） */
export function formatTimeFull(ts: number | null | undefined): string {
  if (!ts) return formatTime(ts);
  const d = new Date(Number(ts) * 1000);
  if (Number.isNaN(d.getTime())) return formatTime(ts);
  return d.toLocaleTimeString('zh-CN', {
    hour: '2-digit',
    minute: '2-digit',
    second: '2-digit',
  });
}
