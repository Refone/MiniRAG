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
import { CompleteIcon } from "@/components/CompleteIcon";
import { FailedIcon } from "@/components/FailedIcon";
import { LoadingIcon } from "@/components/LoadingIcon";

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

/* ------------------------------------------------------------------ */
/* 小工具函数                                                          */
/* ------------------------------------------------------------------ */

/** 生成一个本地文件条目的唯一 id（仅前端列表渲染用，与后端 task_id 无关） */
function makeId(): string {
  return "file-" + Math.random().toString(36).slice(2, 11);
}

/** 日志行类型：kind 决定使用哪个状态图标，text 是节点名 */
type LogLine = { kind: "done" | "running" | "failed"; text: string };

/* ------------------------------------------------------------------ */
/* 文件条目子组件：一个文件对应一行（名称/大小/步骤日志/已耗时/状态徽标） */
/* ------------------------------------------------------------------ */

function FileItem({ file }: { file: ImportFile }) {
  const failed = file.status === "error";

  // 后端在节点抛异常时，finally 仍会把该节点写进 done_nodes（而不是留在 running_nodes），
  // 因此「失败节点」会混在 done 列表里。按顺序识别：失败时最后一个 done 节点即失败节点。
  const failedNode =
    failed && file.done.length > 0 ? file.done[file.done.length - 1] : null;

  // 真正成功完成的节点 = done 去掉最后一个失败节点
  const doneNodes = failedNode ? file.done.slice(0, -1) : file.done;

  // 步骤列表完全来自后端节点（与 query_processor 一致）：已完成节点 → 失败节点 → 进行中节点
  const lines: LogLine[] = [
    ...doneNodes.map((n) => ({ kind: "done" as const, text: n })),
    ...(failedNode ? [{ kind: "failed" as const, text: failedNode }] : []),
    ...file.running.map((n) => ({ kind: "running" as const, text: n })),
  ];

  // 已消耗时间：任务进行中每秒刷新，结束后冻结在最终值
  const [now, setNow] = useState(() => Date.now());
  const active = file.status === "uploading" || file.status === "processing";
  useEffect(() => {
    if (!active) return;
    const timer = window.setInterval(() => setNow(Date.now()), 500);
    return () => window.clearInterval(timer);
  }, [active]);
  const elapsedSeconds = (now - file.startedAt) / 1000;
  const elapsedText = `${elapsedSeconds.toFixed(1)}s`;

  // 完成后（completed）自动收起；上传/处理/失败保持展开，失败时方便查看出错节点
  const isOpen = file.status !== "completed";

  return (
    <div className="file-item">
      <div className="file-info">
        <span className="file-name">{file.name}</span>
        <span className="file-size">{file.sizeKB}</span>
        <details className="log-details" open={isOpen}>
          <summary>{`已耗时 ${elapsedText}，点击收起 / 展开`}</summary>
          <ul className="log-list">
            {lines.length === 0 ? (
              <li className="status-line">暂无进度</li>
            ) : (
              lines.map((line) => (
                <li key={line.text} className="status-line">
                  <span className={`status-line__icon status-line__icon--${line.kind}`}>
                    {line.kind === "done" ? (
                      <CompleteIcon />
                    ) : line.kind === "failed" ? (
                      <FailedIcon />
                    ) : (
                      <LoadingIcon />
                    )}
                  </span>
                  <span className="status-line__text">{line.text}</span>
                </li>
              ))
            )}
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
  const pollStatus = (taskId: string, fileId: string) => {
    const interval = window.setInterval(async () => {
      try {
        const res = await fetch(`${API_BASE}/upload/status/${taskId}`);
        const data: UploadStatusResponse = await res.json();

        // 同步后端节点进度（done_nodes / running_nodes），步骤展示与 query_processor 一致
        updateFile(fileId, {
          done: data.done_nodes || [],
          running: data.running_nodes || [],
        });

        if (data.status === "complete") {
          console.log(`[import] 任务 ${taskId} 处理完成`);
          updateFile(fileId, { status: "completed" });
          clearPolling(fileId);
        } else if (data.status === "failed") {
          console.error(`[import] 任务 ${taskId} 处理失败`);
          updateFile(fileId, { status: "error" });
          clearPolling(fileId);
        } else if (data.status === "processing" || data.status === "pending") {
          updateFile(fileId, { status: "processing" });
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
    const newFile: ImportFile = {
      id,
      name: file.name,
      sizeKB: (file.size / 1024).toFixed(2) + " KB",
      status: "uploading",
      startedAt: Date.now(), // 已消耗时间从开始上传时计时
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

      // 上传完成 → 进入处理中；步骤列表交给 pollStatus 按后端节点同步
      updateFile(id, { status: "processing" });
      pollStatus(taskId, id);
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
