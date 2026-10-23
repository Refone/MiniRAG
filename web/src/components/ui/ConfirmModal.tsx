import type { ReactNode } from "react";

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

/** 确认弹窗（自 ImportPage 删除确认弹窗抽出） */
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
  return (
    <div className="modal-mask">
      <div className="modal">
        <h3>{title}</h3>
        {children}
        <div className="modal-actions">
          <button
            className="btn"
            type="button"
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
