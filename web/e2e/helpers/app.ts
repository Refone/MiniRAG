import { expect, type Page } from "@playwright/test";

/** 查询任务卡片（输入框上方唯一的任务状态卡） */
export const taskCard = (page: Page) =>
  page.locator(".chat-page .task-bar details.progress");

/** 回到底部按钮（未贴底时才有 visible 类） */
export const scrollToBottom = (page: Page) =>
  page.locator(".chat-page .scroll-to-bottom");

/** 打开对话页，等应用外壳与输入卡就绪（--composer-h 写回后布局才算稳定） */
export async function openChat(page: Page): Promise<void> {
  await page.goto("/");
  await expect(page.locator(".app-shell")).toBeVisible();
  await expect(page.locator(".chat-page .composer textarea")).toBeVisible();
  await page.waitForFunction(() => {
    const pageEl = document.querySelector<HTMLElement>(".chat-page");
    return !!pageEl && pageEl.style.getPropertyValue("--composer-h") !== "";
  });
}

/** 发送一条查询（Enter 触发，与用户操作一致） */
export async function sendQuery(page: Page, text: string): Promise<void> {
  const input = page.locator(".chat-page .composer textarea");
  await input.fill(text);
  await input.press("Enter");
  await expect(taskCard(page)).toBeVisible();
}

/** 等查询任务到终态：收到 __close__ 后摘要显示"已完成" */
export async function waitTaskComplete(page: Page): Promise<void> {
  await expect(taskCard(page).locator(".progress-count")).toHaveText(
    "（已完成）",
  );
}

/** 切到文档管理页（App 内 Tab 切换，不是路由跳转） */
export async function openDocs(page: Page): Promise<void> {
  await page.getByRole("button", { name: "文档管理" }).click();
  await expect(page.locator(".docs-page")).toBeVisible();
}

/** 切回对话页 */
export async function openChatTab(page: Page): Promise<void> {
  await page.getByRole("button", { name: "对话" }).click();
  await expect(page.locator(".chat-page")).toBeVisible();
}

/** 打开 NavBar 的 Token 明细面板 */
export async function openTokenPanel(page: Page): Promise<void> {
  await page.locator(".token-chip").click();
  await expect(page.locator(".token-panel")).toBeVisible();
}
