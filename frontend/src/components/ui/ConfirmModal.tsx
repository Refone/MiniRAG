import { useEffect, useId, useRef, type ReactNode } from "react";

interface ConfirmModalProps {
  title: string;
  children: ReactNode;
  confirmText?: string;
  cancelText?: string;
  /** 确认按钮忙碌态文案（如 "删除中..."） */
  busyText?: string;
  busy?: boolean;
  onConfirm: () => void;
  onCancel: () => void;
}

/** 确认弹窗（自文档管理页删除确认弹窗抽出） */
export function ConfirmModal({
  title,
  children,
  confirmText = "确认删除",
  cancelText = "取消",
  busyText = "处理中...",
  busy = false,
  onConfirm,
  onCancel,
}: ConfirmModalProps) {
  const titleId = useId();
  const cancelRef = useRef<HTMLButtonElement>(null);

  // 破坏性操作默认聚焦「取消」，避免回车误确认
  useEffect(() => {
    cancelRef.current?.focus();
  }, []);

  useEffect(() => {
    const onKeyDown = (e: KeyboardEvent) => {
      if (e.key !== "Escape") return;
      if (!busy) onCancel();
    };
    document.addEventListener("keydown", onKeyDown);
    return () => document.removeEventListener("keydown", onKeyDown);
  }, [busy, onCancel]);

  return (
    <div className="modal-mask">
      <div
        className="modal"
        role="dialog"
        aria-modal="true"
        aria-labelledby={titleId}
      >
        <h3 id={titleId}>{title}</h3>
        {children}
        <div className="modal-actions">
          <button
            className="btn"
            type="button"
            ref={cancelRef}
            disabled={busy}
            onClick={onCancel}
          >
            {cancelText}
          </button>
          <button
            className="btn primary"
            type="button"
            disabled={busy}
            onClick={onConfirm}
          >
            {busy ? busyText : confirmText}
          </button>
        </div>
      </div>
    </div>
  );
}
