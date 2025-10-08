import { Component, ReactNode } from 'react';
import './ErrorBoundary.css';

interface ErrorBoundaryProps {
  children: ReactNode;
  fallback?: (error: Error, errorInfo: string, retry: () => void) => ReactNode;
}

interface ErrorBoundaryState {
  hasError: boolean;
  error: Error | null;
  errorInfo: string;
}

export class ErrorBoundary extends Component<ErrorBoundaryProps, ErrorBoundaryState> {
  constructor(props: ErrorBoundaryProps) {
    super(props);
    this.state = {
      hasError: false,
      error: null,
      errorInfo: '',
    };
  }

  static getDerivedStateFromError(error: Error): Partial<ErrorBoundaryState> {
    return { hasError: true, error };
  }

  componentDidCatch(error: Error, errorInfo: { componentStack: string }) {
    console.error('ErrorBoundary caught an error:', error, errorInfo);
    this.setState({
      errorInfo: errorInfo.componentStack,
    });
  }

  handleRetry = () => {
    this.setState({
      hasError: false,
      error: null,
      errorInfo: '',
    });
  };

  render() {
    if (this.state.hasError && this.state.error) {
      if (this.props.fallback) {
        return this.props.fallback(this.state.error, this.state.errorInfo, this.handleRetry);
      }
      return (
        <PageErrorFallback
          error={this.state.error}
          errorInfo={this.state.errorInfo}
          onRetry={this.handleRetry}
        />
      );
    }

    return this.props.children;
  }
}

interface PageErrorFallbackProps {
  error: Error;
  errorInfo: string;
  onRetry: () => void;
}

export function PageErrorFallback({ error, errorInfo, onRetry }: PageErrorFallbackProps) {
  return (
    <div className="error-fallback" role="alert">
      <div className="error-fallback-content">
        <div className="error-fallback-icon">
          <svg width="48" height="48" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
            <circle cx="12" cy="12" r="10" />
            <line x1="12" y1="8" x2="12" y2="12" />
            <line x1="12" y1="16" x2="12.01" y2="16" />
          </svg>
        </div>
        <h2 className="error-fallback-title">Something went wrong</h2>
        <p className="error-fallback-message">
          An unexpected error occurred while rendering this page. You can try reloading or return to the home page.
        </p>
        {import.meta.env.DEV && (
          <details className="error-fallback-details">
            <summary>Error details (development only)</summary>
            <pre className="error-fallback-stack">
              {error.toString()}
              {errorInfo && `\n\nComponent Stack:${errorInfo}`}
            </pre>
          </details>
        )}
        <div className="error-fallback-actions">
          <button
            type="button"
            onClick={onRetry}
            className="button button-primary"
          >
            Retry
          </button>
          <a href="/" className="button button-secondary">
            Go Home
          </a>
        </div>
      </div>
    </div>
  );
}
