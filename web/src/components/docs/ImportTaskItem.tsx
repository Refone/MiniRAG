import { memo, useEffect, useMemo, useRef, useState } from "react";
import { ForkIcon } from "@/components/icons/AppIcons";
import { ImportChildItem } from "@/components/docs/ImportChildItem";
import { StatusBadge } from "@/components/ui/StatusBadge";
import { StatusLog, type StatusLogLine } from "@/components/ui/StatusLog";
import { IMPORT_STATUS_META } from "@/lib/constants";
import type { ImportFile } from "@/types/docs";

interface ImportTaskItemProps {
  file: ImportFile;
}

/** 导入任务条目：PDF / 独文件 md 为单卡；ZIP fork 后追加子任务树。memo 剪枝 (BUG-004) */
export const ImportTaskItem = memo(function ImportTaskItem({
  file,
}: ImportTaskItemProps) {
  const statusMeta = IMPORT_STATUS_META[file.status];

  const lines: StatusLogLine[] = [
    ...file.done.map((n) => ({ kind: "done" as const, text: n })),
    ...file.failed.map((n) => ({ kind: "failed" as const, text: n })),
    ...file.running.map((n) => {
      const detail = file.detail;
      return {
        kind: "running" as const,
        text: detail && detail.node === n ? `${n} · ${detail.text}` : n,
      };
    }),
  ];

  const [now, setNow] = useState(() => Date.now());
  const active = file.status === "uploading" || file.status === "processing";
  useEffect(() => {
    if (!active) return;
    const timer = window.setInterval(() => setNow(Date.now()), 500);
    return () => window.clearInterval(timer);
  }, [active]);
  const elapsedText = `${((now - file.startedAt) / 1000).toFixed(1)}s`;

  const hasChildren = file.children.length > 0;

  /* 父卡日志手动开合；fork 时只自动收起一次，后续子任务更新不再强制改状态 */
  const [parentOpen, setParentOpen] = useState(
    () => file.status !== "complete",
  );
  const autoClosedRef = useRef(false);
  useEffect(() => {
    if (hasChildren && !autoClosedRef.current) {
      autoClosedRef.current = true;
      setParentOpen(false);
    }
  }, [hasChildren]);

  /* 保留原有「父任务完成自动收起一次」；之后用户手动开合不再被覆盖 */
  const prevStatusRef = useRef(file.status);
  useEffect(() => {
    if (file.status === "complete" && prevStatusRef.current !== "complete") {
      setParentOpen(false);
    }
    prevStatusRef.current = file.status;
  }, [file.status]);

  const counts = useMemo(() => {
    const result = {
      pending: 0,
      processing: 0,
      complete: 0,
      failed: 0,
      interrupted: 0,
    };
    file.children.forEach((c) => {
      result[c.status] += 1;
    });
    return result;
  }, [file.children]);

  const aggregateText = useMemo(() => {
    const total = file.children.length;
    const parts = [`${counts.complete} / ${total} 完成`];
    if (counts.processing) parts.push(`${counts.processing} 进行中`);
    if (counts.pending) parts.push(`${counts.pending} 等待`);
    if (counts.failed) parts.push(`${counts.failed} 失败`);
    if (counts.interrupted) parts.push(`${counts.interrupted} 未完成`);
    return parts.join(" · ");
  }, [counts, file.children.length]);

  return (
    <div className="file-item" data-state={file.status}>
      <div className="file-head">
        <div className="file-info">
          <span className="file-name">{file.name}</span>
          <span className="file-size">{file.sizeKB}</span>
          <StatusLog
            className="log-details"
            listClassName="log-list"
            open={parentOpen}
            onToggle={setParentOpen}
            summary={`已耗时 ${elapsedText}${file.detail ? ` · ${file.detail.text}` : ""}，点击收起 / 展开`}
            lines={lines}
          />
        </div>
        <StatusBadge label={statusMeta.label} className={statusMeta.className} />
      </div>

      {hasChildren && (
        <div className="file-fork">
          <div className="fork-head">
            <span className="fork-mark" aria-hidden="true">
              <ForkIcon />
            </span>
            <span className="fork-title">
              已分叉 <strong>{file.children.length}</strong> 个 md 任务
            </span>
            <span className="fork-count" title={aggregateText}>
              {aggregateText}
            </span>
          </div>

          <div
            className="fork-meter"
            role="progressbar"
            aria-label="md 子任务进度"
            aria-valuemin={0}
            aria-valuemax={file.children.length}
            aria-valuenow={counts.complete}
            aria-valuetext={aggregateText}
          >
            {file.children.map((child) => (
              <span
                key={child.id}
                className={`is-${child.status}`}
              />
            ))}
          </div>

          <ul className="child-tree" aria-label="md 子任务列表">
            {file.children.map((child) => (
              <ImportChildItem key={child.id} child={child} />
            ))}
          </ul>
        </div>
      )}
    </div>
  );
});
