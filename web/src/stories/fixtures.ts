/**
 * Storybook 故事共用样例数据。
 *
 * 只被 `*.stories.tsx` 引用：`main.tsx` 从不 import 本文件，
 * 因此不会进入生产构建；但它在 `src/` 下，会被 `tsc --noEmit` 一起校验。
 */
import type { ProgressView } from "@/types/app";
import type { ChatMessage, QueryTaskView } from "@/types/chat";
import type {
  DocsChunkItem,
  DocsDetailResponse,
  DocsListItem,
  ImportChildTask,
  ImportFile,
} from "@/types/docs";
import type { TokenUsageSnapshot } from "@/types/tokenUsage";

/** 对话消息：user / 回答 / typing / 流式 / 失败 / 空答案 */
export const chatMessages: Record<string, ChatMessage> = {
  user: {
    id: "msg-user",
    role: "user",
    text: "MiniRAG 的切块策略是什么？",
    time: "10:24",
    typing: false,
    streaming: false,
    error: null,
  },
  botAnswer: {
    id: "msg-bot",
    role: "bot",
    text: [
      "### 切块策略",
      "",
      "MiniRAG 按 Markdown 标题层级切分，超长段落再做二次合并：",
      "",
      "| 层级 | 作用 |",
      "| --- | --- |",
      "| H1 / H2 | 章节边界 |",
      "| H3 | 子主题 |",
      "",
      "- 表格、代码块整块保留",
      "- 每块写入 Milvus 并保留标题栈",
    ].join("\n"),
    time: "10:24",
    hint: "来自本地知识库 · 3 个来源",
    typing: false,
    streaming: false,
    error: null,
  },
  botTyping: {
    id: "msg-typing",
    role: "bot",
    text: "",
    time: "10:24",
    typing: true,
    streaming: false,
    error: null,
  },
  botStreaming: {
    id: "msg-streaming",
    role: "bot",
    text: "正在生成切块示意图：\n\n![切块示意](http://localhost:8000/api/image/chunk-flow",
    time: "10:24",
    typing: false,
    streaming: true,
    error: null,
  },
  botError: {
    id: "msg-error",
    role: "bot",
    text: "",
    time: "10:24",
    typing: false,
    streaming: false,
    error: "查询服务暂不可用（HTTP 503），请稍后重试。",
  },
  botEmpty: {
    id: "msg-empty",
    role: "bot",
    text: "",
    time: "10:24",
    typing: false,
    streaming: false,
    error: null,
  },
};

/** 查询进度：运行中 / 完成 / 失败 */
export const queryProgress: Record<"running" | "complete" | "failed", ProgressView> = {
  running: {
    done: ["意图识别", "知识库检索"],
    running: ["结果重排"],
    status: "processing",
  },
  complete: {
    done: ["意图识别", "知识库检索", "结果重排", "生成回答"],
    running: [],
    status: "complete",
  },
  failed: {
    done: ["意图识别"],
    running: [],
    status: "failed",
  },
};

export const queryTask: QueryTaskView = {
  id: "task-query-1",
  progress: queryProgress.running,
};

/** 文档切块（title_stack 里允许 null，等价于 markdown 里的空标题行） */
export const chunks: DocsChunkItem[] = [
  {
    content: "# MiniRAG 使用手册\n\n本文档说明本地知识库的导入、切块与检索流程。",
    level: 1,
    title_stack: ["MiniRAG 使用手册"],
  },
  {
    content:
      "## 导入流程\n\n1. 在「文档管理」页点击「添加文档」\n2. 选择 PDF / Markdown / ZIP\n3. 等待任务卡片中的阶段进度完成",
    level: 2,
    title_stack: ["MiniRAG 使用手册", "导入流程"],
  },
  {
    content:
      "### 切块策略\n\n- 按标题层级切分\n- 超长段落二次合并\n- 表格、代码块整块保留\n- 每块保留 `title_stack`，检索结果可回溯章节",
    level: 3,
    title_stack: ["MiniRAG 使用手册", "导入流程", "切块策略"],
  },
  {
    content:
      "## 检索流程\n\n查询经 embedding 后在 Milvus 中召回 Top-K，再由重排模型过滤，最后交给大模型生成回答。",
    level: 2,
    title_stack: ["MiniRAG 使用手册", "检索流程"],
  },
];

