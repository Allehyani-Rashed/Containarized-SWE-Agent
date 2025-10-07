import ConfirmationModal from './ConfirmationModal';

type QuickAbortModalProps = {
  taskId: number | null;
  isLoading: boolean;
  onConfirm: (taskId: number) => void;
  onCancel: () => void;
};

function QuickAbortModal({ taskId, isLoading, onConfirm, onCancel }: QuickAbortModalProps) {
  if (!taskId) {
    return null;
  }

  const handleConfirm = () => {
    onConfirm(taskId);
  };

  return (
    <div className="task-drawer" role="presentation" onClick={onCancel}>
      <div className="task-drawer-backdrop" aria-hidden="true" />
      <div role="presentation" onClick={(event) => event.stopPropagation()}>
        <ConfirmationModal
          open
          title={`Abort Task #${taskId}?`}
          description="The task will be terminated. Currently running operations will complete before stopping. This cannot be undone."
          confirmLabel="Confirm abort"
          isLoading={isLoading}
          onConfirm={handleConfirm}
          onCancel={onCancel}
          idSuffix="quick-abort"
        />
      </div>
    </div>
  );
}

export default QuickAbortModal;
