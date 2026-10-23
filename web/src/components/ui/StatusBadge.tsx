interface StatusBadgeProps {
  label: string;
  className: string;
}

/** 状态徽章（导入任务四态：上传中/处理中/已完成/失败） */
export function StatusBadge({ label, className }: StatusBadgeProps) {
  return <div className={`status-badge ${className}`}>{label}</div>;
}
