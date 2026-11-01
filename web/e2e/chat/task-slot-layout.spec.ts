import { expect, test } from "@playwright/test";
import { openChat, sendQuery, taskCard, waitTaskComplete } from "../helpers/app";
import { expectLayoutStable, readChatLayout } from "../helpers/metrics";

/** 桌面收起态卡片占位：卡片 35px + 8px 间距（chat.css --task-slot-h） */
const SLOT_DESKTOP = 43;

const slotHeight = (page: import("@playwright/test").Page) =>
  page
    .locator(".chat-page .task-slot")
    .evaluate((el) => el.getBoundingClientRect().height);

/**
 * P0 回归：任务卡片与历史会话解耦。
 *
 * 契约：.task-slot 高度恒为 --task-slot-h（桌面 43px / ≤720px 60px）；
 * 卡片开合只改变自身在槽位内的纵向溢出，不推动会话滚动、底部留白与输入卡。
 */
test.describe("任务卡片与历史会话解耦", () => {
  test("无任务 / 卡片在 / 卡片展开时，槽位高度恒定（桌面 43px）", async ({
    page,
  }) => {
    await openChat(page);
    await expect.poll(() => slotHeight(page)).toBeCloseTo(SLOT_DESKTOP, 1);

    await sendQuery(page, "万用表如何测量电压？");
    await expect(taskCard(page)).toBeVisible();
    await expect.poll(() => slotHeight(page)).toBeCloseTo(SLOT_DESKTOP, 1);

    await taskCard(page).locator("summary").click();
    await expect(taskCard(page)).toHaveAttribute("open", "");
    await expect.poll(() => slotHeight(page)).toBeCloseTo(SLOT_DESKTOP, 1);
  });

  test("@mobile 移动端槽位放宽到 60px", async ({ page }) => {
    await openChat(page);
    await expect.poll(() => slotHeight(page)).toBeCloseTo(60, 1);

    await sendQuery(page, "万用表如何测量电压？");
    await expect.poll(() => slotHeight(page)).toBeCloseTo(60, 1);
  });

  test("卡片展开 / 收起不改变会话滚动位置与输入卡位置", async ({ page }) => {
    await openChat(page);
    await sendQuery(page, "万用表如何测量电压？");
    await waitTaskComplete(page);

    const card = taskCard(page);
    const before = await readChatLayout(page);

    await card.locator("summary").click();
    await expect(card).toHaveAttribute("open", "");
    expectLayoutStable(before, await readChatLayout(page));

    await card.locator("summary").click();
    await expect(card).not.toHaveAttribute("open", "");
    expectLayoutStable(before, await readChatLayout(page));
  });
});
