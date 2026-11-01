/**
 * E2E 契约 Mock API Server（只给 Playwright 用，不参与构建）
 *
 * 契约来源（后端改动时同步本文件）：
 * - 路由与响应结构：src/api/main.py
 * - SSE 事件名与帧形状：web/src/lib/sse.ts
 *
 * 设计要点：
 * - 原生 node:http，零依赖；
 * - 前端经 VITE_API_BASE 直连（5174 → 4000 跨源），所有响应带 CORS 头；
 * - 查询 SSE 每次连接都重放同一段事件序列，测试靠断言等待，不靠 sleep 对齐。
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

/**
 * 查询 SSE 事件序列（节奏刻意放慢：给测试留出"流式中途滚轮上翻"的操作窗口）。
 * 事件顺序与真实后端一致：progress(pending) → progress(processing) ×n → delta ×n
 * → final → usage → __close__
 */
const QUERY_FRAMES = [
  {
    event: "progress",
    data: { status: "pending", done_list: [], running_list: [] },
  },
  {
    event: "progress",
    data: {
      status: "processing",
      done_list: ["意图识别"],
      running_list: ["知识库检索"],
    },
  },
  {
    event: "progress",
    data: {
      status: "processing",
      done_list: ["意图识别", "知识库检索"],
      running_list: ["生成回答"],
    },
    delayMs: 60,
  },
  ...DELTAS.map((delta) => ({
    event: "delta",
    data: { delta },
    delayMs: 220,
  })),
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
      return sendJson(res, 200, {
        status: "ok",
        msg: "查询已异步启动",
        session_id: body.session_id,
      });
    }
    if (req.method === "GET" && path.startsWith("/api/query/sse/")) {
      await writeSse(res, QUERY_FRAMES);
      return;
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
