import { expect, test } from "@playwright/test";
import { openChat, openTokenPanel } from "../helpers/app";
import {
  installSession,
  makeTokenSnapshot,
  routeTokenUsage,
} from "../helpers/mock";

/** P2：健康检查失败 → 输入卡状态点显示"服务未连接" */
test("健康检查失败：输入卡显示服务未连接", async ({ page }) => {
  await page.route("**/api/health", (route) =>
    route.fulfill({ status: 500, json: { detail: "mock health down" } }),
  );
  await openChat(page);

  await expect(page.locator(".api-status")).toContainText("服务未连接");
  await expect(page.locator(".api-status .api-dot.bad")).toHaveCount(1);
});

/** P2：健康检查成功 → "服务已连接" */
test("健康检查成功：输入卡显示服务已连接", async ({ page }) => {
  await openChat(page);
  await expect(page.locator(".api-status")).toContainText("服务已连接");
});

/** P2：Token 面板三口径数字（会话总计 / 查询消耗切换） */
test("Token 面板：会话总计与查询消耗数字正确", async ({ page }) => {
  const sessionId = await installSession(page);
  await routeTokenUsage(page, makeTokenSnapshot(sessionId));
  await openChat(page);
  await openTokenPanel(page);

  const panel = page.locator(".token-panel");
  await expect(panel.locator(".tp-total-value .token-num")).toHaveText("1,234");

  await panel.getByRole("button", { name: "查询消耗" }).click();
  await expect(panel.locator(".tp-total-value .token-num")).toHaveText("321");

  await panel.getByRole("button", { name: "上传消耗" }).click();
  await expect(panel.locator(".tp-total-value .token-num")).toHaveText("913");
});

/** P2：Token 统计失败态（GET 500）→ 面板显示失败与重试 */
test("Token 统计失败：面板显示失败态与重试按钮", async ({ page }) => {
  await page.route("**/api/token-usage/*", (route) =>
    route.fulfill({ status: 500, json: { detail: "mock token down" } }),
  );
  await openChat(page);
  await openTokenPanel(page);

  const panel = page.locator(".token-panel");
  await expect(panel).toContainText("Token 统计加载失败");
  await expect(panel.getByRole("button", { name: "重试" })).toBeVisible();
});
