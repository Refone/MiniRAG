import type { ToastItem } from "@/types/app";

interface ToastProps {
  toasts: ToastItem[];
}

/** Toast 栈（左下角；自动消失由 store 计时，本组件纯展示） */
export function Toast({ toasts }: ToastProps) {
  return (
    <div className="toast-wrap">
      {toasts.map((t) => (
        <div
          key={t.id}
          className={`toast${
            t.kind === "success" ? " success" : t.kind === "error" ? " error" : ""
          }`}
        >
          <span className="toast-dot" />
          <span>{t.text}</span>
        </div>
      ))}
    </div>
  );
}
