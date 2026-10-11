import { useEffect, useRef, useState, type ChangeEvent, type DragEvent } from 'react';
import { IMPORT_API_BASE } from '@/lib/api';
import type { ImportFile, ImportStatus, StatusResponse, UploadResponse } from '@/lib/types';

function makeId(): string {
  return 'file-' + Math.random().toString(36).slice(2, 11);
}

function normalizeDoneLog(text: unknown): string {
  const t = typeof text === 'string' ? text : String(text);
  return t.endsWith('已完成') ? t : `${t}已完成`;
}

function normalizeRunningLog(text: unknown): string {
  const t = typeof text === 'string' ? text : String(text);
  if (t.startsWith('正在进行')) return t.endsWith('...') ? t : `${t}...`;
  return `正在进行${t}...`;
}

const STATUS_LABELS: Record<ImportStatus, string> = {
  uploading: '上传中...',
  processing: '处理中...',
  completed: '已完成',
  error: '失败',
};

const STATUS_CLASSES: Record<ImportStatus, string> = {
  uploading: 'status-uploading',
  processing: 'status-processing',
  completed: 'status-completed',
  error: 'status-error',
};

function FileItem({ file }: { file: ImportFile }) {
  const lines = [...file.done.map(normalizeDoneLog), ...file.running.map(normalizeRunningLog)];

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
              backgroundColor: file.progress >= 100 ? 'var(--info)' : 'var(--warning)',
            }}
          />
        </div>
        <details className="log-details">
          <summary>{`日志（已完成${file.done.length}，进行中${file.running.length}，点击展开）`}</summary>
          <ul className="log-list">
            {lines.length === 0 ? <li>暂无日志</li> : lines.map((line, i) => <li key={i}>{line}</li>)}
          </ul>
        </details>
      </div>
      <div className={`status-badge ${STATUS_CLASSES[file.status]}`}>{STATUS_LABELS[file.status]}</div>
    </div>
  );
}

export function ImportPage() {
  const [files, setFiles] = useState<ImportFile[]>([]);
  const [dragging, setDragging] = useState(false);
  const fileInputRef = useRef<HTMLInputElement>(null);
  const intervalsRef = useRef<Record<string, number>>({});
  /** 已上报过轮询失败的任务，避免每 2 秒重复打日志 */
  const pollingErrorReportedRef = useRef<Set<string>>(new Set());

  const updateFile = (id: string, patch: Partial<ImportFile>) => {
    setFiles((prev) => prev.map((f) => (f.id === id ? { ...f, ...patch } : f)));
  };

  const clearPolling = (id: string) => {
    const timer = intervalsRef.current[id];
    if (timer) {
      window.clearInterval(timer);
      delete intervalsRef.current[id];
    }
  };

  // 卸载时清理所有轮询定时器
  useEffect(() => {
    const timers = intervalsRef.current;
    return () => {
      Object.values(timers).forEach((t) => window.clearInterval(t));
    };
  }, []);

  const pollStatus = (taskId: string, fileId: string) => {
    const interval = window.setInterval(async () => {
      try {
        const res = await fetch(`${IMPORT_API_BASE}/status/${taskId}`);
        const data: StatusResponse = await res.json();

        updateFile(fileId, {
          done: data.done_list || [],
          running: data.running_list || [],
        });

        if (data.status === 'completed') {
          console.log(`[import] 任务 ${taskId} 处理完成（${(data.done_list || []).length} 项）`);
          updateFile(fileId, { status: 'completed', progress: 100 });
          clearPolling(fileId);
        } else if (data.status === 'processing') {
          updateFile(fileId, { status: 'processing', progress: 30 });
        } else if (data.status === 'failed') {
          console.error(`[import] 任务 ${taskId} 处理失败`);
          updateFile(fileId, { status: 'error' });
          clearPolling(fileId);
        }
      } catch (e) {
        // 轮询每 2 秒一次，同一个任务只报一次失败，避免刷屏
        if (!pollingErrorReportedRef.current.has(taskId)) {
          pollingErrorReportedRef.current.add(taskId);
          console.error('[import] 轮询任务状态失败', e);
        }
      }
    }, 2000);
    intervalsRef.current[fileId] = interval;
  };

  const uploadFile = async (file: File) => {
    const id = makeId();
    const newFile: ImportFile = {
      id,
      name: file.name,
      sizeKB: (file.size / 1024).toFixed(2) + ' KB',
      status: 'uploading',
      progress: 50,
      done: [],
      running: [],
    };
    setFiles((prev) => [newFile, ...prev]);
    console.log(`[import] 开始上传：${file.name}（${newFile.sizeKB}）`);

    const formData = new FormData();
    formData.append('files', file);

    try {
      // 1. 上传文件（模拟上传进度 50%，实际由网络请求驱动）
      const response = await fetch(`${IMPORT_API_BASE}/upload`, { method: 'POST', body: formData });
      if (!response.ok) throw new Error('Upload failed');

      const result: UploadResponse = await response.json();
      const taskId = result.task_ids[0];
      console.log(`[import] 上传成功：${file.name} → 任务 ${taskId}，开始轮询状态`);

      // 上传完成，进入处理中，进度固定为 30%
      updateFile(id, { status: 'processing', progress: 30 });
      pollStatus(taskId, id);
    } catch (error) {
      console.error(`[import] 上传失败：${file.name}`, error);
      updateFile(id, { status: 'error' });
    }
  };

  const handleFiles = (fileList: FileList | null) => {
    if (!fileList) return;
    Array.from(fileList).forEach(uploadFile);
  };

  const onDrop = (e: DragEvent<HTMLDivElement>) => {
    e.preventDefault();
    setDragging(false);
    handleFiles(e.dataTransfer.files);
  };

  const onInputChange = (e: ChangeEvent<HTMLInputElement>) => {
    handleFiles(e.target.files);
    e.target.value = '';
  };

  return (
    <div className="import-page">
      <h1 className="import-title">📄 知识库文件导入</h1>

      <div
        className={`upload-area${dragging ? ' dragging' : ''}`}
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

      <div className="file-list">
        {files.map((f) => (
          <FileItem key={f.id} file={f} />
        ))}
      </div>
    </div>
  );
}
