import { useMemo } from 'react';
import { usePatStatus } from '../../../hooks/usePatStatus';
import { formatTimestamp } from '../../../utils/time';

type CredentialItem = {
  label: string;
  configured: boolean;
  updatedAt: string | null;
  updatedBy: string | null;
};

function CredentialBanner() {
  const { status, isLoading, error, lastRefreshedAt } = usePatStatus();

  const credentialItems: CredentialItem[] = useMemo(
    () => [
      {
        label: 'GitLab PAT',
        configured: status.configured,
        updatedAt: status.updated_at,
        updatedBy: status.updated_by,
      },
      {
        label: 'ChatGPT Session',
        configured: status.session_configured,
        updatedAt: status.session_updated_at,
        updatedBy: status.session_updated_by,
      },
    ],
    [status.configured, status.updated_at, status.updated_by, status.session_configured, status.session_updated_at, status.session_updated_by],
  );

  const hasAllCredentials = credentialItems.every((item) => item.configured);
  const verificationMessage = useMemo(() => {
    if (!status.verification_status) {
      return null;
    }
    if (status.verification_status === 'error') {
      return status.verification_error
        ? `PAT verification failed: ${status.verification_error}`
        : 'PAT verification failed.';
    }
    return `PAT verified against ${status.verification_host ?? 'GitLab'} at ${formatTimestamp(status.verification_checked_at)}`;
  }, [status.verification_status, status.verification_error, status.verification_host, status.verification_checked_at]);

  return (
    <section className="panel credential-banner" aria-busy={isLoading ? 'true' : 'false'}>
      <div className="panel-header">
        <h3>Credential Status</h3>
        {lastRefreshedAt && <span className="panel-meta">Refreshed {formatTimestamp(lastRefreshedAt)}</span>}
      </div>
      {error && (
        <div className="error-banner" role="alert">
          {error}
        </div>
      )}
      <div className="credential-banner-grid">
        {credentialItems.map((item) => (
          <div
            key={item.label}
            className={`credential-banner-item${item.configured ? ' credential-banner-item-ok' : ' credential-banner-item-warning'}`}
          >
            <p className="credential-banner-label">{item.label}</p>
            <p className="credential-banner-status">{item.configured ? 'Configured' : 'Missing'}</p>
            {item.updatedAt && (
              <p className="credential-banner-meta">
                Updated {formatTimestamp(item.updatedAt)}
                {item.updatedBy ? ` by ${item.updatedBy}` : ''}
              </p>
            )}
          </div>
        ))}
      </div>
      {!hasAllCredentials && (
        <p className="credential-banner-hint">
          Configure missing credentials before dispatching new work so tasks can push branches and reach the Codex API.
        </p>
      )}
      {verificationMessage && <p className="credential-banner-verify">{verificationMessage}</p>}
    </section>
  );
}

export default CredentialBanner;
