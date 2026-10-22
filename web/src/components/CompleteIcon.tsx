import { useState } from "react";

interface CompleteIconProps {
  size?: number;
  className?: string;
}

/**
 * 完成状态图标：对勾绘制动画，播放一次后保持。
 * Session-MVVM 修正 (BUG-001): 子树经历 display:none → visible 时 CSS 动画会
 * 重新播放 (切回 Tab 重复动画)。onAnimationEnd 后移除动画并定格最终状态。
 */
export function CompleteIcon({ size = 16, className }: CompleteIconProps) {
  const [played, setPlayed] = useState(false);
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
        style={played ? { animation: "none", strokeDashoffset: 0 } : undefined}
        onAnimationEnd={() => setPlayed(true)}
        pathLength={100}
        d="M7.5 12.5 L10.5 15.5 L16.5 9.5"
      />
    </svg>
  );
}
