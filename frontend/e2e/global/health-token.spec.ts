import { expect, test } from "@playwright/test";
import { openChat, openTokenPanel } from "../helpers/app";
import {
  installSession,
  makeEmptyTokenSnapshot,
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

/**
 * Token 重置：确认 → DELETE 一次 → 面板归零 + toast，聊天历史不受影响。
 * 重置后的 GET 返回全 0，模拟后端记录已删除。
 */
test("Token 重置：确认后归零且保留聊天历史", async ({ page }) => {
  const sessionId = await installSession(page);
  let resetCount = 0;
  await page.route("**/api/token-usage/*", (route) => {
    if (route.request().method() === "DELETE") {
      resetCount += 1;
      return route.fulfill({ json: { status: "ok", session_id: sessionId } });
    }
    return route.fulfill({
      json:
        resetCount > 0
          ? makeEmptyTokenSnapshot(sessionId)
          : makeTokenSnapshot(sessionId),
    });
  });

  await openChat(page);
  await openTokenPanel(page);
  const panel = page.locator(".token-panel");
  await expect(panel.locator(".tp-total-value .token-num")).toHaveText("1,234");
  await expect(page.locator(".msg").first()).toBeVisible();

  await panel.getByRole("button", { name: "重置统计" }).click();
  const dialog = page.getByRole("dialog", { name: "重置 Token 统计？" });
  await expect(dialog).toBeVisible();
  await expect(dialog).toContainText("当前会话的 Token 使用情况将被重置");
  await expect(dialog).toContainText("历史会话不受影响");

  await dialog.getByRole("button", { name: "确认重置" }).click();
  await expect(dialog).toBeHidden();
  await expect(panel.locator(".tp-total-value .token-num")).toHaveText("0");
  await expect(
    page.locator(".toast").filter({ hasText: "Token 统计已重置" }),
  ).toBeVisible();
  expect(resetCount).toBe(1);
  // 聊天历史与 Token 统计彼此独立：重置统计不触发清空历史
  await expect(page.locator(".msg").first()).toBeVisible();
});

/** Token 重置：取消与 Esc 均不发起 DELETE，数字保持原值 */
test("Token 重置：取消或 Esc 不清零", async ({ page }) => {
  const sessionId = await installSession(page);
  let resetCount = 0;
  await page.route("**/api/token-usage/*", (route) => {
    if (route.request().method() === "DELETE") {
      resetCount += 1;
      return route.fulfill({ json: { status: "ok", session_id: sessionId } });
    }
    return route.fulfill({ json: makeTokenSnapshot(sessionId) });
  });

  await openChat(page);
  await openTokenPanel(page);
  const panel = page.locator(".token-panel");
  const resetButton = panel.getByRole("button", { name: "重置统计" });
  const dialog = page.getByRole("dialog", { name: "重置 Token 统计？" });

  await resetButton.click();
  await expect(dialog).toBeVisible();
  await dialog.getByRole("button", { name: "取消" }).click();
  await expect(dialog).toBeHidden();
  await expect(panel.locator(".tp-total-value .token-num")).toHaveText("1,234");

  await resetButton.click();
  await expect(dialog).toBeVisible();
  await page.keyboard.press("Escape");
  await expect(dialog).toBeHidden();
  await expect(panel.locator(".tp-total-value .token-num")).toHaveText("1,234");
  expect(resetCount).toBe(0);
});
