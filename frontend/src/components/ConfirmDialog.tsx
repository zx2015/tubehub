/**
 * ConfirmDialog — 通用确认弹窗
 *
 * 设计依据：docs/design/04-frontend-components.md §4.7
 *
 * 行为：
 *  - 通过 props 控制 open / 标题 / 描述 / 确认按钮文案
 *  - onConfirm / onCancel 回调由父组件处理
 */
interface ConfirmDialogProps {
  open: boolean;
  title: string;
  message: string;
  confirmText?: string;
  cancelText?: string;
  danger?: boolean;
  onConfirm: () => void;
  onCancel: () => void;
}

export function ConfirmDialog({
  open,
  title,
  message,
  confirmText = '确认',
  cancelText = '取消',
  danger = false,
  onConfirm,
  onCancel,
}: ConfirmDialogProps) {
  if (!open) return null;

  return (
    <div
      className="confirm-dialog__backdrop"
      role="dialog"
      aria-modal="true"
      onClick={onCancel}
    >
      <div
        className="confirm-dialog"
        onClick={(e) => e.stopPropagation()}
      >
        <h2 className="confirm-dialog__title">{title}</h2>
        <p className="confirm-dialog__message">{message}</p>
        <div className="confirm-dialog__actions">
          <button
            type="button"
            className="btn btn--ghost"
            onClick={onCancel}
          >
            {cancelText}
          </button>
          <button
            type="button"
            className={danger ? 'btn btn--danger' : 'btn btn--primary'}
            onClick={onConfirm}
          >
            {confirmText}
          </button>
        </div>
      </div>
    </div>
  );
}

export default ConfirmDialog;