import { ChangeEvent, FormEvent, useMemo, useRef, useState } from 'react';
import {
  clearPat,
  clearSession,
  importSession,
  storePat,
  verifyPat,
} from '../api/integrations';
import { formatTimestamp } from '../utils/time';
import { usePatStatus } from '../hooks/usePatStatus';

type PatFormState = {
  token: string;
  actor: string;
};

type SessionFormState = {
  bundle: string;
  actor: string;
};

const initialPatForm: PatFormState = {
  token: '',
  actor: '',
};

const initialSessionForm: SessionFormState = {
  bundle: '',
  actor: '',
};

function SettingsPage() {
  const {
    status: patStatus,
    updateStatus,
    error: patStatusError,
    clearError: clearPatStatusError,
    lastRefreshedAt: patStatusRefreshedAt,
  } = usePatStatus();
  const [patForm, setPatForm] = useState(initialPatForm);
  const [patMessage, setPatMessage] = useState<string | null>(null);
  const [patSubmitting, setPatSubmitting] = useState(false);
  const [verifyMessage, setVerifyMessage] = useState<string | null>(null);
  const [verifyResult, setVerifyResult] = useState<'success' | 'error' | null>(null);
  const [verifySubmitting, setVerifySubmitting] = useState(false);
  const [clearModalOpen, setClearModalOpen] = useState(false);
  const [clearSubmitting, setClearSubmitting] = useState(false);
  const [clearActor, setClearActor] = useState('');

  const [sessionForm, setSessionForm] = useState(initialSessionForm);
  const [sessionMessage, setSessionMessage] = useState<string | null>(null);
  const [sessionSubmitting, setSessionSubmitting] = useState(false);
  const [sessionFileName, setSessionFileName] = useState<string | null>(null);
  const [sessionClearSubmitting, setSessionClearSubmitting] = useState(false);
  const [sessionClearActor, setSessionClearActor] = useState('');
  const [sessionClearModalOpen, setSessionClearModalOpen] = useState(false);

  const [error, setError] = useState<string | null>(null);
  const sessionFileRequestIdRef = useRef(0);

  const combinedError = error ?? patStatusError;

  const activeCredentialLabel = useMemo(() => {
    switch (patStatus.active_credential) {
      case 'api_token':
        return 'Agent API token';
      case 'session':
        return 'ChatGPT session bundle';
      default:
        return 'None';
    }
  }, [patStatus.active_credential]);


  const handlePatStore = async (event: FormEvent<HTMLFormElement>) => {
    event.preventDefault();
    if (!patForm.token.trim()) {
      setError('Token is required to store the PAT');
      return;
    }
    setPatSubmitting(true);
    setPatMessage(null);
    setSessionMessage(null);
    setError(null);
    clearPatStatusError();
    setVerifyMessage(null);
    setVerifyResult(null);
    try {
      const payload = {
        token: patForm.token.trim(),
        updated_by: patForm.actor.trim() ? patForm.actor.trim() : null,
      };
      const data = await storePat(payload);
      updateStatus(data);
      setPatForm(initialPatForm);
      setPatMessage('Personal access token stored successfully.');
    } catch (apiError) {
      setError(apiError instanceof Error ? apiError.message : 'Failed to store the PAT');
    } finally {
      setPatSubmitting(false);
    }
  };

  const handlePatClear = async () => {
    setClearSubmitting(true);
    setPatMessage(null);
    setSessionMessage(null);
    setError(null);
    clearPatStatusError();
    setVerifyMessage(null);
    setVerifyResult(null);
    try {
      const payload = clearActor.trim() ? { updated_by: clearActor.trim() } : {};
      const data = await clearPat(payload);
      updateStatus(data);
      setPatMessage('Personal access token cleared. Tasks will fail until a new token is configured.');
      setClearActor('');
      setClearModalOpen(false);
      setPatForm(initialPatForm);
    } catch (apiError) {
      setError(apiError instanceof Error ? apiError.message : 'Failed to clear the PAT');
    } finally {
      setClearSubmitting(false);
    }
  };

  const handlePatVerify = async () => {
    setVerifySubmitting(true);
    setVerifyMessage(null);
    setVerifyResult(null);
    setPatMessage(null);
    setSessionMessage(null);
    setError(null);
    clearPatStatusError();
    try {
      const payload: { gitlab_host?: string } = {};
      if (patStatus.verification_host) {
        payload.gitlab_host = patStatus.verification_host;
      }
      const data = await verifyPat(payload);
      updateStatus(data);

      if (data.verification_status === 'verified') {
        const hostLabel = data.verification_host ?? 'GitLab';
        setVerifyResult('success');
        setVerifyMessage(`PAT verified against ${hostLabel}.`);
      } else {
        const fallbackMessage =
          data.verification_error ?? 'Verification completed but the result was inconclusive.';
        setVerifyResult('error');
        setVerifyMessage(fallbackMessage);
      }
    } catch (apiError) {
      const message = apiError instanceof Error ? apiError.message : 'Unable to verify GitLab PAT';
      setVerifyResult('error');
      setVerifyMessage(message);
      setError(message);
    } finally {
      setVerifySubmitting(false);
    }
  };

  const handleSessionImport = async (event: FormEvent<HTMLFormElement>) => {
    event.preventDefault();
    if (!sessionForm.bundle.trim()) {
      setError('Session bundle content is required');
      return;
    }
    setSessionSubmitting(true);
    setSessionMessage(null);
    setPatMessage(null);
    setError(null);
    clearPatStatusError();
    try {
      const payload = {
        bundle: sessionForm.bundle,
        updated_by: sessionForm.actor.trim() ? sessionForm.actor.trim() : null,
      };
      const data = await importSession(payload);
      updateStatus(data);
      setSessionForm(initialSessionForm);
      setSessionFileName(null);
      setSessionMessage('ChatGPT session bundle imported successfully.');
    } catch (apiError) {
      setError(apiError instanceof Error ? apiError.message : 'Failed to import ChatGPT session bundle');
    } finally {
      setSessionSubmitting(false);
    }
  };

  const handleSessionFile = (event: ChangeEvent<HTMLInputElement>) => {
    const input = event.target;
    const file = input.files && input.files[0];
    if (!file) {
      return;
    }

    const requestId = sessionFileRequestIdRef.current + 1;
    sessionFileRequestIdRef.current = requestId;
    setSessionMessage(null);
    setError(null);

    const reader = new FileReader();
    reader.onload = () => {
      if (sessionFileRequestIdRef.current !== requestId) {
        input.value = '';
        return;
      }
      const result = typeof reader.result === 'string' ? reader.result : '';
      setSessionForm((prev) => ({ ...prev, bundle: result }));
      setSessionFileName(file.name);
      input.value = '';
    };
    reader.onerror = () => {
      if (sessionFileRequestIdRef.current !== requestId) {
        input.value = '';
        return;
      }
      setError(`Failed to read ${file.name}`);
      input.value = '';
    };
    reader.readAsText(file);
  };

  const handleSessionClear = async () => {
    setSessionClearSubmitting(true);
    setSessionMessage(null);
    setPatMessage(null);
    setError(null);
    clearPatStatusError();
    try {
      const payload = sessionClearActor.trim() ? { updated_by: sessionClearActor.trim() } : {};
      const data = await clearSession(payload);
      updateStatus(data);
      setSessionMessage('ChatGPT session bundle cleared. Import a fresh bundle to continue.');
      setSessionForm(initialSessionForm);
      setSessionFileName(null);
      setSessionClearActor('');
      setSessionClearModalOpen(false);
    } catch (apiError) {
      setError(apiError instanceof Error ? apiError.message : 'Failed to clear the ChatGPT session bundle');
    } finally {
      setSessionClearSubmitting(false);
    }
  };

  return (
    <div className="page">
      <header className="page-header">
        <h2>Credentials & Integrations</h2>
        <p>Manage GitLab PATs and agent session bundles for the runner environment.</p>
      </header>

      {combinedError && <div className="error-banner">{combinedError}</div>}
      {patMessage && <div className="notice notice-success">{patMessage}</div>}
      {sessionMessage && <div className="notice notice-success">{sessionMessage}</div>}
      {verifyMessage && (
        <div className={`notice ${verifyResult === 'success' ? 'notice-success' : 'notice-warning'}`}>
          {verifyMessage}
        </div>
      )}

      <section className="panel">
        <h3>Credential Overview</h3>
        <div className="credential-summary">
          <div className="summary-row">
            <span>GitLab PAT</span>
            <span
              className={patStatus.configured ? 'status status-done' : 'status status-failed'}
              title="GitLab PATs are write-only; we only track whether a token is stored for this environment"
            >
              {patStatus.configured ? 'Configured' : 'Missing'}
            </span>
          </div>
          <div className="summary-meta">
            <span>Last update: {formatTimestamp(patStatus.updated_at)}</span>
            <span>Updated by: {patStatus.updated_by ? patStatus.updated_by : '--'}</span>
          </div>
          <div className="summary-row">
            <span>PAT Verification</span>
            <span
              className={
                patStatus.verification_status === 'verified'
                  ? 'status status-done'
                  : patStatus.verification_status === 'error'
                  ? 'status status-failed'
                  : 'status status-pending'
              }
              title="Use Verify PAT access to confirm connectivity without exposing the token"
            >
              {patStatus.verification_status === 'verified'
                ? 'Verified'
                : patStatus.verification_status === 'error'
                ? 'Check failed'
                : 'Not run'}
            </span>
          </div>
          <div className="summary-meta">
            <span>Last check: {formatTimestamp(patStatus.verification_checked_at)}</span>
            <span>Target host: {patStatus.verification_host ? patStatus.verification_host : '--'}</span>
          </div>
          {patStatus.verification_status === 'error' && patStatus.verification_error ? (
            <p className="pat-hint pat-hint-error">Last verification failed: {patStatus.verification_error}</p>
          ) : null}
          <div className="summary-row">
            <span>ChatGPT Session</span>
            <span className={patStatus.session_configured ? 'status status-done' : 'status status-failed'}>
              {patStatus.session_configured ? 'Configured' : 'Missing'}
            </span>
          </div>
          <div className="summary-meta">
            <span>Last import: {formatTimestamp(patStatus.session_updated_at)}</span>
            <span>Updated by: {patStatus.session_updated_by ? patStatus.session_updated_by : '--'}</span>
          </div>
          <div className="summary-meta">
            <span>Active credential: {activeCredentialLabel}</span>
            <span>Status refreshed: {formatTimestamp(patStatusRefreshedAt)}</span>
          </div>
        </div>
        {!patStatus.configured && (
          <div className="notice notice-warning">
            <strong>GitLab PAT required.</strong>{' '}
            Provide a project-scoped personal access token with API access.{' '}
            <a
              href="https://github.com/openai/codex/tree/main/docs/authentication.md#gitlab-personal-access-tokens"
              target="_blank"
              rel="noreferrer"
            >
              Review the PAT troubleshooting guide
            </a>
            .
          </div>
        )}
        <p className="pat-hint">
          GitLab PATs are write-only; we encrypt the token and never render the secret after storage.
        </p>
        <p className="pat-hint">
          Status labels reflect this environment. Clearing secrets or switching machines shows “Missing” until you store a new token.
        </p>
      </section>

      <section className="panel">
        <h3>GitLab Personal Access Token</h3>
        <div className="credential-forms">
          <form className="form pat-form" onSubmit={handlePatStore}>
            <label>
              New Token
              <input
                type="password"
                value={patForm.token}
                onChange={(event) => setPatForm({ ...patForm, token: event.target.value })}
                placeholder="glpat-..."
                required
              />
            </label>
            <label>
              Stored By (optional)
              <input
                type="text"
                value={patForm.actor}
                onChange={(event) => setPatForm({ ...patForm, actor: event.target.value })}
                placeholder="operator name"
              />
            </label>
            <button type="submit" disabled={patSubmitting}>
              {patSubmitting ? 'Storing...' : 'Store Token'}
            </button>
          </form>
          <div className="credential-block">
            <button type="button" onClick={handlePatVerify} disabled={verifySubmitting || !patStatus.configured}>
              {verifySubmitting ? 'Verifying...' : 'Verify PAT access'}
            </button>
            <button
              type="button"
              className="danger-button"
              onClick={() => {
                setPatMessage(null);
                setSessionMessage(null);
                setError(null);
                setClearModalOpen(true);
              }}
              disabled={clearSubmitting || !patStatus.configured}
            >
              Clear PAT
            </button>
            <p className="pat-hint">
              Clearing the token aborts pending tasks and blocks new submissions until a replacement is provided.
            </p>
          </div>
        </div>
      </section>

      <section className="panel">
        <h3>ChatGPT Session Bundle</h3>
        <div className="credential-forms">
          <form className="form session-form" onSubmit={handleSessionImport}>
            <label>
              Session JSON
              <textarea
                value={sessionForm.bundle}
                onChange={(event) => setSessionForm({ ...sessionForm, bundle: event.target.value })}
                placeholder="Paste the contents of auth.json"
                rows={6}
                required
              />
            </label>
            <label className="session-file-label">
              Load from file
              <input type="file" accept=".json,application/json" onChange={handleSessionFile} />
            </label>
            {sessionFileName && <p className="file-hint">Loaded from {sessionFileName}</p>}
            <label>
              Imported By (optional)
              <input
                type="text"
                value={sessionForm.actor}
                onChange={(event) => setSessionForm({ ...sessionForm, actor: event.target.value })}
                placeholder="operator name"
              />
            </label>
            <button type="submit" disabled={sessionSubmitting}>
              {sessionSubmitting ? 'Importing...' : 'Import Session'}
            </button>
          </form>
          <div className="credential-block">
            <p className="pat-hint">
              Make sure your agent CLI is installed locally and that you are logged in before copying the session bundle.
            </p>
            <p className="pat-hint">
              macOS copy helper:<br />
              <code>cat ~/.codex/auth.json | pbcopy</code>
            </p>
            <p className="pat-hint">
              linux copy helper:<br />
              <code>cat ~/.codex/auth.json | xclip -selection clipboard</code>
            </p>
            <p className="pat-hint">
              windows copy helper:<br />
              <code>Get-Content $env:USERPROFILE\\.codex\\auth.json | Set-Clipboard</code>
            </p>
            <button
              type="button"
              className="danger-button"
              onClick={() => {
                setSessionMessage(null);
                setError(null);
                setSessionClearModalOpen(true);
              }}
              disabled={sessionClearSubmitting || !patStatus.session_configured}
            >
              Clear Session Bundle
            </button>
            <p className="pat-hint">
              Session bundles let Docker runs authenticate without an agent API key. Import fresh bundles after updating your credentials and clear them if they expire or are revoked.
            </p>
          </div>
        </div>
      </section>

      {clearModalOpen && (
        <div className="modal-backdrop" role="presentation">
          <div className="modal">
            <h3>Clear GitLab PAT?</h3>
            <p>
              Clearing the personal access token immediately fails any pending tasks and prevents new runs until a replacement token is configured. Running tasks continue with the credentials they already captured.
            </p>
            <label>
              Cleared By (optional)
              <input
                type="text"
                value={clearActor}
                onChange={(event) => setClearActor(event.target.value)}
                placeholder="operator name"
              />
            </label>
            <div className="modal-actions">
              <button
                type="button"
                className="ghost-button"
                onClick={() => {
                  setClearModalOpen(false);
                  setClearActor('');
                }}
                disabled={clearSubmitting}
              >
                Cancel
              </button>
              <button
                type="button"
                className="danger-button"
                onClick={() => {
                  void handlePatClear();
                }}
                disabled={clearSubmitting}
              >
                {clearSubmitting ? 'Clearing...' : 'Clear Token'}
              </button>
            </div>
          </div>
        </div>
      )}

      {sessionClearModalOpen && (
        <div className="modal-backdrop" role="presentation">
          <div className="modal">
            <h3>Clear ChatGPT Session Bundle?</h3>
            <p>
              Clearing the session bundle forces Docker tasks to rely on an agent API token. Import a fresh bundle after clearing to continue using session-based authentication.
            </p>
            <label>
              Cleared By (optional)
              <input
                type="text"
                value={sessionClearActor}
                onChange={(event) => setSessionClearActor(event.target.value)}
                placeholder="operator name"
              />
            </label>
            <div className="modal-actions">
              <button
                type="button"
                className="ghost-button"
                onClick={() => {
                  setSessionClearModalOpen(false);
                  setSessionClearActor('');
                }}
                disabled={sessionClearSubmitting}
              >
                Cancel
              </button>
              <button
                type="button"
                className="danger-button"
                onClick={() => {
                  void handleSessionClear();
                }}
                disabled={sessionClearSubmitting}
              >
                {sessionClearSubmitting ? 'Clearing...' : 'Clear Session'}
              </button>
            </div>
          </div>
        </div>
      )}
    </div>
  );
}

export default SettingsPage;
