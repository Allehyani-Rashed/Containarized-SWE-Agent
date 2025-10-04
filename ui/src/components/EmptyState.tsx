import { ReactNode } from 'react';
import Icon, { IconType } from './Icon';
import Button from './Button';
import './EmptyState.css';

export interface EmptyStateProps {
  icon?: IconType | ReactNode;
  title: string;
  description: string;
  actionLabel?: string;
  onAction?: () => void;
  className?: string;
}

function EmptyState({
  icon,
  title,
  description,
  actionLabel,
  onAction,
  className = '',
}: EmptyStateProps) {
  const renderIcon = () => {
    if (!icon) return null;

    if (typeof icon === 'string') {
      return <Icon type={icon as IconType} size={48} className="empty-state-icon-svg" />;
    }

    return <div className="empty-state-icon-custom">{icon}</div>;
  };

  return (
    <div className={`empty-state ${className}`}>
      {icon && <div className="empty-state-icon">{renderIcon()}</div>}
      <div className="empty-state-content">
        <h3 className="empty-state-title">{title}</h3>
        <p className="empty-state-description">{description}</p>
      </div>
      {actionLabel && onAction && (
        <div className="empty-state-action">
          <Button variant="primary" onClick={onAction}>
            {actionLabel}
          </Button>
        </div>
      )}
    </div>
  );
}

export default EmptyState;
