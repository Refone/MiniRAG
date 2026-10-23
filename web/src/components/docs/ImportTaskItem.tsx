import { memo, useEffect, useState } from "react";
import { StatusBadge } from "@/components/ui/StatusBadge";
import { StatusLog, type StatusLogLine } from "@/components/ui/StatusLog";
import { IMPORT_STATUS } from "@/lib/constants";
import type { ImportFile } from "@/types/docs";

interface ImportTaskItemProps {
  file: ImportFile;
}

/** 导入任务条目（原 ImportPage ImportTaskItem 原样平移）；memo 剪枝 (BUG-004) */
export const ImportTaskItem = memo(function ImportTaskItem({
  file,
}: ImportTaskItemProps) {
  const statusMeta =
    IMPORT_STATUS.find((s) => s.value === file.status) ??
    IMPORT_STATUS[IMPORT_STATUS.length - 1];
  const failed = file.status === "error";
  const failedNode =
    failed && file.done.length > 0 ? file.done[file.done.length - 1] : null;
  const doneNodes = failedNode ? file.done.slice(0, -1) : file.done;
  const lines: StatusLogLine[] = [
    ...doneNodes.map((n) => ({ kind: "done" as const, text: n })),
    ...(failedNode ? [{ kind: "failed" as const, text: failedNode }] : []),
    ...file.running.map((n) => ({ kind: "running" as const, text: n })),
  ];

  const [now, setNow] = useState(() => Date.now());
  const active = file.status === "uploading" || file.status === "processing";
  useEffect(() => {
    if (!active) return;
    const timer = window.setInterval(() => setNow(Date.now()), 500);
    return () => window.clearInterval(timer);
  }, [active]);
  const elapsedText = `${((now - file.startedAt) / 1000).toFixed(1)}s`;

  const isOpen = file.status !== "completed";

  return (
    <div className="file-item">
      <div className="file-info">
        <span className="file-name">{file.name}</span>
        <span className="file-size">{file.sizeKB}</span>
        <StatusLog
          className="log-details"
          listClassName="log-list"
          open={isOpen}
          summary={`已耗时 ${elapsedText}，点击收起 / 展开`}
          lines={lines}
        />
      </div>
      <StatusBadge label={statusMeta.label} className={statusMeta.className} />
    </div>
  );
});
