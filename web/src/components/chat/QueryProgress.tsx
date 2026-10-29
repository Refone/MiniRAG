import { StatusLog, type StatusLogLine } from "@/components/ui/StatusLog";
import { TASK_STATUS_LABELS } from "@/lib/constants";
import type { ProgressView } from "@/types/app";

/**
 * 查询任务进度（输入框上方唯一卡片的内容）。
 * 摘要行拆成「标题 + 状态」两个节点：窄屏时标题保持单行、状态整体换行，
 * 避免「阶段 / 进度」被从中间拆开；仅运行步骤摘要（--steps）独占一行。
 */
export function QueryProgress({
  progress,
  open,
}: {
  progress: ProgressView;
  open: boolean;
}) {
  const lines: StatusLogLine[] = [
    ...progress.done.map((text) => ({ kind: "done" as const, text })),
    ...progress.running.map((text) => ({ kind: "running" as const, text })),
  ];

  const runningSteps =
    progress.status === "processing" ? progress.running : [];
  const hasRunningSteps = runningSteps.length > 0;
  const statusText = hasRunningSteps
    ? `进行中：${runningSteps.join("，")}...`
    : TASK_STATUS_LABELS[progress.status] || progress.status || "未知";

  return (
    <StatusLog
      className="progress"
      open={open}
      summary={
        <>
          <span className="progress-title">阶段进度</span>
          <span
            className={`progress-count${hasRunningSteps ? " progress-count--steps" : ""}`}
          >
            {`（${statusText}）`}
          </span>
        </>
      }
      lines={lines}
    />
  );
}
