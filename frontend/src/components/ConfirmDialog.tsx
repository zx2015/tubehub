/**
 * ConfirmDialog — 通用确认弹窗（仿 AddDownloadDialog 浮动窗口风格）
 *
 * 设计依据：docs/design/04-frontend-components.md §4.7
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
        className={`confirm-dialog${danger ? ' confirm-dialog--danger' : ''}`}
        onClick={(e) => e.stopPropagation()}
      >
        {/* 标题栏 + 关闭按钮 */}
        <div className="confirm-dialog__header">
          <h2 className="confirm-dialog__title">{title}</h2>
          <button
            type="button"
            className="confirm-dialog__close"
            onClick={onCancel}
            aria-label="关闭"
          >
            ✕
          </button>
        </div>

        {/* 消息正文 */}
        <div className="confirm-dialog__body">
          <p className="confirm-dialog__message">{message}</p>
        </div>

        {/* 操作按钮 */}
        <div className="confirm-dialog__actions">
          <button type="button" className="btn btn--ghost" onClick={onCancel}>
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