/** 文档详情（预览面板三种模式的输入） */
export const docsDetail: DocsDetailResponse = {
  title: "MiniRAG 使用手册",
  markdown_text: [
    "# MiniRAG 使用手册",
    "",
    "本地知识库的导入与检索，全部在浏览器里完成。",
    "",
    "## 导入流程",
    "",
    "| 格式 | 说明 |",
    "| --- | --- |",
    "| PDF | 服务端解析后切块 |",
    "| Markdown | 按标题层级切块 |",
    "| ZIP | 包内每个 md 成为独立文档 |",
    "",
    "> 导入进度通过 SSE 实时推进。",
  ].join("\n"),
  chunks,
  keywords: "RAG, 向量检索，切块策略，Milvus",
  abstract:
    "MiniRAG 是一个本地知识库问答系统：导入文档后自动切块并写入向量库，对话时先检索、再生成带引用的回答。",
};

/** 文档列表（PDF 带 pdf_link，Markdown 为 null） */
export const docsList: DocsListItem[] = [
  {
    doc_id: "doc_1001",
    title: "MiniRAG 使用手册.pdf",
    type: "pdf",
    pdf_link: "/api/docs/doc_1001/pdf",
    chunks_link: "/api/docs/doc_1001/chunks",
  },
  {
    doc_id: "doc_1002",
    title: "检索参数调优.md",
    type: "markdown",
    pdf_link: null,
    chunks_link: "/api/docs/doc_1002/chunks",
  },
  {
    doc_id: "doc_1003",
    title: "部署与运维.pdf",
    type: "pdf",
    pdf_link: "/api/docs/doc_1003/pdf",
    chunks_link: "/api/docs/doc_1003/chunks",
  },
];

const now = Date.now();

/** 单文件导入任务（处理中） */
export const importFile: ImportFile = {
  id: "task-file-1",
  name: "MiniRAG 使用手册.pdf",
  sizeKB: "2.4 MB",
  status: "processing",
  startedAt: now - 3200,
  done: ["解析 PDF", "OCR 识别"],
  failed: [],
  running: ["向量化切块"],
  forked: false,
  children: [],
};

/** 单文件导入任务（已完成） */
export const importFileComplete: ImportFile = {
  ...importFile,
  id: "task-file-2",
  status: "complete",
  startedAt: now - 12_000,
  done: ["解析 PDF", "OCR 识别", "向量化切块", "写入向量库"],
  running: [],
};

/** 单文件导入任务（失败） */
export const importFileFailed: ImportFile = {
  ...importFile,
  id: "task-file-3",
  status: "failed",
  startedAt: now - 8000,
  done: ["解析 PDF"],
  failed: ["OCR 识别"],
  running: [],
};

/** ZIP 子任务样例 */
export const importChild: ImportChildTask = {
  id: "child-1",
  title: "01-安装",
  path: "手册/01-安装.md",
  index: 0,
  status: "processing",
  startedAt: now - 4200,
  stoppedAt: null,
  done: ["解析 Markdown", "切块"],
  running: ["写入向量库"],
  failed: [],
  error: "",
};

