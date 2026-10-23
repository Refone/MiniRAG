interface EmptyStateProps {
  /** emoji 图标（可空） */
  icon?: string;
  title: string;
  subtitle?: string;
  className?: string;
}

/**
 * 空态（合并文档列表空态与预览空态）：
 * 统一为 icon + 标题 + 副标题结构，容器类名由调用方传入。
 */
export function EmptyState({ icon, title, subtitle, className }: EmptyStateProps) {
  return (
    <div className={className}>
      {icon && <div className="preview-empty-icon">{icon}</div>}
      <p className="preview-empty-title">{title}</p>
      {subtitle && <p className="preview-empty-sub">{subtitle}</p>}
    </div>
  );
}
