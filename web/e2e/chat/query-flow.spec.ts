import { expect, test } from "@playwright/test";
import { openChat, sendQuery, taskCard, waitTaskComplete } from "../helpers/app";
import { installSession, readLastQuery } from "../helpers/mock";

/**
 * P1：完整查询链路（前端 → mock 契约）。
 * 断言：POST /api/query 载荷 → SSE 进度 / 流式回答 / 终态 → 关闭卡片。
 */
test("查询链路：载荷 → 进度 → 流式回答 → 终态 → 关闭卡片", async ({
  page,
}) => {
  const sessionId = await installSession(page);
  await openChat(page);

  const queryRequest = page.waitForRequest(
    (req) => req.url().includes("/api/query") && req.method() === "POST",
  );
  await sendQuery(page, "万用表如何测量电压？");
  const request = await queryRequest;
  expect(request.postDataJSON()).toMatchObject({
    query: "万用表如何测量电压？",
    session_id: sessionId,
    enable_web_search: true,
    enable_hyde: true,
  });

  // mock 侧同样收到同一份载荷（契约双保险）
  expect(await readLastQuery(page, sessionId)).toMatchObject({
    session_id: sessionId,
    query: "万用表如何测量电压？",
  });

  // 流式回答完整落地
  const answer = page.locator(".chat-page .msg.bot .markdown").last();
  await expect(answer).toContainText("不要在带电电路上切换档位。");

  // 终态：摘要"已完成"，关闭按钮出现，发送按钮恢复可用
  await waitTaskComplete(page);
  await expect(page.locator(".task-close")).toBeVisible();
  await expect(page.locator(".composer .send")).toBeEnabled();

  // 展开卡片：三次进度阶段的 done 行都在
  await taskCard(page).locator("summary").click();
  const lines = taskCard(page).locator("ul");
  await expect(lines).toContainText("意图识别");
  await expect(lines).toContainText("知识库检索");
  await expect(lines).toContainText("生成回答");

  // 关闭终态卡片
  await page.locator(".task-close").click();
  await expect(taskCard(page)).toHaveCount(0);
});
