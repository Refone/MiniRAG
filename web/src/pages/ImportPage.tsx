/**
 * 知识库文件导入页（ImportPage）
 *
 * 交互是「两步式异步」——后端导入是长任务（MinerU / VLM / Embedding），
 * 不能同步等待，所以拆成：
 *   1. 上传：选文件 → POST /import/upload，后端立即返回 task_id（HTTP 202）
 *   2. 轮询：前端每 2 秒 GET /import/status/{task_id} 查进度，
 *            直到任务 complete / failed 才停表
 *
 * 后端契约（详见 src/api/routers/import_page.py 与 schema/all_schema.py）：
 *   - POST /import/upload            返回 { task_id, status }
 *   - GET  /import/status/{task_id}  返回 { task_id, status, running_nodes, done_nodes, result }
 *   - 后端 status 取值（utils/task_utils.py 的 TaskStatus）：
 *         pending / processing / complete / failed
 *     前端 ImportStatus 取值（@/lib/types）：
 *         uploading / processing / completed / error
 *     两者在 pollStatus() 里做映射：
 *         complete → completed（注意后端拼写无 d）、failed → error、
 *         pending / processing → processing（pending 视为“已受理、处理中”）。
 */

import {
  useEffect,
  useRef,
  useState,
  type ChangeEvent,
  type DragEvent,
} from "react";
import {
  API_BASE,
  ImportUploadResponse,
  UploadStatusResponse,
} from "@/lib/api";
import type { ImportFile, ImportStatus } from "@/lib/types";

/* ------------------------------------------------------------------ */
/* 常量 & 状态映射                                                      */
/* ------------------------------------------------------------------ */

/** 前端 ImportStatus → 状态徽标文案 */
const STATUS_LABELS: Record<ImportStatus, string> = {
  uploading: "上传中...",
  processing: "处理中...",
  completed: "已完成",
  error: "失败",
};

/** 前端 ImportStatus → 状态徽标底色 class（样式见 styles/global.css） */
const STATUS_CLASSES: Record<ImportStatus, string> = {
  uploading: "status-uploading",
  processing: "status-processing",
  completed: "status-completed",
  error: "status-error",
};

/** 上传步骤在日志里的显示名（后端节点不含“上传”这一步，前端手动补一条） */
const UPLOAD_STEP = "上传文件";

/**
 * 导入链路「后端节点」序列（与 processor/import_processor/main_graph.py 一致）。
 * PDF 会多走 node_pdf_to_md 这一步，Markdown 直接跳过它：
 *   - PDF：6 个节点
 *   - Markdown：5 个节点
 * 注意：完整链路最前面还有「上传文件」这一步（前端补，见 UPLOAD_STEP），
 * 总步数 = 节点数 + 1，由 inferTotalSteps() 统一计算。
 */
const PDF_STEPS = [
  "node_entry",
  "node_pdf_to_md",
  "node_md_img",
  "node_document_split",
  "node_item_name_vect",
  "node_chunks_vect",
];
const MD_STEPS = [
  "node_entry",
  "node_md_img",
  "node_document_split",
  "node_item_name_vect",
  "node_chunks_vect",
];

/* ------------------------------------------------------------------ */
/* 小工具函数                                                          */
/* ------------------------------------------------------------------ */

/** 生成一个本地文件条目的唯一 id（仅前端列表渲染用，与后端 task_id 无关） */
function makeId(): string {
  return "file-" + Math.random().toString(36).slice(2, 11);
}

/** 把后端返回的「已完成节点名」（如 node_entry）包装成中文日志文案 */
function normalizeDoneLog(text: unknown): string {
  const t = typeof text === "string" ? text : String(text);
  return `✅ ${t}`;
}

/** 把后端返回的「进行中节点名」包装成中文日志文案 */
function normalizeRunningLog(text: unknown): string {
  const t = typeof text === "string" ? text : String(text);
  return `⏳ ${t}`;
}

/** 把「失败节点名」包装成失败日志文案 */
function normalizeFailedLog(text: unknown): string {
  const t = typeof text === "string" ? text : String(text);
  return `❌ ${t}`;
}

/**
 * 根据文件名后缀推断导入链路的「总步数」（含最前面的「上传文件」步骤）。
 *   - PDF：1(上传) + 6(节点) = 7 步
 *   - Markdown：1(上传) + 5(节点) = 6 步
 */
function inferTotalSteps(fileName: string): number {
  const nodeSteps = /\.pdf$/i.test(fileName)
    ? PDF_STEPS.length
    : MD_STEPS.length;
  return nodeSteps + 1; // +1：链路第一步「上传文件」
}

/**
 * 由「已完成节点数 / 总节点数」计算处理阶段进度（0 ~ 99）。
 * 每个节点完成推进 100/totalSteps%；99% 是封顶，最后的 100% 只在
 * 后端返回 complete 时才设置，避免「节点已全部完成但状态还没翻转」时进度条先顶到 100%。
 */
