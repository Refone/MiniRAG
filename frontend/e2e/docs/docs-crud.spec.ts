import { expect, test } from "@playwright/test";
import { openChat, openDocs } from "../helpers/app";
import { routeDeleteDocFailure, routeDocsList } from "../helpers/mock";

const DOC_ITEMS = [
  {
    doc_id: "101",
    title: "万用表手册",
    type: "pdf" as const,
    pdf_link: "/api/files/origin/manual.pdf",
    chunks_link: "/api/files/chunks/manual.json",
  },
  {
    doc_id: "102",
    title: "安全操作规范",
    type: "markdown" as const,
    pdf_link: null,
    chunks_link: "/api/files/chunks/safety.json",
  },
];

/** P1：文档列表空态（mock 默认返回空列表） */
test("文档列表空态", async ({ page }) => {
  await openChat(page);
  await openDocs(page);

  await expect(page.locator(".doc-list-empty")).toContainText("文库为空");
  await expect(page.locator(".view-list .head-sub")).toContainText(
    "当前文档总数: 0",
  );
});

/** P1：列表渲染 + 删除成功（确认弹窗 → DELETE → 本地移除 + 成功 toast） */
test("文档列表渲染与删除成功", async ({ page }) => {
  await routeDocsList(page, DOC_ITEMS);
  await openChat(page);
  await openDocs(page);

  await expect(page.locator(".doc-item")).toHaveCount(2);
  await expect(page.locator(".view-list .head-sub")).toContainText(
    "当前文档总数: 2",
  );

  await page
    .locator(".doc-item")
    .filter({ hasText: "万用表手册" })
    .locator(".mini-btn.danger")
    .click();
  await expect(page.locator(".modal")).toContainText("删除文档？");

  await page.locator(".modal-actions .btn.primary").click();
  await expect(page.locator(".doc-item")).toHaveCount(1);
  await expect(page.locator(".toast.success")).toContainText(
    "已删除《万用表手册》",
  );
});

/** P1：删除失败分支（500 契约）→ 错误 toast，条目保留 */
test("删除失败：错误 toast 且条目保留", async ({ page }) => {
  await routeDocsList(page, DOC_ITEMS);
  await routeDeleteDocFailure(page);
  await openChat(page);
  await openDocs(page);

  await expect(page.locator(".doc-item")).toHaveCount(2);
  await page
    .locator(".doc-item")
    .filter({ hasText: "安全操作规范" })
    .locator(".mini-btn.danger")
    .click();
  await page.locator(".modal-actions .btn.primary").click();

  await expect(page.locator(".toast.error")).toContainText(
    "删除失败: 模拟删除失败",
  );
  await expect(page.locator(".doc-item")).toHaveCount(2);
});
