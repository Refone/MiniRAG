/**
 * SSE 帧输出（E2E mock 专用）
 *
 * 帧结构：{ event, data?, delayMs? }
 * - 事件名与 web/src/lib/sse.ts 对齐（progress / delta / final / usage / __close__）；
 * - 末尾必须发 __close__：前端收到后主动 close()，否则 EventSource 会自动重连。
 */
const sleep = (ms) => new Promise((resolve) => setTimeout(resolve, ms));

export async function writeSse(res, frames, defaultPaceMs = 50) {
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
    await sleep(frame.delayMs ?? defaultPaceMs);
    if (res.destroyed || res.writableEnded) return;
    res.write(
      `event: ${frame.event}\ndata: ${JSON.stringify(frame.data ?? {})}\n\n`,
    );
  }

  if (!res.destroyed && !res.writableEnded) res.end();
}