function calcProgress(doneCount: number, totalSteps: number): number {
  if (totalSteps <= 0) return 0;
  return Math.min(Math.round((doneCount / totalSteps) * 100), 99);
}

/* ------------------------------------------------------------------ */
/* 文件条目子组件：一个文件对应一行（名称/大小/进度条/日志/状态徽标）   */
/* ------------------------------------------------------------------ */

function FileItem({ file }: { file: ImportFile }) {
  const uploading = file.status === "uploading";
  const failed = file.status === "error";

  // 后端在节点抛异常时，finally 仍会把该节点写进 done_nodes（而不是留在 running_nodes），
  // 因此「失败节点」会混在 done 列表里。按顺序识别：失败时最后一个 done 节点即失败节点。
  const failedNode =
    failed && file.done.length > 0 ? file.done[file.done.length - 1] : null;

  // 真正成功完成的节点 = done 去掉最后一个失败节点
  const doneNodes = failedNode ? file.done.slice(0, -1) : file.done;

  // 上传步骤的符号：上传中 ⏳ / 上传失败 ❌（error 且无任何节点）/ 其余 ✅
  let uploadLog: string;
  if (uploading) {
    uploadLog = normalizeRunningLog(UPLOAD_STEP);
  } else if (failed && file.done.length === 0) {
    uploadLog = normalizeFailedLog(UPLOAD_STEP);
  } else {
    uploadLog = normalizeDoneLog(UPLOAD_STEP);
  }

  // 顺序：上传步骤 → 已完成节点 → 失败节点 → 进行中节点
  const lines = [
    uploadLog,
    ...doneNodes.map(normalizeDoneLog),
    ...(failedNode ? [normalizeFailedLog(failedNode)] : []),
    ...file.running.map(normalizeRunningLog),
  ];

  // 已完成计数：上传（若已完成）+ 成功节点数（不含失败节点）
  const doneCount = (uploading ? 0 : 1) + doneNodes.length;
  const totalSteps = inferTotalSteps(file.name);

  // 完成后（completed）自动收起；上传/处理/失败保持展开，失败时方便查看出错节点
  const isOpen = file.status !== "completed";

  return (
    <div className="file-item">
      <div className="file-info">
        <span className="file-name">{file.name}</span>
        <span className="file-size">{file.sizeKB}</span>
        <div className="progress-bar-container">
          <div
            className="progress-bar"
            style={{
              width: `${file.progress}%`,
              backgroundColor:
                file.progress >= 100 ? "var(--info)" : "var(--warning)",
            }}
          />
        </div>
        <details className="log-details" open={isOpen}>
          <summary>{`任务已完成 [${doneCount}/${totalSteps}]，点击收起 / 展开`}</summary>
          <ul className="log-list">
            {lines.map((line, i) => (
              <li key={i}>{line}</li>
            ))}
          </ul>
        </details>
      </div>
      <div className={`status-badge ${STATUS_CLASSES[file.status]}`}>
        {STATUS_LABELS[file.status]}
      </div>
    </div>
  );
}

/* ------------------------------------------------------------------ */
/* 主组件                                                              */
/* ------------------------------------------------------------------ */

