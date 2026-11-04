import { expect, test } from "@playwright/test";
import { openChat } from "../helpers/app";
import { readChatLayout } from "../helpers/metrics";

/**
 * P0 回归：输入框高度变化 → 会话底部留白同步（--composer-h 只跟输入卡走）。
 * 契约：.chat 的 padding-bottom = --composer-h + --task-slot-h + 28px；
 * 输入卡长高多少，底部留白就加多少。
 *
 * 注意：输入卡高度与 --composer-h 的写回是"尺寸变化 → ResizeObserver"两帧关系，
 * 断言必须轮询到两者一致，不能在一次读取里比对。
 */
test("输入框长高时，会话底部留白同步增长", async ({ page }) => {
  await openChat(page);
  const before = await readChatLayout(page);

  const input = page.locator(".chat-page .composer textarea");
  await input.fill("第一行\n第二行\n第三行\n第四行\n第五行\n第六行");

  await expect
    .poll(
      async () =>
        (await readChatLayout(page)).composerRect.height -
        before.composerRect.height,
      { message: "输入卡应随多行内容长高" },
    )
    .toBeGreaterThan(10);

  // 留白增量 = 输入卡增量（等 --composer-h 写回）
  await expect
    .poll(
      async () => {
        const cur = await readChatLayout(page);
        return Math.abs(
          cur.paddingBottom -
            before.paddingBottom -
            (cur.composerRect.height - before.composerRect.height),
        );
      },
      { message: "留白增量应与输入卡增量一致" },
    )
    .toBeLessThanOrEqual(1);

  // 留白公式恒定：composer-h + task-slot-h + 28
  await expect
    .poll(async () => {
      const cur = await readChatLayout(page);
      const composerVar = parseFloat(cur.composerVar);
      return Math.abs(
        cur.paddingBottom - (composerVar + cur.taskSlotHeight + 28),
      );
    })
    .toBeLessThanOrEqual(1);
});
