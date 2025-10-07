import { useEffect, useMemo, useState } from 'react';
import { getConcurrencySettings } from '../../../api/settings';
import { Project, ConcurrencySettings } from '../../../types';
import { formatTimestamp } from '../../../utils/time';
import { computeConcurrencyBannerState } from '../taskSelectors';

type ConcurrencyBannerProps = {
  projects: Project[];
};

function ConcurrencyBanner({ projects }: ConcurrencyBannerProps) {
  const [settings, setSettings] = useState<ConcurrencySettings | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [isLoading, setIsLoading] = useState<boolean>(true);

  useEffect(() => {
    let cancelled = false;

    const loadSettings = async () => {
      try {
        const snapshot = await getConcurrencySettings();
        if (!cancelled) {
          setSettings(snapshot);
          setError(null);
        }
      } catch (apiError) {
        if (!cancelled) {
          setError(apiError instanceof Error ? apiError.message : 'Failed to load concurrency settings');
        }
      } finally {
        if (!cancelled) {
          setIsLoading(false);
        }
      }
    };

    void loadSettings();

    return () => {
      cancelled = true;
    };
  }, []);

  const bannerState = useMemo(() => computeConcurrencyBannerState(projects, settings), [projects, settings]);
  const projectsAtLimitNames = useMemo(
    () => bannerState.projectsAtLimit.map((project) => project.name).join(', '),
    [bannerState.projectsAtLimit],
  );

  return (
    <section className="panel concurrency-banner" aria-busy={isLoading ? 'true' : 'false'}>
      <div className="panel-header">
        <h3>Concurrency & Worker Pool</h3>
        {settings?.updated_at && <span className="panel-meta">Updated {formatTimestamp(settings.updated_at)}</span>}
      </div>
      {error && (
        <div className="error-banner" role="alert">
          {error}
        </div>
      )}
      <div className="concurrency-banner-grid">
        <div>
          <p className="concurrency-banner-label">Project Limit</p>
          <p className="concurrency-banner-value">
            {bannerState.effectiveLimit ? `${bannerState.effectiveLimit} concurrent tasks` : 'Unlimited'}
          </p>
        </div>
        <div>
          <p className="concurrency-banner-label">Active Tasks</p>
          <p className="concurrency-banner-value">{bannerState.totalActive}</p>
        </div>
        <div>
          <p className="concurrency-banner-label">Parallel Pool</p>
          <p className="concurrency-banner-value">{settings?.parallel_enabled ? 'Enabled' : 'Disabled'}</p>
        </div>
        <div>
          <p className="concurrency-banner-label">Worker Slots</p>
          <p className="concurrency-banner-value">{settings?.worker_pool_size ?? '--'}</p>
        </div>
      </div>
      {bannerState.projectsAtLimit.length > 0 && (
        <p className="concurrency-banner-warning" role="status">
          Project limit reached for {projectsAtLimitNames}. New tasks queue until slots free up.
        </p>
      )}
    </section>
  );
}

export default ConcurrencyBanner;