export function ImportPage() {
  /* ---- 状态 ---- */
  // 已添加的文件列表（前端展示用，每个条目独立跟踪进度）
  const [files, setFiles] = useState<ImportFile[]>([]);
  // 是否正有文件拖拽悬停在上传区上（用于高亮）
  const [dragging, setDragging] = useState(false);

  /* ---- refs ---- */
  // 隐藏的 <input type="file">，点击上传区时用它唤起系统文件选择框
  const fileInputRef = useRef<HTMLInputElement>(null);
  // 每个文件条目对应一个轮询定时器：key = 前端 file id，value = setInterval 句柄
  const intervalsRef = useRef<Record<string, number>>({});
  // 已上报过轮询失败的任务：避免同一任务每 2 秒重复打 error 日志刷屏
  const pollingErrorReportedRef = useRef<Set<string>>(new Set());

  /** 按 id 局部更新某个文件条目（浅合并，只改传入的字段） */
  const updateFile = (id: string, patch: Partial<ImportFile>) => {
    setFiles((prev) => prev.map((f) => (f.id === id ? { ...f, ...patch } : f)));
  };

  /** 停止某个文件条目的轮询定时器（任务结束或失败后调用） */
  const clearPolling = (id: string) => {
    const timer = intervalsRef.current[id];
    if (timer) {
      window.clearInterval(timer);
      delete intervalsRef.current[id];
    }
  };

  // 卸载组件时清掉所有仍在跑的定时器，避免内存泄漏 / 后台继续发请求
  useEffect(() => {
    const timers = intervalsRef.current;
    return () => {
      Object.values(timers).forEach((t) => window.clearInterval(t));
    };
  }, []);

  /** 轮询任务进度：每隔 2 秒查一次，直到 complete / failed 才停止 */
  const pollStatus = (taskId: string, fileId: string, totalSteps: number) => {
    const interval = window.setInterval(async () => {
      try {
        const res = await fetch(`${API_BASE}/upload/status/${taskId}`);
        const data: UploadStatusResponse = await res.json();

        // 1) 同步节点进度（后端字段是 done_nodes / running_nodes）
        const doneNodes = data.done_nodes || [];
        const doneNodeCount = doneNodes.length;
        updateFile(fileId, {
          done: doneNodes,
          running: data.running_nodes || [],
        });

        if (data.status === "complete") {
          console.log(
            `[import] 任务 ${taskId} 处理完成（${doneNodeCount} 项）`,
          );
          updateFile(fileId, { status: "completed", progress: 100 });
          clearPolling(fileId);
        } else if (data.status === "failed") {
          console.error(`[import] 任务 ${taskId} 处理失败`);
          updateFile(fileId, { status: "error" });
          clearPolling(fileId);
        } else if (data.status === "processing" || data.status === "pending") {
          // 都还没跑完：进度计数 = 已上传(1) + 已完成节点数（进入轮询时上传已完成）
          updateFile(fileId, {
            status: "processing",
            progress: calcProgress(doneNodeCount + 1, totalSteps),
          });
        }
        // 其它未知状态：不做任何更新，保留上一次展示，等下一轮轮询
      } catch (e) {
        // 轮询每 2 秒一次，同一个任务只报一次失败，避免刷屏
        if (!pollingErrorReportedRef.current.has(taskId)) {
          pollingErrorReportedRef.current.add(taskId);
          console.error("[import] 轮询任务状态失败", e);
        }
      }
    }, 2000);
    intervalsRef.current[fileId] = interval;
  };

  /** 上传单个文件：先落一条「上传中」条目，成功后拿到 task_id 再转入轮询 */
  const uploadFile = async (file: File) => {
    const id = makeId();
    // 按文件类型确定导入链路总步数（含上传：PDF 7 步 / Markdown 6 步），供进度条按比例推进
    const totalSteps = inferTotalSteps(file.name);
    const newFile: ImportFile = {
      id,
      name: file.name,
      sizeKB: (file.size / 1024).toFixed(2) + " KB",
      status: "uploading",
      progress: 0, // 上传阶段没有可靠的字节进度回调，先保持 0%
      done: [],
      running: [],
    };
    setFiles((prev) => [newFile, ...prev]);
    console.log(`[import] 开始上传：${file.name}（${newFile.sizeKB}）`);

    // 后端接收单个文件，字段名为 file（见 import_page.py 的 UploadFile 参数）
    const formData = new FormData();
    formData.append("file", file);

    try {
      const response = await fetch(`${API_BASE}/upload`, {
        method: "POST",
        body: formData,
      });
      if (!response.ok) throw new Error("Upload failed");

      const result: ImportUploadResponse = await response.json();
      const taskId = result.task_id;
      console.log(
        `[import] 上传成功：${file.name} → 任务 ${taskId}，开始轮询状态`,
      );

      // 2. 上传完成 → 进入处理中；进度不再写死，交给 pollStatus 按已完成节点数推进
      updateFile(id, { status: "processing" });
      pollStatus(taskId, id, totalSteps);
    } catch (error) {
      console.error(`[import] 上传失败：${file.name}`, error);
      updateFile(id, { status: "error" });
    }
  };

  /** 处理一组文件（拖拽与点击选择共用此入口） */
  const handleFiles = (fileList: FileList | null) => {
    if (!fileList) return;
    Array.from(fileList).forEach(uploadFile);
  };

  /** 拖拽释放：把拖进来的文件交给 handleFiles */
  const onDrop = (e: DragEvent<HTMLDivElement>) => {
    e.preventDefault();
    setDragging(false);
    handleFiles(e.dataTransfer.files);
  };

  /** 点击选择：把选中的文件交给 handleFiles，并清空 input 以便重复选同一文件 */
  const onInputChange = (e: ChangeEvent<HTMLInputElement>) => {
    handleFiles(e.target.files);
    e.target.value = "";
  };

  return (
    <div className="import-page">
      <h1 className="import-title">📄 知识库文件导入</h1>

      {/* 上传区：点击唤起文件选择框，也支持拖拽 */}
      <div
        className={`upload-area${dragging ? " dragging" : ""}`}
        onClick={() => fileInputRef.current?.click()}
        onDragOver={(e) => {
          e.preventDefault();
          setDragging(true);
        }}
        onDragLeave={(e) => {
          e.preventDefault();
          setDragging(false);
        }}
        onDrop={onDrop}
      >
        <div className="upload-icon">☁️</div>
        <p>点击或拖拽文件到此处 (PDF/MD)</p>
        <input
          ref={fileInputRef}
          type="file"
          className="file-input"
          multiple
          accept=".pdf,.md"
          onChange={onInputChange}
        />
      </div>

      {/* 已添加的文件列表，每个文件一个 FileItem */}
      <div className="file-list">
        {files.map((f) => (
          <FileItem key={f.id} file={f} />
        ))}
      </div>
    </div>
  );
}
