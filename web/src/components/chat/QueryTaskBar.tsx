import { QueryProgress } from "@/components/chat/QueryProgress";
import { CloseIcon } from "@/components/icons/AppIcons";
import type { QueryTaskView } from "@/types/chat";

/**
 * 查询页唯一任务状态卡片：常驻输入框上方，显示最后一次查询。
 * - 卡片默认展开；任务完成/失败后**不自动收起**，用户可点击摘要手动收起/展开；
 * - 终态在卡片右侧显示关闭按钮，点击移除卡片（运行中不可关闭）；
 * - key=task.id：新查询重新挂载内容并展开。
 */
export function QueryTaskBar({
  task,
  onDismiss,
}: {
  task: QueryTaskView;
  onDismiss: () => void;
}) {
  const closable =
    task.progress.status === "completed" || task.progress.status === "failed";

  return (
    <div
      className={`task-bar${closable ? " task-bar--closable" : ""}`}
      role="status"
      aria-live="polite"
      aria-atomic="false"
      aria-label="查询任务状态"
    >
      <QueryProgress key={task.id} progress={task.progress} open />

      {closable && (
        <button
          type="button"
          className="task-close"
          onClick={onDismiss}
          aria-label="关闭任务状态卡片"
          title="关闭任务状态卡片"
        >
          <CloseIcon />
        </button>
      )}
    </div>
  );
}
