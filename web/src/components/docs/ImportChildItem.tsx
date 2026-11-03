import { memo, useEffect, useState } from "react";
import { FileIcon } from "@/components/icons/AppIcons";
import { StatusBadge } from "@/components/ui/StatusBadge";
import { StatusLog, type StatusLogLine } from "@/components/ui/StatusLog";
import { IMPORT_CHILD_STATUS_META } from "@/lib/constants";
import type { ImportChildTask } from "@/types/docs";

interface ImportChildItemProps {
  child: ImportChildTask;
}

/**
 * ZIP 分叉出的单个 md 子任务卡片。
 *
 * 交互约定 (PRD / 方案设计): 日志默认收起，状态变化不自动开合，
 * 只有用户点击才展开/收起；摘要行始终表达「当前步骤 + 耗时」。
 * 这里刻意不向 StatusLog 传 open，让 <details> 保持非受控。
 */
export const ImportChildItem = memo(function ImportChildItem({
  child,
}: ImportChildItemProps) {
  const statusMeta = IMPORT_CHILD_STATUS_META[child.status];

  const [now, setNow] = useState(() => Date.now());
  const active = child.status === "processing";
  useEffect(() => {
    if (!active) return;
    const timer = window.setInterval(() => setNow(Date.now()), 500);
    return () => window.clearInterval(timer);
  }, [active]);

  const elapsedMs = child.startedAt
    ? Math.max(0, (child.stoppedAt ?? now) - child.startedAt)
    : 0;
  const elapsedText = `${(elapsedMs / 1000).toFixed(1)}s`;

  let summaryText: string;
  if (child.status === "pending") {
    summaryText = "等待开始";
  } else if (child.status === "processing") {
    const detailText = child.detail ? ` · ${child.detail.text}` : "";
    summaryText = `已耗时 ${elapsedText} · ${child.running[0] || "处理中"}${detailText}`;
  } else if (child.status === "complete") {
    summaryText = `耗时 ${elapsedText}`;
  } else if (child.status === "failed") {
    summaryText = child.failed[0]
      ? `失败于 ${child.failed[0]}`
      : "处理失败";
  } else {
    summaryText = "未完成";
  }

  const lines: StatusLogLine[] = [
    ...child.done.map((text) => ({ kind: "done" as const, text })),
    ...child.failed.map((text) => ({ kind: "failed" as const, text })),
    ...child.running.map((text) => {
      const detail = child.detail;
      return {
        kind: "running" as const,
        text: detail && detail.node === text ? `${text} · ${detail.text}` : text,
      };
    }),
  ];

  // 展示含后缀的文件名；title/path 都来自服务端，React 默认转义
  const filename = child.path.split("/").pop() || `${child.title}.md`;

  return (
    <li
      className="child-item"
      data-state={child.status}
      style={{ animationDelay: `${Math.min(child.index, 10) * 40}ms` }}
    >
      <div className="child-head">
        <FileIcon className="child-file-icon" />
        <span className="child-name" title={child.path}>
          {filename}
        </span>
        <StatusBadge label={statusMeta.label} className={statusMeta.className} />
      </div>

      <StatusLog
        className="log-details child-log"
        listClassName="log-list"
        summary={
          <>
            <span className="child-summary">{summaryText}</span>
            <span className="log-hint"> · 点击收起 / 展开</span>
          </>
        }
        lines={lines}
        emptyText={child.status === "pending" ? "排队等待执行…" : "暂无进度"}
      />

      {child.error && <div className="child-error">{child.error}</div>}
    </li>
  );
});
