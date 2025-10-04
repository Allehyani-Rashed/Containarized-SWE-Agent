import React, { useState } from 'react';
import './PieChart.css';
import EmptyState from './EmptyState';

export interface PieChartData {
  label: string;
  value: number;
  color: string;
}

interface PieChartProps {
  data: PieChartData[];
  size?: number;
  donut?: boolean;
}

function PieChart({ data, size = 200, donut = true }: PieChartProps) {
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

  const total = data.reduce((sum, item) => sum + item.value, 0);

  // Guard against division by zero when all values are 0
  if (total === 0) {
    return (
      <EmptyState
        icon="chart"
        title="No data to display"
        description="All values are zero. Add some data to see the chart."
      />
    );
  }
  const centerX = size / 2;
  const centerY = size / 2;
  const radius = size / 2 - 10;
  const innerRadius = donut ? radius * 0.6 : 0;

  let currentAngle = -90; // Start from top

  const segments = data.map((item, index) => {
    const percentage = (item.value / total) * 100;
    const angle = (item.value / total) * 360;
    const startAngle = currentAngle;
    const endAngle = currentAngle + angle;

    currentAngle = endAngle;

    const isActive = activeIndex === index;
    const offset = isActive ? 5 : 0;

    // Calculate arc path
    const start = polarToCartesian(centerX, centerY, radius + offset, startAngle);
    const end = polarToCartesian(centerX, centerY, radius + offset, endAngle);
    const largeArcFlag = angle > 180 ? 1 : 0;

    let path: string;
    if (donut) {
      const innerStart = polarToCartesian(centerX, centerY, innerRadius + offset, startAngle);
      const innerEnd = polarToCartesian(centerX, centerY, innerRadius + offset, endAngle);

      path = [
        `M ${start.x} ${start.y}`,
        `A ${radius + offset} ${radius + offset} 0 ${largeArcFlag} 1 ${end.x} ${end.y}`,
        `L ${innerEnd.x} ${innerEnd.y}`,
        `A ${innerRadius + offset} ${innerRadius + offset} 0 ${largeArcFlag} 0 ${innerStart.x} ${innerStart.y}`,
        'Z',
      ].join(' ');
    } else {
      path = [
        `M ${centerX} ${centerY}`,
        `L ${start.x} ${start.y}`,
        `A ${radius + offset} ${radius + offset} 0 ${largeArcFlag} 1 ${end.x} ${end.y}`,
        'Z',
      ].join(' ');
    }

    return {
      path,
      color: item.color,
      label: item.label,
      value: item.value,
      percentage: percentage.toFixed(1),
      index,
    };
  });

  // Generate descriptive aria-label
  const chartDescription = `${donut ? 'Donut' : 'Pie'} chart with ${data.length} segments showing a total of ${total}. Breakdown: ${data.map(d => {
    const pct = ((d.value / total) * 100).toFixed(1);
    return `${d.label}: ${d.value} (${pct}%)`;
  }).join(', ')}`;

  return (
    <div
      className="pie-chart-container"
      role="img"
      aria-label={chartDescription}
    >
      <svg
        width={size}
        height={size}
        viewBox={`0 0 ${size} ${size}`}
        className="pie-chart-svg"
        aria-hidden="true"
      >
        {segments.map((segment) => (
          <path
            key={segment.index}
            d={segment.path}
            fill={segment.color}
            className={`pie-chart-segment ${activeIndex === segment.index ? 'active' : ''}`}
            onMouseEnter={() => setActiveIndex(segment.index)}
            onMouseLeave={() => setActiveIndex(null)}
          >
            <title>{`${segment.label}: ${segment.value} (${segment.percentage}%)`}</title>
          </path>
        ))}

        {donut && (
          <text
            x={centerX}
            y={centerY}
            textAnchor="middle"
            dominantBaseline="middle"
            className="pie-chart-center-text"
          >
            <tspan x={centerX} dy="-0.2em" className="pie-chart-total-label">Total</tspan>
            <tspan x={centerX} dy="1.2em" className="pie-chart-total-value">{total}</tspan>
          </text>
        )}
      </svg>

      {activeIndex !== null && (
        <div className="pie-chart-tooltip">
          <div className="pie-chart-tooltip-label">{segments[activeIndex].label}</div>
          <div className="pie-chart-tooltip-value">
            {segments[activeIndex].value} ({segments[activeIndex].percentage}%)
          </div>
        </div>
      )}
    </div>
  );
}

function polarToCartesian(
  centerX: number,
  centerY: number,
  radius: number,
  angleInDegrees: number
): { x: number; y: number } {
  const angleInRadians = (angleInDegrees * Math.PI) / 180;
  return {
    x: centerX + radius * Math.cos(angleInRadians),
    y: centerY + radius * Math.sin(angleInRadians),
  };
}

export default PieChart;
