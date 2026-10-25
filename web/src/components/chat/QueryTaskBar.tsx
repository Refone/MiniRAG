import { QueryProgress } from "@/components/chat/QueryProgress";
import type { QueryTaskView } from "@/types/chat";

/**
 * 查询页唯一任务状态卡片：常驻输入框上方，显示最后一次查询。
 * - 运行中（pending / processing）展开；完成/失败（终态）自动收起为摘要行；
 * - key=task.id：新查询原地顶替并重新展开，手动展开状态不跨任务残留。
 */
export function QueryTaskBar({ task }: { task: QueryTaskView }) {
  const isRunning =
    task.progress.status === "pending" || task.progress.status === "processing";

  return (
    <div
      className="task-bar"
      role="status"
      aria-live="polite"
      aria-atomic="false"
      aria-label="查询任务状态"
    >
      <QueryProgress key={task.id} progress={task.progress} open={isRunning} />
    </div>
  );
}
