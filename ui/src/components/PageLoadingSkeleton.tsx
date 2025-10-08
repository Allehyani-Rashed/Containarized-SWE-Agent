import './PageLoadingSkeleton.css';

export default function PageLoadingSkeleton() {
  return (
    <div className="page-loading-skeleton">
      <div className="skeleton-header"></div>
      <div className="skeleton-content">
        <div className="skeleton-line"></div>
        <div className="skeleton-line"></div>
        <div className="skeleton-line short"></div>
      </div>
    </div>
  );
}
