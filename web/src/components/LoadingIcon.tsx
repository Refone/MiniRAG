interface LoadingIconProps {
  size?: number;
  className?: string;
}

/** 等待状态图标：无限循环旋转的加载动画。 */
export function LoadingIcon({ size = 16, className }: LoadingIconProps) {
  return (
    <svg
      className={`status-icon status-icon-loading${className ? ` ${className}` : ""}`}
      width={size}
      height={size}
      viewBox="0 0 24 24"
      fill="none"
      aria-hidden="true"
    >
      <circle className="status-icon-loading__track" cx="12" cy="12" r="9" />
      <circle className="status-icon-loading__arc" cx="12" cy="12" r="9" />
    </svg>
  );
}
