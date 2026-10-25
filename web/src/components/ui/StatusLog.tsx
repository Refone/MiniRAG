import type { ReactNode } from "react";
import { StatusIcon } from "@/components/icons/StatusIcon";

export interface StatusLogLine {
  kind: "done" | "running" | "failed";
  text: string;
}

interface StatusLogProps {
  lines: StatusLogLine[];
  /** 折叠区摘要行（不传则不渲染 summary）；聊天页传结构化节点，导入页传字符串 */
  summary?: ReactNode;
  open?: boolean;
  emptyText?: string;
  /** details 元素类名：聊天页 "progress" / 导入任务 "log-details" */
  className?: string;
  /** ul 元素类名：导入任务传 "log-list"（聊天页无） */
  listClassName?: string;
}

/**
 * 进度日志（合并 ChatPage ProgressDetails 与 ImportTaskItem 日志区）：
 * done/running/failed 三态状态行列表，折叠区由调用方决定 open 与 summary 内容
 * （summary 接受 ReactNode：查询卡片需要标题 / 计数分段，窄屏才能整体换行）。
 */
export function StatusLog({
  lines,
  summary,
  open,
  emptyText = "暂无进度",
  className = "progress",
  listClassName,
}: StatusLogProps) {
  return (
    <details className={className} open={open}>
      {summary && <summary>{summary}</summary>}
      <ul className={listClassName}>
        {lines.length === 0 ? (
          <li className="status-line">{emptyText}</li>
        ) : (
          lines.map((item) => (
            <li key={item.text} className="status-line">
              <span
                className={`status-line__icon status-line__icon--${item.kind}`}
              >
                {item.kind === "done" ? (
                  <StatusIcon kind="done" />
                ) : item.kind === "failed" ? (
                  <StatusIcon kind="failed" />
                ) : (
                  <StatusIcon kind="loading" />
                )}
              </span>
              <span className="status-line__text">{item.text}</span>
            </li>
          ))
        )}
      </ul>
    </details>
  );
}
