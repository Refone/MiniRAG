import { expect, test } from "@playwright/test";
import {
  openChat,
  scrollToBottom,
  sendQuery,
  taskCard,
  waitTaskComplete,
} from "../helpers/app";
import { readScrollTop, waitForChatPinned } from "../helpers/metrics";

/**
 * P0 回归：会话贴底跟随。
 *
 * 契约：
 * - 历史加载完停在最新消息，不显示「回到底部」；
 * - 用户主动上滚后，流式输出不得把会话拉回底部；
 * - 点「回到底部」恢复跟随并隐藏按钮。
 */
test.describe("会话滚动：贴底跟随", () => {
  test("历史加载后停在最新消息，不出现回到底部按钮", async ({ page }) => {
    await openChat(page);

    const newest = page
      .locator(".msg")
      .filter({ hasText: "最新一条历史消息" });
    await expect(newest).toHaveCount(1);
    await expect(newest).toBeInViewport();
    await waitForChatPinned(page);
    await expect(scrollToBottom(page)).not.toHaveClass(/visible/);
  });

  test("用户上滚后流式输出不再拉回底部；点回到底部恢复跟随", async ({
    page,
  }) => {
    await openChat(page);
    await waitForChatPinned(page);

    await sendQuery(page, "万用表如何测量电压？");
    const answer = page.locator(".chat-page .msg.bot .markdown").last();
    await expect(answer).toContainText("万用表");

    // 流式中途用户主动上滚：解除跟随
    const chatBox = await page.locator(".chat-page .chat").boundingBox();
    if (!chatBox) throw new Error("找不到 .chat 滚动容器");
    await page.mouse.move(
      chatBox.x + chatBox.width / 2,
      chatBox.y + Math.min(chatBox.height / 2, 300),
    );
    await page.mouse.wheel(0, -500);
    await expect(scrollToBottom(page)).toHaveClass(/visible/);
    const before = await readScrollTop(page);

    // 剩余 delta 继续在视口下方增长，会话位置不得被拉回
    await expect(answer).toContainText("不要在带电电路上切换档位。");
    await waitTaskComplete(page);
    expect(Math.abs((await readScrollTop(page)) - before)).toBeLessThanOrEqual(2);
    await expect(taskCard(page)).toBeVisible();

    // 手动回到底部 → 恢复跟随
    await scrollToBottom(page).click();
    await waitForChatPinned(page);
    await expect(scrollToBottom(page)).not.toHaveClass(/visible/);
  });
});
