import { expect, test } from "@playwright/test";
import {
  openChat,
  openChatTab,
  openDocs,
  sendQuery,
  waitTaskComplete,
} from "../helpers/app";
import { installSession } from "../helpers/mock";

/**
 * P1：查询进行中切 Tab（Activity 保活 + SSE 上移 store）。
 * 契约：隐藏期间 EventSource 不断流，切回后回答继续增长、任务正常收尾。
 */
test("查询进行中切到文档页再切回，SSE 不断流", async ({ page }) => {
  await installSession(page);
  await openChat(page);
  await sendQuery(page, "万用表如何测量电压？");

  const answer = page.locator(".chat-page .msg.bot .markdown").last();
  await expect(answer).toContainText("万用表");

  // 隐藏对话页 700ms（mock 流式总长约 2.3s，仍在中途）
  await openDocs(page);
  await page.waitForTimeout(700);
  await openChatTab(page);

  // 切回后流式内容已经继续增长，并能正常收尾
  await expect(answer).toContainText("不要在带电电路上切换档位。");
  await waitTaskComplete(page);
});
