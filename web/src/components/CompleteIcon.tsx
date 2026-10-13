interface CompleteIconProps {
  size?: number;
  className?: string;
}

/** 完成状态图标：对勾绘制动画，播放一次后保持。 */
export function CompleteIcon({ size = 16, className }: CompleteIconProps) {
  return (
    <svg
      className={`status-icon status-icon-complete${className ? ` ${className}` : ""}`}
      width={size}
      height={size}
      viewBox="0 0 24 24"
      fill="none"
      aria-hidden="true"
    >
      <circle className="status-icon-complete__ring" cx="12" cy="12" r="10" />
      <path
        className="status-icon-complete__check"
        pathLength={100}
        d="M7.5 12.5 L10.5 15.5 L16.5 9.5"
      />
    </svg>
  );
}
