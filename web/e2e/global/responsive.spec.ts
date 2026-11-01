import { expect, test } from "@playwright/test";
import { openChat, sendQuery } from "../helpers/app";
import { installSession } from "../helpers/mock";

/**
 * P2：移动端响应式（390×844，mobile-chromium project）。
 * 契约：无横向溢出；输入卡与任务卡片都在视口内（.composer-wrap 左右 10px 内缩）。
 */
test("@mobile 移动端布局：无横向溢出，输入卡与任务卡片在视口内", async ({
  page,
}) => {
  await installSession(page);
  await openChat(page);

  const viewportWidth = page.viewportSize()?.width ?? 390;
  expect(
    await page.evaluate(
      () => document.documentElement.scrollWidth - window.innerWidth,
    ),
  ).toBeLessThanOrEqual(0);

  const composer = await page.locator(".chat-page .composer").boundingBox();
  expect(composer).not.toBeNull();
  if (!composer) throw new Error("找不到输入卡");
  expect(composer.x).toBeGreaterThanOrEqual(0);
  expect(composer.x + composer.width).toBeLessThanOrEqual(viewportWidth + 1);

  // 发送查询后，任务卡片同样不超出视口
  await sendQuery(page, "万用表如何测量电压？");
  const card = await page.locator(".chat-page .task-bar").boundingBox();
  expect(card).not.toBeNull();
  if (!card) throw new Error("找不到任务卡片");
  expect(card.x).toBeGreaterThanOrEqual(0);
  expect(card.x + card.width).toBeLessThanOrEqual(viewportWidth + 1);
});
