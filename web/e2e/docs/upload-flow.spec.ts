import { expect, test } from "@playwright/test";
import { openChat, openDocs } from "../helpers/app";
import { routeDocsList } from "../helpers/mock";

const DOC_ITEMS = [
  {
    doc_id: "201",
    title: "导入后的文档",
    type: "markdown" as const,
    pdf_link: null,
    chunks_link: "/api/files/chunks/imported.json",
  },
];

/**
 * P1：ZIP 上传链路（POST /api/upload → SSE fork → child-progress → 父任务完成）。
 * mock 固定回放：2 个 md 子任务，全部完成。
 */
test("ZIP 上传：fork 子任务 → 全部完成 → 列表自动刷新", async ({ page }) => {
  await routeDocsList(page, DOC_ITEMS);
  await openChat(page);
  await openDocs(page);

  // 切到「添加文档」视图并选择文件
  await page.getByRole("button", { name: "添加文档" }).click();
  await page.locator(".file-input").setInputFiles({
    name: "bundle.zip",
    mimeType: "application/zip",
    buffer: Buffer.from("PK-mock-zip"),
  });

  // 父任务卡片出现，最终完成
  const fileItem = page.locator(".file-item");
  await expect(fileItem).toHaveCount(1);
  await expect(fileItem).toHaveAttribute("data-state", "complete", {
    timeout: 15_000,
  });
  await expect(fileItem.locator(".file-name")).toHaveText("bundle.zip");
  await expect(fileItem.locator(".file-head .status-badge")).toHaveText(
    "已完成",
  );

  // fork 出 2 个子任务，全部完成
  await expect(fileItem.locator(".fork-title strong")).toHaveText("2");
  await expect(fileItem.locator(".fork-count")).toContainText("2 / 2 完成");
  await expect(fileItem.locator(".child-tree .status-badge")).toHaveText([
    "已完成",
    "已完成",
  ]);

  // 导入完成触发列表自动刷新（mock 列表 1 条）
  await expect(
    page.locator(".toast").filter({ hasText: "文档列表已自动刷新" }),
  ).toBeVisible();
});
