import { useState } from "react";

interface FailedIconProps {
  size?: number;
  className?: string;
}

/**
 * 失败状态图标：叉号绘制动画，播放一次后保持。
 * Session-MVVM 修正 (BUG-001): 子树经历 display:none → visible 时 CSS 动画会
 * 重新播放 (切回 Tab 重复动画)。onAnimationEnd 后移除动画并定格最终状态。
 */
export function FailedIcon({ size = 16, className }: FailedIconProps) {
  const [played, setPlayed] = useState(false);
  return (
    <svg
      className={`status-icon status-icon-failed${className ? ` ${className}` : ""}`}
      width={size}
      height={size}
      viewBox="0 0 24 24"
      fill="none"
      aria-hidden="true"
    >
      <circle className="status-icon-failed__ring" cx="12" cy="12" r="10" />
      <path
        className="status-icon-failed__cross"
        style={played ? { animation: "none", strokeDashoffset: 0 } : undefined}
        onAnimationEnd={() => setPlayed(true)}
        pathLength={100}
        d="M8.5 8.5 L15.5 15.5 M15.5 8.5 L8.5 15.5"
      />
    </svg>
  );
}
