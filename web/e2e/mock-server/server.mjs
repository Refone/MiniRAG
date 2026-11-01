/**
 * E2E 契约 Mock API Server（只给 Playwright 用，不参与构建）
 *
 * 契约来源（后端改动时同步本文件）：
 * - 路由与响应结构：src/api/main.py
 * - SSE 事件名与帧形状：web/src/lib/sse.ts
 *
 * 设计要点：
 * - 原生 node:http，零依赖；前端经 VITE_API_BASE 直连（跨源，所有响应带 CORS 头）；
 * - REST 端点返回稳定 fixture；单条用例需要特殊返回值时用 page.route 拦截覆盖，
 *   避免多 worker 共享 mock 状态互相污染；
 * - EventSource 无法被 page.route 拦截，所以查询 / 上传的 SSE 必须由本服务提供；
 * - 查询 SSE 支持按会话切换场景（POST /__mock/scenario），用于错误 / 断连用例；
 * - POST /api/query 的请求体会被记录（GET /__mock/last-query?sessionId=），
 *   供用例断言前端发出的载荷。
 */
import { createServer } from "node:http";
import { readFileSync } from "node:fs";
import { dirname, join } from "node:path";
import { fileURLToPath } from "node:url";
import { writeSse } from "./sse.mjs";

const HERE = dirname(fileURLToPath(import.meta.url));
const PORT = Number(process.env.MOCK_PORT ?? 4000);

const readFixture = (name) =>
  JSON.parse(readFileSync(join(HERE, "fixtures", name), "utf8"));

const HISTORY = readFixture("history.json");
const DOCS = readFixture("docs.json");
const TOKEN_USAGE = readFixture("token-usage.json");

/** 与流式 delta 拼接结果一致，避免 final 覆盖时出现文本跳变 */
const DELTAS = [
  "万用表测量电压：",
  "先把档位拨到",
  "直流电压档，",
  "黑表笔接 COM，",
  "红表笔接被测点，",
  "读数稳定后",
  "再记录数值。",
  "注意：",
  "不要在带电电路上切换档位。",
];
const ANSWER = DELTAS.join("");

const PROGRESS_PENDING = {
  event: "progress",
  data: { status: "pending", done_list: [], running_list: [] },
};
const PROGRESS_RUNNING = {
  event: "progress",
  data: {
    status: "processing",
    done_list: ["意图识别"],
    running_list: ["知识库检索"],
  },
};

/**
 * 查询 SSE 事件序列（pace 刻意放慢：给测试留出"流式中途滚轮上翻 / 切 Tab"的窗口）。
 * 正常顺序与真实后端一致：progress → delta ×n → final → usage → __close__
 */
const QUERY_FRAMES = [
  PROGRESS_PENDING,
  PROGRESS_RUNNING,
  {
    event: "progress",
    data: {
      status: "processing",
      done_list: ["意图识别", "知识库检索"],
      running_list: ["生成回答"],
    },
    delayMs: 60,
  },
  ...DELTAS.map((delta) => ({ event: "delta", data: { delta }, delayMs: 220 })),
  {
    event: "final",
    data: {
      status: "complete",
      answer: ANSWER,
      done_list: ["意图识别", "知识库检索", "生成回答"],
      running_list: [],
    },
    delayMs: 80,
  },
  { event: "usage", data: TOKEN_USAGE, delayMs: 20 },
  { event: "__close__", data: {} },
];

/** 服务端业务错误：event: error 带 data，随后仍发 __close__（与后端约定一致） */
const QUERY_ERROR_FRAMES = [
  PROGRESS_PENDING,
  PROGRESS_RUNNING,
  {
    event: "error",
    data: { error: "检索超时，请重试" },
    delayMs: 120,
  },
  { event: "__close__", data: {} },
];

/** 连接中断：只推一帧进度后直接掐断，不发 __close__（前端走原生 error 分支） */
const QUERY_DISCONNECT_FRAMES = [PROGRESS_PENDING, PROGRESS_RUNNING];

const QUERY_SCENARIOS = {
  default: () => ({ frames: QUERY_FRAMES, closeMode: "end" }),
  "query-error": () => ({ frames: QUERY_ERROR_FRAMES, closeMode: "end" }),
  "query-disconnect": () => ({
    frames: QUERY_DISCONNECT_FRAMES,
    closeMode: "destroy",
  }),
};

/** ZIP 上传链路：父任务 + fork 两个 md 子任务，全部完成 */
const UPLOAD_FRAMES = [
  { event: "progress", data: { status: "pending", done_list: [], running_list: [] } },
  {
    event: "progress",
    data: { status: "processing", done_list: [], running_list: ["解析文档"] },
    delayMs: 80,
  },
  {
    event: "fork",
    data: {
      parent_task_id: "mock-task",
      total: 2,
      children: [
        { child_id: "mock-child-1", title: "安装说明", path: "docs/install.md", index: 0 },
        { child_id: "mock-child-2", title: "使用说明", path: "docs/usage.md", index: 1 },
      ],
    },
    delayMs: 60,
  },
  {
    event: "child-progress",
    data: {
      child_id: "mock-child-1",
      status: "processing",
      done_list: [],
      running_list: ["解析"],
      failed_list: [],
    },
    delayMs: 60,
  },
  {
    event: "child-progress",
    data: {
      child_id: "mock-child-1",
      status: "complete",
      done_list: ["解析", "切块"],
      running_list: [],
      failed_list: [],
    },
    delayMs: 80,
  },
  {
    event: "child-progress",
    data: {
      child_id: "mock-child-2",
      status: "processing",
      done_list: [],
      running_list: ["解析"],
      failed_list: [],
    },
    delayMs: 60,
  },
  {
    event: "child-progress",
    data: {
      child_id: "mock-child-2",
      status: "complete",
      done_list: ["解析", "切块"],
      running_list: [],
      failed_list: [],
    },
    delayMs: 80,
  },
  {
    event: "progress",
    data: {
      status: "complete",
      done_list: ["解析文档", "向量入库"],
      running_list: [],
      failed_list: [],
    },
    delayMs: 60,
  },
  { event: "usage", data: TOKEN_USAGE, delayMs: 10 },
  { event: "__close__", data: {} },
];

