import { useState } from "react";

interface StatusIconProps {
  kind: "loading" | "done" | "failed";
  size?: number;
  className?: string;
}

/**
 * 状态图标（合并原 CompleteIcon / FailedIcon / LoadingIcon）：
 * - done / failed：勾叉绘制动画，播放一次后保持。Session-MVVM 修正 (BUG-001):
 *   子树经历 display:none → visible 时 CSS 动画会重新播放 (切回 Tab 重复动画)。
 *   onAnimationEnd 后移除动画并定格最终状态。
 * - loading：无限循环旋转的加载动画。
 */
export function StatusIcon({ kind, size = 16, className }: StatusIconProps) {
  const [played, setPlayed] = useState(false);
  const cls = `status-icon status-icon-${
    kind === "loading" ? "loading" : kind === "done" ? "complete" : "failed"
  }${className ? ` ${className}` : ""}`;

  if (kind === "loading") {
    return (
      <svg
        className={cls}
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

  return (
    <svg
      className={cls}
      width={size}
      height={size}
      viewBox="0 0 24 24"
      fill="none"
      aria-hidden="true"
    >
      <circle
        className={
          kind === "done"
            ? "status-icon-complete__ring"
            : "status-icon-failed__ring"
        }
        cx="12"
        cy="12"
        r="10"
      />
      <path
        className={
          kind === "done"
            ? "status-icon-complete__check"
            : "status-icon-failed__cross"
        }
        style={played ? { animation: "none", strokeDashoffset: 0 } : undefined}
        onAnimationEnd={() => setPlayed(true)}
        pathLength={100}
        d={
          kind === "done"
            ? "M7.5 12.5 L10.5 15.5 L16.5 9.5"
            : "M8.5 8.5 L15.5 15.5 M15.5 8.5 L8.5 15.5"
        }
      />
    </svg>
  );
}
