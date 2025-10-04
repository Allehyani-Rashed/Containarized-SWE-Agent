import React, { useState } from 'react';
import './LineChart.css';
import EmptyState from './EmptyState';

export interface LineChartData {
  label: string;
  value: number;
}

interface LineChartProps {
  data: LineChartData[];
  color?: string;
  height?: number;
  showDots?: boolean;
  showGrid?: boolean;
  fillArea?: boolean;
}

function LineChart({
  data,
  color = '#3b82f6',
  height = 200,
  showDots = true,
  showGrid = true,
  fillArea = true,
}: LineChartProps) {
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
  const range = maxValue - minValue || 1;

  const padding = 40;
  const chartWidth = 100;
  const chartHeight = 100;
  const stepX = chartWidth / (data.length - 1 || 1);

  // Calculate points
  const points = data.map((item, index) => {
    const x = index * stepX;
    const y = chartHeight - ((item.value - minValue) / range) * chartHeight;
    return { x, y, value: item.value, label: item.label };
  });

  // Create SVG path
  const linePath = points.map((point, index) => {
    const command = index === 0 ? 'M' : 'L';
    return `${command} ${point.x} ${point.y}`;
  }).join(' ');

  // Create area path
  const areaPath = fillArea
    ? `${linePath} L ${points[points.length - 1].x} ${chartHeight} L 0 ${chartHeight} Z`
    : '';

  // Grid lines
  const gridLines = showGrid ? [0, 25, 50, 75, 100] : [];

  // Generate descriptive aria-label
  const chartDescription = `Line chart with ${data.length} data points. Values range from ${minValue} to ${maxValue}. Data points: ${data.map(d => `${d.label}: ${d.value}`).join(', ')}`;

  return (
    <div
      className="line-chart-container"
      style={{ height: `${height}px` }}
      role="img"
      aria-label={chartDescription}
    >
      <svg
        viewBox={`0 0 ${chartWidth + padding * 2} ${chartHeight + padding * 2}`}
        className="line-chart-svg"
        preserveAspectRatio="xMidYMid meet"
        aria-hidden="true"
      >
        <defs>
          <linearGradient id="lineChartGradient" x1="0%" y1="0%" x2="0%" y2="100%">
            <stop offset="0%" stopColor={color} stopOpacity="0.3" />
            <stop offset="100%" stopColor={color} stopOpacity="0.05" />
          </linearGradient>
        </defs>

        <g transform={`translate(${padding}, ${padding})`}>
          {/* Grid lines */}
          {gridLines.map((y) => (
            <line
              key={`grid-${y}`}
              x1="0"
              y1={y}
              x2={chartWidth}
              y2={y}
              className="line-chart-grid-line"
            />
          ))}

          {/* Area fill */}
          {fillArea && (
            <path
              d={areaPath}
              fill="url(#lineChartGradient)"
              className="line-chart-area"
            />
          )}

          {/* Line */}
          <path
            d={linePath}
            fill="none"
            stroke={color}
            strokeWidth="2"
            strokeLinecap="round"
            strokeLinejoin="round"
            className="line-chart-line"
          />

          {/* Dots */}
          {showDots && points.map((point, index) => {
            const isActive = activeIndex === index;
            return (
              <circle
                key={point.label}
                cx={point.x}
                cy={point.y}
                r={isActive ? 5 : 3}
                fill={color}
                className={`line-chart-dot ${isActive ? 'active' : ''}`}
                onMouseEnter={() => setActiveIndex(index)}
                onMouseLeave={() => setActiveIndex(null)}
                style={{ animationDelay: `${index * 0.05}s` }}
              >
                <title>{`${point.label}: ${point.value}`}</title>
              </circle>
            );
          })}

          {/* X-axis labels */}
          {data.map((item, index) => {
            const point = points[index];
            const showLabel = data.length <= 7 || index % Math.ceil(data.length / 7) === 0;

            return showLabel ? (
              <text
                key={item.label}
                x={point.x}
                y={chartHeight + 15}
                textAnchor="middle"
                className="line-chart-x-label"
              >
                {item.label}
              </text>
            ) : null;
          })}
        </g>
      </svg>

      {activeIndex !== null && (
        <div
          className="line-chart-tooltip"
          style={{
            left: `${(points[activeIndex].x / chartWidth) * 100}%`,
          }}
        >
          <div className="line-chart-tooltip-label">{points[activeIndex].label}</div>
          <div className="line-chart-tooltip-value">{points[activeIndex].value}</div>
        </div>
      )}
    </div>
  );
}

export default LineChart;
