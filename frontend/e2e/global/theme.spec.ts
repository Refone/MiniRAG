import { expect, test } from "@playwright/test";
import { openChat } from "../helpers/app";

/**
 * P2：明暗主题切换。
 * 契约：html[data-theme] 跟随 preferenceStore；切换按钮 aria-label 同步；
 * 全程无页面级异常（pageerror）。
 */
test("主题切换：data-theme 跟随且无页面异常", async ({ page }) => {
  const pageErrors: string[] = [];
  page.on("pageerror", (err) => pageErrors.push(err.message));

  await openChat(page);
  await expect(page.locator("html")).toHaveAttribute("data-theme", "light");

  await page.locator(".theme-toggle").click();
  await expect(page.locator("html")).toHaveAttribute("data-theme", "dark");
  await expect(page.locator(".theme-toggle")).toHaveAttribute(
    "aria-label",
    "切换到浅色模式",
  );

  await page.locator(".theme-toggle").click();
  await expect(page.locator("html")).toHaveAttribute("data-theme", "light");
  expect(pageErrors).toEqual([]);
});