/** sessionId → 查询 SSE 场景（默认 default） */
const scenarios = new Map();
/** sessionId → POST /api/query 最近一次请求体 */
const lastQueryBySession = new Map();

function sendJson(res, status, body) {
  const text = JSON.stringify(body);
  res.writeHead(status, {
    "Content-Type": "application/json; charset=utf-8",
    "Content-Length": Buffer.byteLength(text),
  });
  res.end(text);
}

function readJson(req) {
  return new Promise((resolve, reject) => {
    let raw = "";
    req.on("data", (chunk) => {
      raw += chunk;
    });
    req.on("end", () => {
      try {
        resolve(raw ? JSON.parse(raw) : {});
      } catch (err) {
        reject(err);
      }
    });
    req.on("error", reject);
  });
}

/** 上传请求体是 multipart，内容不需要解析，读干净即可 */
function drain(req) {
  return new Promise((resolve) => {
    req.on("data", () => {});
    req.on("end", resolve);
    req.on("error", resolve);
  });
}

const server = createServer(async (req, res) => {
  const url = new URL(req.url ?? "/", `http://127.0.0.1:${PORT}`);
  const path = url.pathname;

  // 前端 5174 → mock 4000 是跨源，所有响应（含 SSE）都要带 CORS 头
  res.setHeader("Access-Control-Allow-Origin", "*");
  res.setHeader("Access-Control-Allow-Methods", "GET,POST,DELETE,OPTIONS");
  res.setHeader("Access-Control-Allow-Headers", "Content-Type");

  if (req.method === "OPTIONS") {
    res.writeHead(204);
    res.end();
    return;
  }

  try {
    /* ---- mock 控制面（E2E 专用，产品代码不会调用） ---- */
    if (req.method === "POST" && path === "/__mock/scenario") {
      const body = await readJson(req);
      if (!body.sessionId || !body.scenario) {
        return sendJson(res, 400, { detail: "需要 sessionId 与 scenario" });
      }
      if (!QUERY_SCENARIOS[body.scenario]) {
        return sendJson(res, 400, {
          detail: `未知场景: ${body.scenario}`,
        });
      }
      scenarios.set(body.sessionId, body.scenario);
      return sendJson(res, 200, { ok: true, scenario: body.scenario });
    }
    if (req.method === "GET" && path === "/__mock/last-query") {
      const sessionId = url.searchParams.get("sessionId") ?? "";
      return sendJson(res, 200, lastQueryBySession.get(sessionId) ?? null);
    }

    /* ---- 业务端点 ---- */
    if (req.method === "GET" && path === "/api/health") {
      return sendJson(res, 200, { status: "ok", version: "mock" });
    }
    if (req.method === "GET" && path.startsWith("/api/history/")) {
      return sendJson(res, 200, { status: "ok", history: HISTORY });
    }
    if (req.method === "GET" && path === "/api/docs") {
      return sendJson(res, 200, DOCS);
    }
    if (req.method === "GET" && path.startsWith("/api/token-usage/")) {
      return sendJson(res, 200, TOKEN_USAGE);
    }
    if (req.method === "POST" && path === "/api/query") {
      const body = await readJson(req);
      if (!body.session_id) {
        return sendJson(res, 400, { detail: "缺少会话标识 session_id" });
      }
      lastQueryBySession.set(body.session_id, body);
      return sendJson(res, 200, {
        status: "ok",
        msg: "查询已异步启动",
        session_id: body.session_id,
      });
    }
    if (req.method === "GET" && path.startsWith("/api/query/sse/")) {
      const sessionId = decodeURIComponent(path.slice("/api/query/sse/".length));
      const scenario = scenarios.get(sessionId) ?? "default";
      const { frames, closeMode } = QUERY_SCENARIOS[scenario]();
      await writeSse(res, frames, { closeMode });
      return;
    }
    if (req.method === "POST" && path === "/api/upload") {
      await drain(req);
      return sendJson(res, 202, { task_id: "mock-task", status: "pending" });
    }
    if (req.method === "GET" && path.startsWith("/api/upload/sse/")) {
      await writeSse(res, UPLOAD_FRAMES);
      return;
    }
    if (req.method === "DELETE" && path.startsWith("/api/docs/")) {
      return sendJson(res, 200, { success: true });
    }
    if (req.method === "GET" && path.startsWith("/api/docs/")) {
      return sendJson(res, 404, { detail: "mock: 文档详情未实现" });
    }
    return sendJson(res, 404, {
      detail: `mock 未实现的路由: ${req.method} ${path}`,
    });
  } catch (err) {
    return sendJson(res, 500, {
      detail: `mock 内部错误: ${err instanceof Error ? err.message : String(err)}`,
    });
  }
});

server.listen(PORT, "127.0.0.1", () => {
  console.log(`[mock] 契约 Mock API 已启动: http://127.0.0.1:${PORT}`);
});
