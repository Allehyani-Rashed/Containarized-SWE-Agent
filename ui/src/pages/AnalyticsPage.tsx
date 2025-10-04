import { ReactNode, useEffect, useState } from 'react';
import Card from '../components/Card';
import StatusBadge from '../components/StatusBadge';
import Icon from '../components/Icon';
import PieChart from '../components/PieChart';
import BarChart from '../components/BarChart';
import LineChart, { LineChartData } from '../components/LineChart';
import Skeleton from '../components/Skeleton';
import './AnalyticsPage.css';

// Mock data matching PDF design
const mockMetrics = {
  totalTasks: { value: 247, change: 12 },
  successRate: { value: 89, change: 3 },
  avgDuration: { value: '24m', change: -5 },
  activeProjects: { value: 4, change: 1 },
};

const taskDistribution = [
  { label: 'Completed', count: 185, color: 'success', percentage: 75 },
  { label: 'Running', count: 3, color: 'running', percentage: 1 },
  { label: 'Pending', count: 12, color: 'pending', percentage: 5 },
  { label: 'Failed', count: 27, color: 'failed', percentage: 11 },
  { label: 'Aborted', count: 20, color: 'aborted', percentage: 8 },
];

const modelUsage = [
  { label: 'GPT 5 Codex High', count: 142, color: 'blue', percentage: 58 },
  { label: 'GPT 5 Codex Medium', count: 68, color: 'green', percentage: 28 },
  { label: 'GPT 5 Codex Low', count: 25, color: 'purple', percentage: 10 },
];

// Color mappings for charts
const statusColors: Record<string, string> = {
  success: '#10b981',
  running: '#3b82f6',
  pending: '#f59e0b',
  failed: '#ef4444',
  aborted: '#6b7280',
};

const modelColors: Record<string, string> = {
  blue: '#3b82f6',
  green: '#10b981',
  purple: '#a855f7',
  orange: '#fb923c',
};

// Tasks over time (last 7 days)
const tasksOverTime: LineChartData[] = [
  { label: 'Mon', value: 28 },
  { label: 'Tue', value: 35 },
  { label: 'Wed', value: 42 },
  { label: 'Thu', value: 38 },
  { label: 'Fri', value: 51 },
  { label: 'Sat', value: 33 },
  { label: 'Sun', value: 20 },
];

// Success rate trend (last 7 days)
const successRateTrend: LineChartData[] = [
  { label: 'Mon', value: 85 },
  { label: 'Tue', value: 88 },
  { label: 'Wed', value: 92 },
  { label: 'Thu', value: 87 },
  { label: 'Fri', value: 90 },
  { label: 'Sat', value: 91 },
  { label: 'Sun', value: 89 },
];

const apiStatus = [
  { label: 'FastAPI Backend', status: 'Online', statusType: 'online' as const },
  { label: 'Database', status: 'Connected', statusType: 'online' as const },
  { label: 'Redis Cache', status: 'Active', statusType: 'active' as const },
];

const performanceMetrics = [
  { label: 'CPU Usage', value: 23, color: 'blue' },
  { label: 'Memory Usage', value: 67, color: 'yellow' },
  { label: 'Disk Usage', value: 45, color: 'green' },
  { label: 'Network I/O', value: 12, color: 'blue' },
];

function ProgressBar({ percentage, color }: { percentage: number; color: string }) {
  return (
    <div className="analytics-progress-bar">
      <div
        className={`analytics-progress-fill analytics-progress-${color}`}
        style={{ width: `${percentage}%` }}
      />
    </div>
  );
}

function MetricCard({
  icon,
  iconColor,
  value,
  label,
  change,
}: {
  icon: ReactNode;
  iconColor: 'blue' | 'green' | 'purple' | 'orange';
  value: string | number;
  label: string;
  change: number;
}) {
  const changeSign = change >= 0 ? '+' : '';
  const changeClass = change >= 0 ? 'positive' : 'negative';

  return (
    <Card className="analytics-metric-card">
      <div className={`analytics-metric-icon analytics-metric-icon-${iconColor}`}>
        <span className="analytics-icon-text">{icon}</span>
      </div>
      <div className="analytics-metric-value">{value}</div>
      <div className="analytics-metric-label">{label}</div>
      <div className="analytics-metric-progress">
        <ProgressBar
          percentage={change >= 0 ? 80 : 60}
          color={iconColor}
        />
        <span className={`analytics-metric-change analytics-metric-change-${changeClass}`}>
          {changeSign}{change}%
        </span>
      </div>
    </Card>
  );
}

