import React, { useState } from 'react';
import './BarChart.css';
import EmptyState from './EmptyState';

export interface BarChartData {
  label: string;
  value: number;
  color: string;
}

interface BarChartProps {
  data: BarChartData[];
  orientation?: 'horizontal' | 'vertical';
  height?: number;
  showValues?: boolean;
  animate?: boolean;
}

function BarChart({
  data,
  orientation = 'horizontal',
  height = 300,
  showValues = true,
  animate = true
}: BarChartProps) {
  const [activeIndex, setActiveIndex] = useState<number | null>(null);

  // Guard against empty or null data
  if (!data || data.length === 0) {
    return (
      <EmptyState
        icon="chart"
        title="No data available"
        description="There is no data to display in this chart."
      />
    );
  }

  const maxValue = Math.max(...data.map(d => d.value));
  const minValue = Math.min(...data.map(d => d.value));

  // Keyboard navigation handler
  const handleKeyDown = (e: React.KeyboardEvent, index: number) => {
    if (e.key === 'ArrowRight' || e.key === 'ArrowDown') {
      e.preventDefault();
      const nextIndex = Math.min(index + 1, data.length - 1);
      const nextElement = document.querySelector(`[data-bar-index="${nextIndex}"]`) as HTMLElement;
      nextElement?.focus();
    } else if (e.key === 'ArrowLeft' || e.key === 'ArrowUp') {
      e.preventDefault();
      const prevIndex = Math.max(index - 1, 0);
      const prevElement = document.querySelector(`[data-bar-index="${prevIndex}"]`) as HTMLElement;
      prevElement?.focus();
    }
  };

  if (orientation === 'horizontal') {
    return (
      <div
        className="bar-chart-container bar-chart-horizontal"
        style={{ height: `${height}px` }}
        role="img"
        aria-label={`Bar chart showing ${data.length} items with values ranging from ${minValue} to ${maxValue}`}
      >
        {data.map((item, index) => {
          const percentage = (item.value / maxValue) * 100;
          const isActive = activeIndex === index;

          return (
            <div
              key={item.label}
              className={`bar-chart-item ${isActive ? 'active' : ''}`}
              onMouseEnter={() => setActiveIndex(index)}
              onMouseLeave={() => setActiveIndex(null)}
              onFocus={() => setActiveIndex(index)}
              onBlur={() => setActiveIndex(null)}
              onKeyDown={(e) => handleKeyDown(e, index)}
              tabIndex={0}
              role="button"
              aria-label={`${item.label}: ${item.value}`}
              data-bar-index={index}
            >
              <div className="bar-chart-label">{item.label}</div>
              <div className="bar-chart-bar-wrapper">
                <div
                  className={`bar-chart-bar ${animate ? 'animate' : ''}`}
                  style={{
                    '--bar-width': `${percentage}%`,
                    backgroundColor: item.color,
                    animationDelay: `${index * 0.1}s`,
                  } as React.CSSProperties}
                >
                  {showValues && (
                    <span className="bar-chart-value">{item.value}</span>
                  )}
                </div>
              </div>
            </div>
          );
        })}
      </div>
    );
  }

  // Vertical orientation
  return (
    <div
      className="bar-chart-container bar-chart-vertical"
      style={{ height: `${height}px` }}
      role="img"
      aria-label={`Vertical bar chart showing ${data.length} items with values ranging from ${minValue} to ${maxValue}`}
    >
      <div className="bar-chart-bars">
        {data.map((item, index) => {
          const percentage = (item.value / maxValue) * 100;
          const isActive = activeIndex === index;

          return (
            <div
              key={item.label}
              className={`bar-chart-column ${isActive ? 'active' : ''}`}
              onMouseEnter={() => setActiveIndex(index)}
              onMouseLeave={() => setActiveIndex(null)}
              onFocus={() => setActiveIndex(index)}
              onBlur={() => setActiveIndex(null)}
              onKeyDown={(e) => handleKeyDown(e, index)}
              tabIndex={0}
              role="button"
              aria-label={`${item.label}: ${item.value}`}
              data-bar-index={index}
            >
              {showValues && (
                <div className="bar-chart-value-top">{item.value}</div>
              )}
              <div className="bar-chart-column-wrapper">
                <div
                  className={`bar-chart-column-bar ${animate ? 'animate' : ''}`}
                  style={{
                    '--bar-height': `${percentage}%`,
                    backgroundColor: item.color,
                    animationDelay: `${index * 0.1}s`,
                  } as React.CSSProperties}
                />
              </div>
              <div className="bar-chart-column-label">{item.label}</div>
            </div>
          );
        })}
      </div>
    </div>
  );
}

export default BarChart;
