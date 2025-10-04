import { ReactNode } from 'react';
import './StatusBadge.css';

export type StatusType =
  | 'pending'
  | 'running'
  | 'done'
  | 'failed'
  | 'aborted'
  | 'active'
  | 'error'
  | 'idle'
  | 'verified'
  | 'configured'
  | 'missing'
  | 'selected'
  | 'online'
  | 'offline';

export interface StatusBadgeProps {
  status: StatusType;
  label?: string;
  icon?: ReactNode;
  dot?: boolean;
  size?: 'small' | 'medium' | 'large';
}

function StatusBadge({ status, label, icon, dot = false, size = 'medium' }: StatusBadgeProps) {
  const displayLabel = label || status.charAt(0).toUpperCase() + status.slice(1);

  return (
    <span className={`status-badge status-badge-${status} status-badge-${size}`}>
      {dot && <span className="status-badge-dot"></span>}
      {icon && <span className="status-badge-icon">{icon}</span>}
      <span className="status-badge-label">{displayLabel}</span>
    </span>
  );
}

export default StatusBadge;
