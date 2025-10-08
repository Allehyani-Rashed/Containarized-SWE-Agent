import { onCLS, onFCP, onINP, onLCP, onTTFB, Metric } from 'web-vitals';

type VitalsCallback = (metric: Metric) => void;

const isDevelopment = import.meta.env.DEV;

// Log metrics to console in development
function logMetric(metric: Metric) {
  const { name, value, rating } = metric;
  const ratingEmoji = rating === 'good' ? '✅' : rating === 'needs-improvement' ? '⚠️' : '❌';

  console.log(
    `${ratingEmoji} Web Vital: ${name}`,
    `\n  Value: ${Math.round(value)}ms`,
    `\n  Rating: ${rating}`,
    `\n  Details:`, metric
  );
}

// Optional: Send metrics to analytics endpoint
function sendToAnalytics(metric: Metric) {
  // Only send in production if you have an analytics endpoint configured
  if (!isDevelopment && import.meta.env.VITE_ANALYTICS_ENDPOINT) {
    const body = JSON.stringify(metric);

    // Use sendBeacon if available (doesn't block page unload)
    if (navigator.sendBeacon) {
      navigator.sendBeacon(import.meta.env.VITE_ANALYTICS_ENDPOINT, body);
    } else {
      // Fallback to fetch
      fetch(import.meta.env.VITE_ANALYTICS_ENDPOINT, {
        method: 'POST',
        body,
        headers: { 'Content-Type': 'application/json' },
        keepalive: true,
      }).catch(() => {
        // Silently fail - analytics should not break the app
      });
    }
  }
}

function handleMetric(metric: Metric) {
  // Always log in development
  if (isDevelopment) {
    logMetric(metric);
  }

  // Optionally send to analytics
  sendToAnalytics(metric);
}

export function measureWebVitals(callback?: VitalsCallback) {
  const metricHandler = callback || handleMetric;

  try {
    onCLS(metricHandler);
    onFCP(metricHandler);
    onINP(metricHandler); // INP replaced FID in web-vitals v3+
    onLCP(metricHandler);
    onTTFB(metricHandler);
  } catch (error) {
    // Silently fail - web vitals measurement should not break the app
    console.error('Failed to measure web vitals:', error);
  }
}
