import { ReactNode, MouseEvent, KeyboardEvent } from 'react';
import './Card.css';

export interface CardProps {
  children: ReactNode;
  className?: string;
  variant?: 'default' | 'icon' | 'status';
  icon?: ReactNode;
  iconColor?: 'blue' | 'green' | 'orange' | 'purple' | 'red' | 'cyan';
  statusIndicator?: ReactNode;
  onClick?: () => void;
}

function Card({
  children,
  className = '',
  variant = 'default',
  icon,
  iconColor = 'blue',
  statusIndicator,
  onClick,
}: CardProps) {
  const baseClass = 'card';
  const variantClass = variant !== 'default' ? `card-${variant}` : '';
  const clickableClass = onClick ? 'card-clickable' : '';
  const combinedClass = [baseClass, variantClass, clickableClass, className]
    .filter(Boolean)
    .join(' ');

  const handleClick = onClick
    ? (e: MouseEvent) => {
        e.preventDefault();
        onClick();
      }
    : undefined;

  const handleKeyDown = onClick
    ? (e: KeyboardEvent) => {
        if (e.key === 'Enter' || e.key === ' ') {
          e.preventDefault();
          onClick();
        }
      }
    : undefined;

  return (
    <div
      className={combinedClass}
      onClick={handleClick}
      onKeyDown={handleKeyDown}
      role={onClick ? 'button' : undefined}
      tabIndex={onClick ? 0 : undefined}
    >
      {variant === 'icon' && icon && (
        <div className={`icon-wrapper icon-${iconColor}`}>
          {icon}
        </div>
      )}
      {variant === 'status' && statusIndicator && (
        <div className="card-status-indicator">{statusIndicator}</div>
      )}
      <div className="card-content">{children}</div>
    </div>
  );
}

export default Card;
