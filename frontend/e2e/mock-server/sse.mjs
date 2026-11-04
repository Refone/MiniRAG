/**
 * SSE 帧输出（E2E mock 专用）
 *
 * 帧结构：{ event, data?, delayMs? }
 * - 事件名与 frontend/src/lib/sse.ts 对齐（progress / fork / child-progress / delta /
 *   final / usage / __close__）；
 * - closeMode="end"（默认）：末尾发 __close__ 后正常关流；前端收到后主动 close()，
 *   否则 EventSource 会自动重连；
 * - closeMode="destroy"：直接掐断连接、不发 __close__，用于模拟"连接中断"。
 */
const sleep = (ms) => new Promise((resolve) => setTimeout(resolve, ms));

export async function writeSse(res, frames, { paceMs = 50, closeMode = "end" } = {}) {
  res.writeHead(200, {
    "Content-Type": "text/event-stream; charset=utf-8",
    "Cache-Control": "no-cache",
    Connection: "keep-alive",
  });
  res.flushHeaders?.();
  // 客户端提前断开（关页 / 刷新）时吞掉 EPIPE，避免 mock 进程报错
  res.on("error", () => {});

  for (const frame of frames) {
    if (res.destroyed || res.writableEnded) return;
    await sleep(frame.delayMs ?? paceMs);
    if (res.destroyed || res.writableEnded) return;
    res.write(
      `event: ${frame.event}\ndata: ${JSON.stringify(frame.data ?? {})}\n\n`,
    );
  }

  if (closeMode === "destroy") {
    res.destroy();
    return;
  }
  if (!res.destroyed && !res.writableEnded) res.end();
}
