import React from 'react';
import './Skeleton.css';

export type SkeletonVariant = 'text' | 'title' | 'rectangle' | 'circle' | 'table-row';

export interface SkeletonProps {
  variant?: SkeletonVariant;
  width?: string | number;
  height?: string | number;
  count?: number;
  className?: string;
}

function Skeleton({
  variant = 'text',
  width,
  height,
  count = 1,
  className = '',
}: SkeletonProps) {
  const getSkeletonStyle = () => {
    const style: React.CSSProperties = {};

    if (width) {
      style.width = typeof width === 'number' ? `${width}px` : width;
    }

    if (height) {
      style.height = typeof height === 'number' ? `${height}px` : height;
    }

    return style;
  };

  const renderSkeleton = (key: number) => {
    if (variant === 'table-row') {
      return (
        <tr key={key} className="skeleton-table-row">
          {Array.from({ length: 11 }).map((_, cellIndex) => (
            <td key={cellIndex}>
              <span
                className="skeleton skeleton-text"
                style={{ width: `${Math.max(32, 85 - cellIndex * 6)}%` }}
              />
            </td>
          ))}
        </tr>
      );
    }

    return (
      <span
        key={key}
        className={`skeleton skeleton-${variant} ${className}`}
        style={getSkeletonStyle()}
      />
    );
  };

  if (count === 1) {
    return renderSkeleton(0);
  }

  return (
    <>
      {Array.from({ length: count }, (_, index) => renderSkeleton(index))}
    </>
  );
}

export default Skeleton;
