import { expect, test } from "@playwright/test";
import { openChat, sendQuery, taskCard, waitTaskComplete } from "../helpers/app";

/**
 * P0 回归：查询进度卡默认收起。
 *
 * 契约：<details class="progress"> 不带 open 属性（不自动展开）；用户点击摘要可开合；
 * 新查询重新挂载后回到收起态。
 */
test.describe("查询任务卡片：默认收起", () => {
  test("新查询的进度卡不自动展开，可手动开合", async ({ page }) => {
    await openChat(page);
    await expect(taskCard(page)).toHaveCount(0);

    await sendQuery(page, "万用表如何测量电压？");
    const card = taskCard(page);
    await expect(card).not.toHaveAttribute("open", "");
    await expect(card.locator("ul")).toBeHidden();

    await card.locator("summary").click();
    await expect(card).toHaveAttribute("open", "");
    await expect(card.locator("ul")).toBeVisible();

    await card.locator("summary").click();
    await expect(card).not.toHaveAttribute("open", "");

    // 查询结束不自动展开：终态仍保持用户最后选择的收起态
    await waitTaskComplete(page);
    await expect(card).not.toHaveAttribute("open", "");
  });

  test("新查询重新挂载，回到收起态", async ({ page }) => {
    await openChat(page);
    await sendQuery(page, "第一个问题");
    await waitTaskComplete(page);

    const card = taskCard(page);
    await card.locator("summary").click();
    await expect(card).toHaveAttribute("open", "");

    await sendQuery(page, "第二个问题");
    await expect(taskCard(page)).not.toHaveAttribute("open", "");
    await waitTaskComplete(page);
  });
});
