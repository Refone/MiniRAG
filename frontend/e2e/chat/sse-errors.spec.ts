import { expect, test } from "@playwright/test";
import { openChat, sendQuery, taskCard } from "../helpers/app";
import { installSession, setQueryScenario } from "../helpers/mock";

/** 取最近一条 bot 回答的正文容器 */
const latestAnswer = (page: import("@playwright/test").Page) =>
  page.locator(".chat-page .msg.bot .markdown").last();

/**
 * P1：SSE 错误两条路径（契约来自 frontend/src/lib/sse.ts）。
 * - 服务端 event: error（带 data）：错误文案落到回答，随后 __close__ 正常收尾；
 * - 原生连接错误（无 data）：前端主动关流，任务进 failed 终态。
 */
test("服务端 error 事件：错误文案落到回答，流程正常收尾", async ({ page }) => {
  const sessionId = await installSession(page);
  await setQueryScenario(page, sessionId, "query-error");
  await openChat(page);

  await sendQuery(page, "触发服务端错误");
  await expect(latestAnswer(page)).toContainText("（错误：检索超时，请重试）");

  // 服务端错误后仍发 __close__：任务按"已完成"收尾，发送按钮释放
  await expect(taskCard(page).locator(".progress-count")).toHaveText(
    "（已完成）",
  );
  await expect(page.locator(".composer .send")).toBeEnabled();
});

test("连接中断：不发 __close__ 直接掐断 → 失败终态 + 可关闭卡片", async ({
  page,
}) => {
  const sessionId = await installSession(page);
  await setQueryScenario(page, sessionId, "query-disconnect");
  await openChat(page);

  await sendQuery(page, "触发连接中断");
  await expect(latestAnswer(page)).toContainText("SSE 连接中断/失败");
  await expect(taskCard(page).locator(".progress-count")).toHaveText(
    "（失败）",
  );
  await expect(page.locator(".task-close")).toBeVisible();
  await expect(page.locator(".composer .send")).toBeEnabled();
});
