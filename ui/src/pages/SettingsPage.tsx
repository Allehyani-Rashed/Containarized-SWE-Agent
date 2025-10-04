import { ChangeEvent, FormEvent, useRef, useState } from 'react';
import {
  clearPat,
  clearSession,
  importSession,
  storePat,
  verifyPat,
} from '../api/integrations';
import { formatTimestamp } from '../utils/time';
import { usePatStatus } from '../hooks/usePatStatus';
import Card from '../components/Card';
import Button from '../components/Button';
import { TextInput, TextArea } from '../components/Input';
import InfoPanel, { InfoItem, InfoList } from '../components/InfoPanel';
import StatusBadge from '../components/StatusBadge';
import Icon from '../components/Icon';
import './SettingsPage.css';

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

  // Accordion state - GitLab PAT expanded by default, Session collapsed
  const [patExpanded, setPatExpanded] = useState(true);
  const [sessionExpanded, setSessionExpanded] = useState(false);

  const combinedError = error ?? patStatusError;

  const allCredentialsVerified =
    patStatus.configured &&
    patStatus.session_configured &&
    patStatus.verification_status === 'verified';

  const needsSetup = !patStatus.configured || !patStatus.session_configured;


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
      {/* Quick Setup Banner - shown when credentials are missing */}
      {needsSetup && (
        <InfoPanel
          title="Quick Setup Required"
          variant="info"
          icon={<Icon type="alert" size={20} />}
          iconColor="blue"
        >
          <p>
            {!patStatus.configured && !patStatus.session_configured
              ? 'Configure both GitLab PAT and ChatGPT Session Bundle to get started'
              : !patStatus.configured
              ? 'GitLab PAT is required to submit tasks and create merge requests'
              : 'ChatGPT Session Bundle is required for Docker-backed agent runs'}
          </p>
        </InfoPanel>
      )}

      {/* Success Banner - shown when all credentials are verified */}
      {allCredentialsVerified && (
        <InfoPanel
          title="All Credentials Verified"
          variant="success"
          icon={
            <svg width="20" height="20" viewBox="0 0 20 20" fill="currentColor">
              <path
                fillRule="evenodd"
                d="M10 18a8 8 0 100-16 8 8 0 000 16zm3.707-9.293a1 1 0 00-1.414-1.414L9 10.586 7.707 9.293a1 1 0 00-1.414 1.414l2 2a1 1 0 001.414 0l4-4z"
                clipRule="evenodd"
              />
            </svg>
          }
          iconColor="green"
        >
          <p>Your GitLab PAT and ChatGPT session are properly configured and verified</p>
        </InfoPanel>
      )}

      {/* Error Banner */}
      {combinedError && (
        <InfoPanel title="Error" variant="error" iconColor="red">
          <p>{combinedError}</p>
        </InfoPanel>
      )}

      {/* Success Messages */}
      {patMessage && (
        <InfoPanel title="Success" variant="success" iconColor="green">
          <p>{patMessage}</p>
        </InfoPanel>
      )}
      {sessionMessage && (
        <InfoPanel title="Success" variant="success" iconColor="green">
          <p>{sessionMessage}</p>
        </InfoPanel>
      )}
      {verifyMessage && (
        <InfoPanel
          title={verifyResult === 'success' ? 'Verification Successful' : 'Verification Failed'}
          variant={verifyResult === 'success' ? 'success' : 'warning'}
          iconColor={verifyResult === 'success' ? 'green' : 'orange'}
          className={`notice ${verifyResult === 'success' ? 'notice-success' : 'notice-warning'}`}
        >
          <p>{verifyMessage}</p>
        </InfoPanel>
      )}

      <div className="settings-layout">
        {/* Main Content Area */}
        <main className="settings-main">
          {/* GitLab Personal Access Token Card */}
          <section className="accordion-section">
            <Card>
              {/* Accordion Header - Always Visible */}
              <button
                type="button"
                className="accordion-header"
                onClick={() => setPatExpanded(!patExpanded)}
                aria-expanded={patExpanded}
                aria-controls="gitlab-pat-section"
              >
                <div className="accordion-header-content">
                  <div className="accordion-icon credential-card-icon-orange">
                    <Icon type="key" size={24} />
                  </div>
                  <div className="accordion-title-section">
                    <h3>GitLab Personal Access Token</h3>
                    <div className="accordion-summary">
                      <StatusBadge
                        status={patStatus.configured ? 'configured' : 'missing'}
                        size="small"
                      />
                      <span className="accordion-summary-text">
                        {patStatus.updated_at ? `Updated ${formatTimestamp(patStatus.updated_at)}` : 'Not configured'}
                      </span>
                    </div>
                  </div>
                </div>
                <div className={`accordion-chevron ${patExpanded ? 'expanded' : ''}`}>
                  <Icon type="chevron-down" size={20} />
                </div>
              </button>

              {/* Accordion Content - Collapsible */}
              <div id="gitlab-pat-section" className={`accordion-content ${patExpanded ? 'expanded' : ''}`}>
                <div className="accordion-content-inner">
                  <InfoList columns={2}>
                    <InfoItem
                      label="Status"
                      value={
                        <StatusBadge status={patStatus.configured ? 'configured' : 'missing'} size="small" />
                      }
                    />
                    <InfoItem label="Last Update" value={formatTimestamp(patStatus.updated_at)} />
                    <InfoItem label="Updated By" value={patStatus.updated_by || '--'} />
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
              <TextInput
                label="Actor (Optional)"
                type="text"
                value={patForm.actor}
                onChange={(e) => setPatForm({ ...patForm, actor: e.target.value })}
                placeholder="operator"
              />

              <div className="button-group">
                <Button variant="primary" type="submit" disabled={patSubmitting} icon={<Icon type="key" size={20} />}>
                  {patSubmitting ? 'Storing...' : 'Store Token'}
                </Button>
                <Button
                  variant="secondary"
                  type="button"
                  onClick={handlePatVerify}
                  disabled={verifySubmitting || !patStatus.configured}
                  icon={<Icon type="check" size={20} />}
                >
                  {verifySubmitting ? 'Verifying...' : 'Verify PAT Access'}
                </Button>
                <Button
                  variant="danger"
                  type="button"
                  onClick={() => {
                    setPatMessage(null);
                    setSessionMessage(null);
                    setError(null);
                    setClearModalOpen(true);
                  }}
                  disabled={clearSubmitting || !patStatus.configured}
                  icon={<Icon type="trash" size={20} />}
                >
                  Clear PAT
                </Button>
              </div>
            </form>

                  <InfoPanel title="Credentials are write-only for security" variant="info" iconColor="blue">
                    <p>
                      GitLab PATs are encrypted and never displayed after storage. Clearing the PAT will prevent new
                      task submissions until reconfigured.
                    </p>
                  </InfoPanel>

                  {patStatus.verification_status === 'error' && patStatus.verification_error && (
                    <InfoPanel title="Verification Failed" variant="warning" iconColor="orange" icon={<Icon type="alert" size={20} />}>
                      <p>Clearing the PAT will prevent new task submissions until reconfigured</p>
                      <p className="error-detail">{patStatus.verification_error}</p>
                    </InfoPanel>
                  )}
                </div>
              </div>
            </Card>
          </section>

          {/* ChatGPT Session Bundle Card */}
          <section className="accordion-section">
            <Card>
              {/* Accordion Header - Always Visible */}
              <button
                type="button"
                className="accordion-header"
                onClick={() => setSessionExpanded(!sessionExpanded)}
                aria-expanded={sessionExpanded}
                aria-controls="chatgpt-session-section"
              >
                <div className="accordion-header-content">
                  <div className="accordion-icon credential-card-icon-green">
                    <Icon type="robot" size={24} />
                  </div>
                  <div className="accordion-title-section">
                    <h3>ChatGPT Session Bundle</h3>
                    <div className="accordion-summary">
                      <StatusBadge
                        status={patStatus.session_configured ? 'active' : 'missing'}
                        size="small"
                      />
                      <span className="accordion-summary-text">
                        {patStatus.session_updated_at ? `Updated ${formatTimestamp(patStatus.session_updated_at)}` : 'Not configured'}
                      </span>
                    </div>
                  </div>
                </div>
                <div className={`accordion-chevron ${sessionExpanded ? 'expanded' : ''}`}>
                  <Icon type="chevron-down" size={20} />
                </div>
              </button>

              {/* Accordion Content - Collapsible */}
              <div id="chatgpt-session-section" className={`accordion-content ${sessionExpanded ? 'expanded' : ''}`}>
                <div className="accordion-content-inner">
                  <InfoList columns={2}>
                    <InfoItem
                      label="Status"
                      value={
                        <StatusBadge
                          status={patStatus.session_configured ? 'active' : 'missing'}
                          size="small"
                        />
                      }
                    />
                    <InfoItem label="Updated By" value={patStatus.session_updated_by || '--'} />
                    <InfoItem label="Bundle Type" value="Session Bundle" />
                    <InfoItem label="Last Refresh" value={formatTimestamp(patStatus.session_updated_at)} />
                  </InfoList>

                  <form className="credential-form" onSubmit={handleSessionImport}>
              <TextArea
                label="Session Bundle JSON"
                value={sessionForm.bundle}
                onChange={(e) => setSessionForm({ ...sessionForm, bundle: e.target.value })}
                placeholder='{"session_token": "...", "user_agent": "...", "cf_clearance": "..."}'
                rows={6}
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

              <TextInput
                label="Actor (Optional)"
                type="text"
                value={sessionForm.actor}
                onChange={(e) => setSessionForm({ ...sessionForm, actor: e.target.value })}
                placeholder="operator"
              />

              <div className="button-group">
                <Button variant="success" type="submit" disabled={sessionSubmitting} icon={<Icon type="robot" size={20} />}>
                  {sessionSubmitting ? 'Importing...' : 'Import Session'}
                </Button>
              </div>
            </form>

            <div className="cli-commands">
              <h4>CLI Commands</h4>
              <pre>
                <code># macOS:{'\n'}pbpaste | jq . &gt; session_bundle.json</code>
              </pre>
              <pre>
                <code># Linux:{'\n'}xclip -o | jq . &gt; session_bundle.json</code>
              </pre>
              <pre>
                <code># Windows:{'\n'}Get-Clipboard | ConvertFrom-Json &gt; session_bundle.json</code>
              </pre>
            </div>

                  <div>
                  <Button
                    variant="danger"
                    type="button"
                    onClick={() => {
                      setSessionMessage(null);
                      setError(null);
                      setSessionClearModalOpen(true);
                    }}
                    disabled={sessionClearSubmitting || !patStatus.session_configured}
                    icon={<Icon type="trash" size={20} />}
                  >
                    Clear Session Bundle
                  </Button>

                  <InfoPanel title="Warning" variant="warning" iconColor="orange" icon={<Icon type="alert" size={20} />}>
                    <p>Clearing will affect Docker-backed task runs</p>
                  </InfoPanel>
                  </div>
                </div>
              </div>
            </Card>
          </section>
        </main>
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

      {/* Clear Session Modal */}
      {sessionClearModalOpen && (
        <div className="modal-backdrop" role="presentation">
          <div className="modal">
            <h3>Clear ChatGPT Session Bundle?</h3>
            <p>
              Clearing the session bundle disables Docker-backed Codex runs until you import a replacement.
              Stub-only runs (set RUNNER_DISABLE_DOCKER=1) continue to work without a session bundle.
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