function AnalyticsPage() {
  const [isLoading, setIsLoading] = useState(true);

  // Simulate loading data
  useEffect(() => {
    const timer = setTimeout(() => {
      setIsLoading(false);
    }, 800);
    return () => clearTimeout(timer);
  }, []);

  if (isLoading) {
    return (
      <div className="analytics-page">
        <div className="analytics-header">
          <h1 className="analytics-title">Analytics & Insights</h1>
          <p className="analytics-subtitle">
            Monitor performance, usage patterns, and system health metrics
          </p>
        </div>

        {/* Skeleton Metric Cards */}
        <div className="analytics-metrics-grid">
          {Array.from({ length: 4 }).map((_, index) => (
            <Card key={index} className="analytics-metric-card">
              <div style={{ display: 'flex', flexDirection: 'column', gap: '0.75rem' }}>
                <Skeleton variant="circle" width={48} height={48} />
                <Skeleton variant="title" width="60%" />
                <Skeleton variant="text" width="40%" />
                <Skeleton variant="rectangle" height={8} />
              </div>
            </Card>
          ))}
        </div>

        {/* Skeleton Charts */}
        <div className="analytics-two-col">
          <Card>
            <Skeleton variant="title" width="50%" />
            <div style={{ marginTop: '1.5rem' }}>
              <Skeleton variant="rectangle" height={240} />
            </div>
          </Card>
          <Card>
            <Skeleton variant="title" width="50%" />
            <div style={{ marginTop: '1.5rem' }}>
              <Skeleton variant="rectangle" height={240} />
            </div>
          </Card>
        </div>

        {/* Skeleton Trends */}
        <div className="analytics-trends-grid">
          <Card>
            <Skeleton variant="title" width="60%" />
            <Skeleton variant="text" width="80%" />
            <div style={{ marginTop: '1.5rem' }}>
              <Skeleton variant="rectangle" height={200} />
            </div>
          </Card>
          <Card>
            <Skeleton variant="title" width="60%" />
            <Skeleton variant="text" width="80%" />
            <div style={{ marginTop: '1.5rem' }}>
              <Skeleton variant="rectangle" height={200} />
            </div>
          </Card>
        </div>

        {/* Skeleton Health */}
        <Card>
          <Skeleton variant="title" width="40%" />
          <Skeleton variant="text" width="70%" />
          <div style={{ marginTop: '1.5rem', display: 'grid', gap: '1.5rem', gridTemplateColumns: 'repeat(auto-fit, minmax(280px, 1fr))' }}>
            {Array.from({ length: 3 }).map((_, index) => (
              <div key={index} style={{ display: 'flex', flexDirection: 'column', gap: '0.75rem' }}>
                <Skeleton variant="title" width="50%" />
                <Skeleton variant="text" width="80%" />
                <Skeleton variant="text" width="70%" />
                <Skeleton variant="text" width="60%" />
              </div>
            ))}
          </div>
        </Card>
      </div>
    );
  }

  return (
    <div className="analytics-page">
      <div className="analytics-header">
        <h1 className="analytics-title">Analytics & Insights</h1>
        <p className="analytics-subtitle">
          Monitor performance, usage patterns, and system health metrics
        </p>
      </div>

      {/* System Health Metrics Cards */}
      <div className="analytics-metrics-grid">
        <MetricCard
          icon={<Icon type="clipboard" size={24} />}
          iconColor="blue"
          value={mockMetrics.totalTasks.value}
          label="Total Tasks"
          change={mockMetrics.totalTasks.change}
        />
        <MetricCard
          icon={<Icon type="check" size={24} />}
          iconColor="green"
          value={`${mockMetrics.successRate.value}%`}
          label="Success Rate"
          change={mockMetrics.successRate.change}
        />
        <MetricCard
          icon={<Icon type="clock" size={24} />}
          iconColor="purple"
          value={mockMetrics.avgDuration.value}
          label="Avg Duration"
          change={mockMetrics.avgDuration.change}
        />
        <MetricCard
          icon={<Icon type="folder" size={24} />}
          iconColor="orange"
          value={mockMetrics.activeProjects.value}
          label="Active Projects"
          change={mockMetrics.activeProjects.change}
        />
      </div>

      {/* Two-column section: Task Distribution & Model Usage */}
      <div className="analytics-two-col">
        {/* Task Status Distribution */}
        <Card className="analytics-distribution-card">
          <h2 className="analytics-card-title">Task Status Distribution</h2>
          <div className="analytics-chart-wrapper">
            <PieChart
              data={taskDistribution.map(item => ({
                label: item.label,
                value: item.count,
                color: statusColors[item.color],
              }))}
              size={240}
              donut
            />
          </div>
          <div className="analytics-distribution-legend">
            {taskDistribution.map((item) => (
              <div key={item.label} className="analytics-legend-item">
                <span className={`analytics-status-dot analytics-status-dot-${item.color}`} />
                <span className="analytics-legend-label">{item.label}</span>
                <span className="analytics-legend-count">{item.count}</span>
              </div>
            ))}
          </div>
        </Card>

        {/* Model Usage */}
        <Card className="analytics-model-card">
          <h2 className="analytics-card-title">Model Usage</h2>
          <div className="analytics-chart-wrapper">
            <BarChart
              data={modelUsage.map(item => ({
                label: item.label,
                value: item.count,
                color: modelColors[item.color],
              }))}
              orientation="horizontal"
              height={240}
              showValues
            />
          </div>
        </Card>
      </div>

      {/* Task Trends Section */}
      <div className="analytics-trends-grid">
        <Card className="analytics-trend-card">
          <h2 className="analytics-card-title">Tasks Over Time</h2>
          <p className="analytics-card-subtitle">Daily task submissions over the last week</p>
          <div className="analytics-chart-wrapper">
            <LineChart
              data={tasksOverTime}
              color="#3b82f6"
              height={200}
              showDots
              showGrid
              fillArea
            />
          </div>
        </Card>

        <Card className="analytics-trend-card">
          <h2 className="analytics-card-title">Success Rate Trend</h2>
          <p className="analytics-card-subtitle">Task success rate percentage over the last week</p>
          <div className="analytics-chart-wrapper">
            <LineChart
              data={successRateTrend}
              color="#10b981"
              height={200}
              showDots
              showGrid
              fillArea
            />
          </div>
        </Card>
      </div>

      {/* System Health Section */}
      <Card className="analytics-health-card">
        <h2 className="analytics-card-title">System Health</h2>
        <p className="analytics-card-subtitle">
          Real-time monitoring of system components and performance metrics
        </p>

        <div className="analytics-health-grid">
          {/* API Status */}
          <div className="analytics-health-section">
            <div className="analytics-health-section-header">
              <div className="analytics-health-icon analytics-health-icon-green">
                <span><Icon type="plug" size={24} /></span>
              </div>
              <h3 className="analytics-health-section-title">API Status</h3>
            </div>
            <div className="analytics-health-items">
              {apiStatus.map((item) => (
                <div key={item.label} className="analytics-health-item">
                  <span className="analytics-health-item-label">{item.label}</span>
                  <StatusBadge status={item.statusType} label={item.status} dot size="small" />
                </div>
              ))}
            </div>
          </div>

          {/* Performance */}
          <div className="analytics-health-section">
            <div className="analytics-health-section-header">
              <div className="analytics-health-icon analytics-health-icon-blue">
                <span><Icon type="chart" size={24} /></span>
              </div>
              <h3 className="analytics-health-section-title">Performance</h3>
            </div>
            <div className="analytics-health-items">
              {performanceMetrics.map((item) => (
                <div key={item.label} className="analytics-performance-item">
                  <div className="analytics-performance-label-row">
                    <span className="analytics-performance-label">{item.label}</span>
                    <span className="analytics-performance-value">{item.value}%</span>
                  </div>
                  <ProgressBar percentage={item.value} color={item.color} />
                </div>
              ))}
            </div>
          </div>

          {/* Alerts */}
          <div className="analytics-health-section">
            <div className="analytics-health-section-header">
              <div className="analytics-health-icon analytics-health-icon-purple">
                <span><Icon type="bell" size={24} /></span>
              </div>
              <h3 className="analytics-health-section-title">Alerts</h3>
            </div>
            <div className="analytics-health-items">
              <div className="analytics-alert-item analytics-alert-success">
                <div className="analytics-alert-icon"><Icon type="check" size={20} /></div>
                <div className="analytics-alert-content">
                  <div className="analytics-alert-title">All Systems Normal</div>
                  <div className="analytics-alert-message">No active alerts or warnings</div>
                </div>
              </div>
              <div className="analytics-alert-item analytics-alert-info">
                <div className="analytics-alert-icon"><Icon type="info" size={20} /></div>
                <div className="analytics-alert-content">
                  <div className="analytics-alert-title">Cache Optimization</div>
                  <div className="analytics-alert-message">
                    Cache hit rate at 94% - excellent performance
                  </div>
                </div>
              </div>
            </div>
          </div>
        </div>
      </Card>

      {/* User Badge - Bottom Left Corner */}
      <div className="analytics-user-badge">
        <div className="analytics-user-avatar">OP</div>
        <div className="analytics-user-info">
          <div className="analytics-user-name">Operator</div>
          <StatusBadge status="online" label="Online" dot size="small" />
        </div>
      </div>
    </div>
  );
}

export default AnalyticsPage;
