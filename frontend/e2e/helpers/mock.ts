import { expect, type Page } from "@playwright/test";

/** mock API 端口/来源（与 playwright.config.ts、mock-server/server.mjs 一致） */
export const MOCK_ORIGIN = "http://127.0.0.1:4000";

/** 生成测试专属会话 id（对应前端 localStorage kb_session_id） */
export function makeSessionId(): string {
  return `sess-e2e-${Math.random().toString(36).slice(2, 10)}`;
}

/**
 * 页面加载前写入会话 id。
 * 查询 SSE 场景按会话区分，避免并行用例互相污染 mock 状态。
 */
export async function installSession(
  page: Page,
  sessionId = makeSessionId(),
): Promise<string> {
  await page.addInitScript((id) => {
    localStorage.setItem("kb_session_id", id);
  }, sessionId);
  return sessionId;
}

/** 设置该会话的查询 SSE 场景：default / query-error / query-disconnect */
export async function setQueryScenario(
  page: Page,
  sessionId: string,
  scenario: string,
): Promise<void> {
  const res = await page.request.post(`${MOCK_ORIGIN}/__mock/scenario`, {
    data: { sessionId, scenario },
  });
  expect(res.ok(), `设置 mock 场景失败: ${scenario}`).toBeTruthy();
}

/** 读取 mock 记录的前端查询载荷（POST /api/query 请求体） */
export async function readLastQuery(
  page: Page,
  sessionId: string,
): Promise<Record<string, unknown> | null> {
  const res = await page.request.get(
    `${MOCK_ORIGIN}/__mock/last-query?sessionId=${encodeURIComponent(sessionId)}`,
  );
  return (await res.json()) as Record<string, unknown> | null;
}

/** 文档列表条目（GET /api/docs 单条，与 @/types/docs DocsListItem 一致） */
export interface DocsListItemFixture {
  doc_id: string;
  title: string;
  type: "pdf" | "markdown";
  pdf_link: string | null;
  chunks_link: string;
}

/** 用路由拦截覆盖文档列表（REST 可拦截，避免改 mock 的全局 fixture） */
export async function routeDocsList(
  page: Page,
  items: DocsListItemFixture[],
): Promise<void> {
  await page.route("**/api/docs?*", (route) =>
    route.fulfill({ json: { total: items.length, list: items } }),
  );
}

/** Token 快照（GET /api/token-usage 响应，与后端 TokenUsageSnapshot 一致） */
export interface TokenUsageFixture {
  session_id: string;
  user_ip: string;
  updated_at: number | null;
  llm_tokens: number;
  vlm_tokens: number;
  embedding_tokens: number;
  reranker_tokens: number;
  total_tokens: number;
  query: {
    llm_tokens: number;
    vlm_tokens: number;
    embedding_tokens: number;
    reranker_tokens: number;
    total_tokens: number;
  };
  upload: {
    llm_tokens: number;
    vlm_tokens: number;
    embedding_tokens: number;
    reranker_tokens: number;
    total_tokens: number;
  };
}

/** 四模型总和 1234，其中查询 321 / 上传 913（口径切换断言用） */
export function makeTokenSnapshot(sessionId: string): TokenUsageFixture {
  return {
    session_id: sessionId,
    user_ip: "127.0.0.1",
    updated_at: 1767225600000,
    llm_tokens: 1000,
    vlm_tokens: 100,
    embedding_tokens: 100,
    reranker_tokens: 34,
    total_tokens: 1234,
    query: {
      llm_tokens: 300,
      vlm_tokens: 0,
      embedding_tokens: 21,
      reranker_tokens: 0,
      total_tokens: 321,
    },
    upload: {
      llm_tokens: 700,
      vlm_tokens: 100,
      embedding_tokens: 79,
      reranker_tokens: 34,
      total_tokens: 913,
    },
  };
}

/** 全 0 的 Token 快照（重置后的 GET 响应，updated_at 为 null） */
export function makeEmptyTokenSnapshot(sessionId: string): TokenUsageFixture {
  const empty = () => ({
    llm_tokens: 0,
    vlm_tokens: 0,
    embedding_tokens: 0,
    reranker_tokens: 0,
    total_tokens: 0,
  });
  return {
    session_id: sessionId,
    user_ip: "",
    updated_at: null,
    ...empty(),
    query: empty(),
    upload: empty(),
  };
}

/** 用路由拦截覆盖 Token 统计响应 */
export async function routeTokenUsage(
  page: Page,
  snapshot: TokenUsageFixture,
): Promise<void> {
  await page.route("**/api/token-usage/*", (route) =>
    route.fulfill({ json: snapshot }),
  );
}

/** 用路由拦截模拟删除接口 500（其余 /api/docs/* 请求放行） */
export async function routeDeleteDocFailure(page: Page): Promise<void> {
  await page.route("**/api/docs/*", (route) => {
    if (route.request().method() === "DELETE") {
      return route.fulfill({
        status: 500,
        json: { success: false, detail: "模拟删除失败" },
      });
    }
    return route.fallback();
  });
}
