import { ChangeEvent, FormEvent, useEffect, useRef, useState } from 'react';
import {
  clearPat,
  clearSession,
  importSession,
  storePat,
  verifyPat,
} from '../api/integrations';
import { getConcurrencySettings, updateConcurrencySettings } from '../api/settings';
import { formatTimestamp } from '../utils/time';
import { ConcurrencySettings } from '../types';
import { usePatStatus } from '../hooks/usePatStatus';
import Card from '../components/Card';
import Button from '../components/Button';
import { TextInput, TextArea } from '../components/Input';
import { InfoItem, InfoList } from '../components/InfoPanel';
import StatusBadge from '../components/StatusBadge';
import Icon from '../components/Icon';
import './SettingsPage.css';

type PatFormState = {
  token: string;
};

type SessionFormState = {
  bundle: string;
};

const initialPatForm: PatFormState = {
  token: '',
};

const initialSessionForm: SessionFormState = {
  bundle: '',
};

function SettingsPage() {
  const {
    status: patStatus,
    updateStatus,
    error: patStatusError,
    clearError: clearPatStatusError,
  } = usePatStatus();
  const [patForm, setPatForm] = useState(initialPatForm);
  const [patMessage, setPatMessage] = useState<string | null>(null);
  const [patSubmitting, setPatSubmitting] = useState(false);
  const [verifyMessage, setVerifyMessage] = useState<string | null>(null);
  const [verifyResult, setVerifyResult] = useState<'success' | 'error' | null>(null);
  const [verifySubmitting, setVerifySubmitting] = useState(false);
  const [clearModalOpen, setClearModalOpen] = useState(false);
  const [clearSubmitting, setClearSubmitting] = useState(false);

  const [sessionForm, setSessionForm] = useState(initialSessionForm);
  const [sessionMessage, setSessionMessage] = useState<string | null>(null);
  const [sessionSubmitting, setSessionSubmitting] = useState(false);
  const [sessionFileName, setSessionFileName] = useState<string | null>(null);
  const [sessionClearSubmitting, setSessionClearSubmitting] = useState(false);
  const [sessionClearModalOpen, setSessionClearModalOpen] = useState(false);

  const [concurrencySettings, setConcurrencySettings] = useState<ConcurrencySettings | null>(null);
  const [concurrencyForm, setConcurrencyForm] = useState({ projectLimit: '' });
  const [concurrencyMessage, setConcurrencyMessage] = useState<string | null>(null);
  const [concurrencyError, setConcurrencyError] = useState<string | null>(null);
  const [concurrencyLoading, setConcurrencyLoading] = useState(false);
  const [concurrencySubmitting, setConcurrencySubmitting] = useState(false);

  const [error, setError] = useState<string | null>(null);
  const sessionFileRequestIdRef = useRef(0);

  const combinedError = error ?? patStatusError;

  const allCredentialsVerified =
    patStatus.configured &&
    patStatus.session_configured &&
    patStatus.verification_status === 'verified';

  const needsSetup = !patStatus.configured || !patStatus.session_configured;

  useEffect(() => {
    let cancelled = false;

    const loadConcurrency = async () => {
      setConcurrencyLoading(true);
      setConcurrencyError(null);
      try {
        const data = await getConcurrencySettings();
        if (!cancelled) {
          setConcurrencySettings(data);
          setConcurrencyForm((prev) => ({
            ...prev,
            projectLimit: String(data.project_limit),
          }));
        }
      } catch (apiError) {
        if (!cancelled) {
          const message = apiError instanceof Error ? apiError.message : 'Failed to load concurrency settings';
          setConcurrencyError(message);
        }
      } finally {
        if (!cancelled) {
          setConcurrencyLoading(false);
        }
      }
    };

    void loadConcurrency();

    return () => {
      cancelled = true;
    };
  }, []);


  const handleConcurrencyInputChange = (event: ChangeEvent<HTMLInputElement>) => {
    const { name, value } = event.target;
    setConcurrencyForm((prev) => ({ ...prev, [name]: value }));
  };

  const handleConcurrencySubmit = async (event: FormEvent<HTMLFormElement>) => {
    event.preventDefault();
    setConcurrencyError(null);
    setConcurrencyMessage(null);

    const limitValue = concurrencyForm.projectLimit.trim();
    if (!limitValue) {
      setConcurrencyError('Project limit is required');
      return;
    }

    const parsedLimit = Number(limitValue);
    if (!Number.isInteger(parsedLimit) || parsedLimit < 1) {
      setConcurrencyError('Project limit must be a positive integer');
      return;
    }

    setConcurrencySubmitting(true);
    try {
      const payload = { project_limit: parsedLimit };
      const updated = await updateConcurrencySettings(payload);
      setConcurrencySettings(updated);
      setConcurrencyForm({ projectLimit: String(updated.project_limit) });
      setConcurrencyMessage('Concurrency limit updated successfully.');
    } catch (apiError) {
      const message = apiError instanceof Error ? apiError.message : 'Failed to update concurrency settings';
      setConcurrencyError(message);
    } finally {
      setConcurrencySubmitting(false);
    }
  };


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
      const data = await clearPat({});
      updateStatus(data);
      setPatMessage('Personal access token cleared. Tasks will fail until a new token is configured.');
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
      const data = await clearSession({});
      updateStatus(data);
      setSessionMessage('ChatGPT session bundle cleared. Import a fresh bundle to continue.');
      setSessionForm(initialSessionForm);
      setSessionFileName(null);
      setSessionClearModalOpen(false);
    } catch (apiError) {
      setError(apiError instanceof Error ? apiError.message : 'Failed to clear the ChatGPT session bundle');
    } finally {
      setSessionClearSubmitting(false);
    }
  };

  return (
    <div className="layout-page">

      {/* Page-Level Banners */}
      {needsSetup && (
        <div className="info-banner info-banner-info">
          <Icon type="alert" size={20} />
          <div>
            <strong>Quick Setup Required</strong>
            <p>
              {!patStatus.configured && !patStatus.session_configured
                ? 'Configure both GitLab PAT and ChatGPT Session Bundle to get started'
                : !patStatus.configured
                ? 'GitLab PAT is required to submit tasks and create merge requests'
                : 'ChatGPT Session Bundle is required for Docker-backed agent runs'}
            </p>
          </div>
        </div>
      )}

      {allCredentialsVerified && (
        <div className="success-banner">
          <Icon type="check-circle" size={20} />
          <div>
            <strong>All Credentials Verified</strong>
            <p>Your GitLab PAT and ChatGPT session are properly configured and verified</p>
          </div>
        </div>
      )}

      {combinedError && <div className="error-banner">{combinedError}</div>}
      {patMessage && <div className="alert alert-success">{patMessage}</div>}
      {sessionMessage && <div className="alert alert-success">{sessionMessage}</div>}
      {verifyMessage && (
        <div className={`alert ${verifyResult === 'success' ? 'alert-success' : 'alert-warning'}`}>
          {verifyMessage}
        </div>
      )}

      {/* Settings Layout - 3-Column Grid */}
      <div className="settings-grid-3col">
        {/* GitLab Personal Access Token Card */}
        <Card>
          <div className="credential-card-header">
            <h3>GitLab Personal Access Token</h3>
            <StatusBadge
              status={patStatus.configured ? 'configured' : 'missing'}
              size="small"
            />
          </div>

          <InfoList columns={1}>
            <InfoItem label="Last Update" value={formatTimestamp(patStatus.updated_at)} />
            <InfoItem
              label="Verification"
              value={
                <StatusBadge
                  status={
                    patStatus.verification_status === 'verified'
                      ? 'verified'
                      : patStatus.verification_status === 'error'
                      ? 'error'
                      : 'pending'
                  }
                  label={
                    patStatus.verification_status === 'verified'
                      ? 'Verified'
                      : patStatus.verification_status === 'error'
                      ? 'Failed'
                      : 'Not run'
                  }
                  size="small"
                />
              }
            />
            <InfoItem label="Host" value={patStatus.verification_host || '--'} />
          </InfoList>

          <form className="credential-form" onSubmit={handlePatStore}>
            <TextInput
              label="Personal Access Token"
              type="password"
              value={patForm.token}
              onChange={(e) => setPatForm({ ...patForm, token: e.target.value })}
              placeholder="glpat-xxxxxxxxxxxxxxxxxxxx"
              hint="Required scopes: api, read_user, read_repository"
              required
            />
            <div className="button-group">
              <Button
                variant="primary"
                type="submit"
                size="medium"
                disabled={patSubmitting}
              >
                {patSubmitting ? 'Storing...' : 'Store Token'}
              </Button>
              <Button
                variant="success"
                type="button"
                onClick={handlePatVerify}
                disabled={verifySubmitting || !patStatus.configured}
              >
                {verifySubmitting ? 'Verifying...' : 'Verify'}
              </Button>
            </div>
          </form>

          {patStatus.configured && (
            <div className="danger-zone">
              <Button
                variant="danger"
                type="button"
                onClick={() => {
                  setPatMessage(null);
                  setSessionMessage(null);
                  setError(null);
                  setClearModalOpen(true);
                }}
                disabled={clearSubmitting}
              >
                Clear PAT
              </Button>
            </div>
          )}

          {patStatus.verification_status === 'error' && patStatus.verification_error && (
            <div className="credential-warning">
              <Icon type="alert" size={16} />
              <span>{patStatus.verification_error}</span>
            </div>
          )}
        </Card>

        {/* ChatGPT Session Bundle Card */}
        <Card>
          <div className="credential-card-header">
            <h3>ChatGPT Session Bundle</h3>
            <StatusBadge
              status={patStatus.session_configured ? 'active' : 'missing'}
              size="small"
            />
          </div>

          <InfoList columns={1}>
            <InfoItem label="Last Refresh" value={formatTimestamp(patStatus.session_updated_at)} />
          </InfoList>

          <form className="credential-form" onSubmit={handleSessionImport}>
            <TextArea
              label="Session Bundle JSON"
              value={sessionForm.bundle}
              onChange={(e) => setSessionForm({ ...sessionForm, bundle: e.target.value })}
              placeholder='{"session_token": "...", "user_agent": "...", "cf_clearance": "..."}'
              rows={4}
              required
            />

            <div className="file-upload-group">
              <label className="file-upload-label">
                <span>Upload Bundle File</span>
                <input
                  type="file"
                  accept=".json,application/json"
                  onChange={handleSessionFile}
                  className="file-upload-input"
                />
                <span className="file-upload-button">Choose File</span>
                <span className="file-upload-name">
                  {sessionFileName || 'No file chosen'}
                </span>
              </label>
              {sessionFileName && <p className="file-hint">session_bundle.json</p>}
            </div>

            <div className="button-group">
              <Button
                variant="primary"
                type="submit"
                size="medium"
                disabled={sessionSubmitting}
              >
                {sessionSubmitting ? 'Importing...' : 'Import Session'}
              </Button>
            </div>
          </form>

          {patStatus.session_configured && (
            <div className="danger-zone">
              <Button
                variant="danger"
                type="button"
                onClick={() => {
                  setSessionMessage(null);
                  setError(null);
                  setSessionClearModalOpen(true);
                }}
                disabled={sessionClearSubmitting}
              >
                Clear Session
              </Button>
            </div>
          )}

          <div className="cli-hint">
            <h4>CLI Commands</h4>
            <p className="card-subtitle">macOS:</p>
            <code>pbpaste | jq . {'>'} session_bundle.json</code>
            <p className="card-subtitle">Linux:</p>
            <code>xclip -o -selection clipboard | jq . {'>'} session_bundle.json</code>
          </div>
        </Card>

        {/* Global Concurrency Card */}
        <Card className="concurrency-card">
            <h2>Global Concurrency</h2>
            <p className="card-subtitle">Set the per-project concurrency cap enforced by the worker.</p>
            {concurrencyError && <div className="error-banner">{concurrencyError}</div>}
            {concurrencyMessage && <div className="alert alert-success">{concurrencyMessage}</div>}
            <form className="concurrency-form" onSubmit={handleConcurrencySubmit}>
              <div className="concurrency-grid">
                <TextInput
                  label="Project Concurrency Limit"
                  type="number"
                  min={1}
                  name="projectLimit"
                  value={concurrencyForm.projectLimit}
                  onChange={handleConcurrencyInputChange}
                  disabled={concurrencyLoading || concurrencySubmitting}
                  required
                />
              </div>
              <Button
                type="submit"
                variant="primary"
                size="medium"
                disabled={concurrencySubmitting || concurrencyLoading}
              >
                {concurrencySubmitting ? 'Updating…' : 'Update Limit'}
              </Button>
            </form>
            <div className="concurrency-stats">
              {concurrencyLoading ? (
                <p>Loading concurrency settings…</p>
              ) : concurrencySettings ? (
                <InfoList columns={1}>
                  <InfoItem label="Configured Limit" value={concurrencySettings.project_limit} />
                  <InfoItem
                    label="Effective Runtime Limit"
                    value={concurrencySettings.effective_project_limit}
                  />
                  <InfoItem
                    label="Worker Pool Size"
                    value={concurrencySettings.worker_pool_size}
                  />
                  <InfoItem
                    label="Parallel Execution"
                    value={concurrencySettings.parallel_enabled ? 'Enabled' : 'Disabled'}
                  />
                  <InfoItem label="Last Updated" value={formatTimestamp(concurrencySettings.updated_at)} />
                </InfoList>
              ) : (
                <p>Concurrency settings unavailable.</p>
              )}
            </div>
          </Card>
      </div>

      {/* Clear PAT Modal */}
      {clearModalOpen && (
        <div className="modal-backdrop" role="presentation">
          <div className="modal">
            <h3>Clear GitLab PAT?</h3>
            <p>
              Clearing the personal access token immediately fails any pending tasks and prevents new runs
              until a replacement token is configured. Running tasks continue with the credentials they
              already captured.
            </p>
            <div className="modal-actions">
              <button
                type="button"
                className="ghost-button"
                onClick={() => {
                  setClearModalOpen(false);
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

      {/* Clear Session Modal */}
      {sessionClearModalOpen && (
        <div className="modal-backdrop" role="presentation">
          <div className="modal">
            <h3>Clear ChatGPT Session Bundle?</h3>
            <p>
              Clearing the session bundle disables Docker-backed Codex runs until you import a replacement.
              Stub-only runs (set RUNNER_DISABLE_DOCKER=1) continue to work without a session bundle.
            </p>
            <div className="modal-actions">
              <button
                type="button"
                className="ghost-button"
                onClick={() => {
                  setSessionClearModalOpen(false);
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
