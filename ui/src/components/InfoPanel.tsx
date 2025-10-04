import { ReactNode } from 'react';
import './InfoPanel.css';

export interface InfoPanelProps {
  title: string;
  icon?: ReactNode;
  iconColor?: 'blue' | 'green' | 'orange' | 'purple' | 'red' | 'cyan';
  children: ReactNode;
  statusIndicator?: ReactNode;
  actions?: ReactNode;
  variant?: 'default' | 'success' | 'warning' | 'error' | 'info';
  className?: string;
}

function InfoPanel({
  title,
  icon,
  iconColor = 'blue',
  children,
  statusIndicator,
  actions,
  variant = 'default',
  className = '',
}: InfoPanelProps) {
  const baseClass = 'info-panel';
  const variantClass = variant !== 'default' ? `info-panel-${variant}` : '';
  const combinedClass = [baseClass, variantClass, className].filter(Boolean).join(' ');

  return (
    <div className={combinedClass}>
      <div className="info-panel-header">
        <div className="info-panel-header-main">
          {icon && <div className={`info-panel-icon info-panel-icon-${iconColor}`}>{icon}</div>}
          <h3 className="info-panel-title">{title}</h3>
        </div>
        {statusIndicator && <div className="info-panel-status">{statusIndicator}</div>}
      </div>
      <div className="info-panel-content">{children}</div>
      {actions && <div className="info-panel-actions">{actions}</div>}
    </div>
  );
}

export default InfoPanel;

// InfoItem component for key-value pairs inside InfoPanel
export interface InfoItemProps {
  label: string;
  value: ReactNode;
  className?: string;
}

export function InfoItem({ label, value, className = '' }: InfoItemProps) {
  return (
    <div className={`info-item ${className}`}>
      <dt className="info-item-label">{label}</dt>
      <dd className="info-item-value">{value}</dd>
    </div>
  );
}

// InfoList component for multiple InfoItems
export interface InfoListProps {
  children: ReactNode;
  columns?: 1 | 2 | 3;
  className?: string;
}

export function InfoList({ children, columns = 1, className = '' }: InfoListProps) {
  return <dl className={`info-list info-list-cols-${columns} ${className}`}>{children}</dl>;
}