/** ZIP 导入任务：父卡 + 子任务树 */
export const importZipFile: ImportFile = {
  id: "task-zip-1",
  name: "MiniRAG 文档合集.zip",
  sizeKB: "8.1 MB",
  status: "processing",
  startedAt: now - 9000,
  done: ["解压 ZIP"],
  failed: [],
  running: [],
  forked: true,
  children: [
    {
      ...importChild,
      id: "child-1",
      status: "complete",
      stoppedAt: now - 5000,
      done: ["解析 Markdown", "切块", "写入向量库"],
      running: [],
    },
    {
      ...importChild,
      id: "child-2",
      title: "02-切块",
      path: "手册/02-切块.md",
      index: 1,
    },
    {
      ...importChild,
      id: "child-3",
      title: "03-检索",
      path: "手册/03-检索.md",
      index: 2,
      status: "pending",
      startedAt: null,
      done: [],
      running: [],
    },
    {
      ...importChild,
      id: "child-4",
      title: "04-调优",
      path: "手册/04-调优.md",
      index: 3,
      status: "failed",
      startedAt: now - 6000,
      stoppedAt: now - 3000,
      done: ["解析 Markdown"],
      running: [],
      failed: ["切块"],
      error: "模型调用超时",
    },
    {
      ...importChild,
      id: "child-5",
      title: "05-部署",
      path: "手册/05-部署.md",
      index: 4,
      status: "interrupted",
      startedAt: now - 7000,
      stoppedAt: null,
      done: [],
      running: [],
    },
  ],
};

/** Token 统计快照：查询 + 上传后的会话总计（面板三口径可切换） */
export const mockTokenUsage: TokenUsageSnapshot = {
  session_id: "sess-demo-token",
  user_ip: "127.0.0.1",
  updated_at: Math.floor(Date.now() / 1000),
  llm_tokens: 1106,
  vlm_tokens: 1264,
  embedding_tokens: 1795,
  reranker_tokens: 350,
  total_tokens: 4515,
  query: {
    llm_tokens: 620,
    vlm_tokens: 0,
    embedding_tokens: 905,
    reranker_tokens: 350,
    total_tokens: 1875,
  },
  upload: {
    llm_tokens: 486,
    vlm_tokens: 1264,
    embedding_tokens: 890,
    reranker_tokens: 0,
    total_tokens: 2640,
  },
};

/** Token 统计快照：空统计态（全 0，updated_at 为 null） */
export const emptyTokenUsage: TokenUsageSnapshot = {
  session_id: "sess-demo-empty",
  user_ip: "127.0.0.1",
  updated_at: null,
  llm_tokens: 0,
  vlm_tokens: 0,
  embedding_tokens: 0,
  reranker_tokens: 0,
  total_tokens: 0,
  query: {
    llm_tokens: 0,
    vlm_tokens: 0,
    embedding_tokens: 0,
    reranker_tokens: 0,
    total_tokens: 0,
  },
  upload: {
    llm_tokens: 0,
    vlm_tokens: 0,
    embedding_tokens: 0,
    reranker_tokens: 0,
    total_tokens: 0,
  },
};

/** Token 统计快照：百万级大数值态（排版验证） */
export const largeTokenUsage: TokenUsageSnapshot = {
  session_id: "sess-demo-large",
  user_ip: "127.0.0.1",
  updated_at: Math.floor(Date.now() / 1000),
  llm_tokens: 903280,
  vlm_tokens: 62540,
  embedding_tokens: 222782,
  reranker_tokens: 96000,
  total_tokens: 1284602,
  query: {
    llm_tokens: 842000,
    vlm_tokens: 52000,
    embedding_tokens: 78000,
    reranker_tokens: 96000,
    total_tokens: 1068000,
  },
  upload: {
    llm_tokens: 61280,
    vlm_tokens: 10540,
    embedding_tokens: 144782,
    reranker_tokens: 0,
    total_tokens: 216602,
  },
};

/** Token 统计快照：相对 mockTokenUsage 的增量（llm +300 / embedding +200 / reranker +300），验证按模型拆分的气泡 */
export const tokenUsageAfterDelta: TokenUsageSnapshot = {
  session_id: "sess-demo-token",
  user_ip: "127.0.0.1",
  updated_at: Math.floor(Date.now() / 1000),
  llm_tokens: 1406,
  vlm_tokens: 1264,
  embedding_tokens: 1995,
  reranker_tokens: 650,
  total_tokens: 5315,
  query: {
    llm_tokens: 920,
    vlm_tokens: 0,
    embedding_tokens: 1105,
    reranker_tokens: 650,
    total_tokens: 2675,
  },
  upload: {
    llm_tokens: 486,
    vlm_tokens: 1264,
    embedding_tokens: 890,
    reranker_tokens: 0,
    total_tokens: 2640,
  },
};
