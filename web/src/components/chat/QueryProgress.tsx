import { StatusLog, type StatusLogLine } from "@/components/ui/StatusLog";
import { PROGRESS_STATUS_LABELS } from "@/lib/constants";
import type { ProgressView } from "@/types/app";

/**
 * 查询任务进度（输入框上方唯一卡片的内容）。
 * 摘要行拆成「标题 + 计数」两个节点：窄屏时标题保持单行、计数整体换行，
 * 避免「阶段 / 进度」被从中间拆开。
 */
export function QueryProgress({
  progress,
  open,
}: {
  progress: ProgressView;
  open: boolean;
}) {
  const status =
    PROGRESS_STATUS_LABELS[progress.status] || progress.status || "unknown";
  const lines: StatusLogLine[] = [
    ...progress.done.map((text) => ({ kind: "done" as const, text })),
    ...progress.running.map((text) => ({ kind: "running" as const, text })),
  ];

  return (
    <StatusLog
      className="progress"
      open={open}
      summary={
        <>
          <span className="progress-title">阶段进度</span>
          <span className="progress-count">
            {`（已完成${progress.done.length}，进行中${progress.running.length}，状态：${status}）`}
          </span>
        </>
      }
      lines={lines}
    />
  );
}
