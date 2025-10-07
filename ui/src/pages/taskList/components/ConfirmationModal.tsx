import { ReactNode, useRef } from 'react';
import { useFocusTrap } from '../../../hooks/useFocusTrap';

type ConfirmationModalProps = {
  open: boolean;
  title: string;
  description: ReactNode;
  confirmLabel: string;
  cancelLabel?: string;
  confirmVariant?: 'danger' | 'secondary';
  isLoading?: boolean;
  onConfirm: () => void;
  onCancel: () => void;
  idSuffix?: string;
};

const confirmClassNameByVariant: Record<'danger' | 'secondary', string> = {
  danger: 'danger-button',
  secondary: 'secondary-button',
};

function ConfirmationModal({
  open,
  title,
  description,
  confirmLabel,
  cancelLabel = 'Cancel',
  confirmVariant = 'danger',
  isLoading = false,
  onConfirm,
  onCancel,
  idSuffix = 'confirmation',
}: ConfirmationModalProps) {
  const modalRef = useRef<HTMLDivElement | null>(null);
  const confirmButtonRef = useRef<HTMLButtonElement | null>(null);

  const titleId = `${idSuffix}-title`;
  const descriptionId = `${idSuffix}-description`;

  useFocusTrap(modalRef, open, confirmButtonRef);

  if (!open) {
    return null;
  }

  return (
    <div className="drawer-modal" role="presentation">
      <div
        className="drawer-modal-card"
        role="alertdialog"
        aria-modal="true"
        aria-labelledby={titleId}
        aria-describedby={descriptionId}
        ref={modalRef}
      >
        <h4 id={titleId}>{title}</h4>
        <p id={descriptionId}>{description}</p>
        <div className="drawer-modal-actions">
          <button
            type="button"
            className={confirmClassNameByVariant[confirmVariant]}
            onClick={onConfirm}
            disabled={isLoading}
            ref={confirmButtonRef}
          >
            {isLoading ? 'Working…' : confirmLabel}
          </button>
          <button type="button" className="ghost-button" onClick={onCancel} disabled={isLoading}>
            {cancelLabel}
          </button>
        </div>
      </div>
    </div>
  );
}

export default ConfirmationModal;
