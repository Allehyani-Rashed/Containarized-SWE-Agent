import { ReactNode } from 'react';
import { ErrorBoundary } from '../components/ErrorBoundary';
import Card from '../components/Card';
import InfoPanel from '../components/InfoPanel';
import Icon from '../components/Icon';
import './HelpPage.css';

interface FAQItemProps {
  question: string;
  answer: string | ReactNode;
}

function FAQItem({ question, answer }: FAQItemProps) {
  return (
    <div className="faq-item">
      <h4 className="faq-question">{question}</h4>
      <div className="faq-answer">{answer}</div>
    </div>
  );
}

interface TroubleshootingItemProps {
  problem: string;
  solution: string | ReactNode;
}

function TroubleshootingItem({ problem, solution }: TroubleshootingItemProps) {
  return (
    <div className="troubleshooting-item">
      <h4 className="troubleshooting-problem">{problem}</h4>
      <div className="troubleshooting-solution">{solution}</div>
    </div>
  );
}

function HelpPage() {
  return (
    <ErrorBoundary>
      <div className="layout-page">
        {/* Getting Started Section */}
        <section className="help-section">
          <Card>
            <div className="section-header">
              <div className="section-icon section-icon-blue"><Icon type="rocket" size={24} /></div>
              <h3>Getting Started</h3>
            </div>

            <div className="help-content">
              <div className="step-list">
                <div className="step-item">
                  <div className="step-number">1</div>
                  <div className="step-content">
                    <h4>Configure Credentials</h4>
                    <p>
                      Navigate to the <strong>Settings</strong> page and configure your GitLab Personal Access
                      Token (PAT) and ChatGPT Session Bundle. Both are required for tasks to run successfully.
                    </p>
                    <div className="code-block">
                      <code>Settings → Store GitLab PAT → Import Session Bundle</code>
                    </div>
                  </div>
                </div>

                <div className="step-item">
                  <div className="step-number">2</div>
                  <div className="step-content">
                    <h4>Create Your First Project</h4>
                    <p>
                      Go to the <strong>Projects</strong> page and add a new project by providing the GitLab
                      repository URL. The system will automatically clone and cache the repository.
                    </p>
                    <div className="code-block">
                      <code>Projects → Add Project → Enter Repository URL</code>
                    </div>
                  </div>
                </div>

                <div className="step-item">
                  <div className="step-number">3</div>
                  <div className="step-content">
                    <h4>Configure Project Allowlist (Optional)</h4>
                    <p>
                      Set up domain allowlists for your project to control which external resources the agent
                      can access. This is important for security and preventing unintended network calls.
                    </p>
                    <div className="code-block">
                      <code>Project Detail → Allowlist → Add Domains</code>
                    </div>
                  </div>
                </div>

                <div className="step-item">
                  <div className="step-number">4</div>
                  <div className="step-content">
                    <h4>Submit Your First Task</h4>
                    <p>
                      From the home page, select your project, enter a detailed prompt describing what you want
                      the agent to accomplish, choose your model, and submit. The agent will work in a sandboxed
                      environment and create a merge request when complete.
                    </p>
                    <div className="code-block">
                      <code>Home → Select Project → Enter Prompt → Submit Task</code>
                    </div>
                  </div>
                </div>

                <div className="step-item">
                  <div className="step-number">5</div>
                  <div className="step-content">
                    <h4>Monitor Task Progress</h4>
                    <p>
                      Navigate to the <strong>Tasks</strong> page to view all submitted tasks. Click on any task
                      to view real-time logs, track progress, and access the merge request when complete.
                    </p>
                    <div className="code-block">
                      <code>Tasks → View Task → Monitor Logs</code>
                    </div>
                  </div>
                </div>
              </div>
            </div>
          </Card>
        </section>

        {/* FAQ Section */}
        <section className="help-section">
          <Card>
            <div className="section-header">
              <div className="section-icon section-icon-green"><Icon type="help" size={24} /></div>
              <h3>Frequently Asked Questions</h3>
            </div>

            <div className="help-content">
              <div className="faq-list">
                <FAQItem
                  question="What is a GitLab Personal Access Token (PAT)?"
                  answer={
                    <>
                      <p>
                        A Personal Access Token is a credential that allows the Codex Agent to authenticate with
                        your GitLab instance and perform operations like cloning repositories, creating branches,
                        and submitting merge requests.
                      </p>
                      <p className="faq-detail">
                        To create one: Go to GitLab → Settings → Access Tokens → Create Personal Access Token
                        (path may vary by GitLab version)
                      </p>
                    </>
                  }
                />

                <FAQItem
                  question="What scopes does my GitLab PAT need?"
                  answer={
                    <>
                      <p>Your Personal Access Token requires the following scopes:</p>
                      <ul className="faq-list-items">
                        <li>
                          <strong>api</strong> - Full API access for creating merge requests and managing
                          repositories
                        </li>
                        <li>
                          <strong>read_user</strong> - Read user information for attribution
                        </li>
                        <li>
                          <strong>read_repository</strong> - Access repository contents and metadata
                        </li>
                      </ul>
                      <div className="code-block">
                        <code>Required scopes: api, read_user, read_repository</code>
                      </div>
                    </>
                  }
                />

                <FAQItem
                  question="What is a ChatGPT Session Bundle?"
                  answer={
                    <>
                      <p>
                        A ChatGPT Session Bundle is a JSON file containing authentication credentials that allow
                        the Codex Agent to interact with OpenAI&apos;s ChatGPT service. This bundle includes
                        session tokens and browser fingerprints required for API access.
                      </p>
                      <p className="faq-detail">
                        The bundle is exported from your browser and imported into the Settings page. Session bundles
                        are encrypted via Fernet before storage. GitLab PATs are sourced from the .env file for
                        local deployments.
                      </p>
                    </>
                  }
                />

                <FAQItem
                  question="How do I manage project allowlists?"
                  answer={
                    <>
                      <p>
                        Project allowlists control which external domains the Codex Agent can access during task
                        execution. This is a critical security feature that prevents unintended data exfiltration.
                      </p>
                      <p>To configure:</p>
                      <ol className="faq-list-items">
                        <li>Navigate to the project detail page</li>
                        <li>Click on the Allowlist section</li>
                        <li>Add domains (e.g., pypi.org, npmjs.com) one per line</li>
                        <li>Save changes</li>
                      </ol>
                      <p className="faq-detail">
                        The system automatically includes essential domains like GitLab hosts and package
                        registries in the base allowlist.
                      </p>
                    </>
                  }
                />

                <FAQItem
                  question="What happens if a task fails?"
                  answer={
                    <>
                      <p>When a task fails, several things occur:</p>
                      <ul className="faq-list-items">
                        <li>The task status changes to &quot;failed&quot;</li>
                        <li>All execution logs are preserved for debugging</li>
                        <li>The workspace is retained (in debug mode) for inspection</li>
                        <li>No merge request is created</li>
                      </ul>
                      <p className="faq-detail">
                        Common failure reasons include: missing credentials, network restrictions, invalid prompts,
                        or agent execution errors. Check the task logs for detailed error messages.
                      </p>
                    </>
                  }
                />

                <FAQItem
                  question="How do I view task logs?"
                  answer={
                    <>
                      <p>Task logs provide real-time visibility into agent execution:</p>
                      <ol className="faq-list-items">
                        <li>Navigate to the Tasks page</li>
                        <li>Click on the task you want to inspect</li>
                        <li>The log viewer will display streaming output</li>
                        <li>Use the filters to focus on specific log levels (info, warning, error)</li>
                      </ol>
                      <p className="faq-detail">
                        Logs include agent reasoning, file modifications, API calls, and error messages. Sensitive
                        data like tokens are automatically redacted.
                      </p>
                    </>
                  }
                />

                <FAQItem
                  question="Can I abort a running task?"
                  answer={
                    <>
                      <p>
                        Yes, you can abort running tasks from the Tasks page. Click the abort button next to the
                        task. The system will attempt to gracefully terminate the Docker container and clean up
                        resources.
                      </p>
                      <p className="faq-detail">
                        Note: Aborting a task marks it as aborted but does not create a merge request. The partial
                        work is not committed to the repository.
                      </p>
                    </>
                  }
                />

                <FAQItem
                  question="How does the sandboxing work?"
                  answer={
                    <>
                      <p>
                        Each task runs in an isolated Docker container with strict security controls:
                      </p>
                      <ul className="faq-list-items">
                        <li>Read-only root filesystem</li>
                        <li>No privilege escalation allowed</li>
                        <li>Network access limited by allowlist via Tinyproxy</li>
                        <li>Memory and CPU limits enforced</li>
                        <li>Dropped Linux capabilities</li>
                      </ul>
                      <p className="faq-detail">
                        This ensures tasks cannot access sensitive host resources or make unauthorized network
                        connections.
                      </p>
                    </>
                  }
                />
              </div>
            </div>
          </Card>
        </section>

        {/* Troubleshooting Section */}
        <section className="help-section">
          <Card>
            <div className="section-header">
              <div className="section-icon section-icon-orange"><Icon type="settings" size={24} /></div>
              <h3>Troubleshooting</h3>
            </div>

            <div className="help-content">
              <div className="troubleshooting-list">
                <TroubleshootingItem
                  problem="Tasks fail immediately with authentication error"
                  solution={
                    <>
                      <p>
                        <strong>Cause:</strong> Missing or invalid GitLab PAT or ChatGPT Session Bundle.
                      </p>
                      <p>
                        <strong>Solution:</strong>
                      </p>
                      <ol className="troubleshooting-steps">
                        <li>Go to Settings and verify your credentials are configured</li>
                        <li>Click &quot;Verify&quot; to test the GitLab token</li>
                        <li>Ensure your session bundle is current (not expired)</li>
                        <li>Re-import credentials if verification fails</li>
                      </ol>
                    </>
                  }
                />

                <TroubleshootingItem
                  problem="Network timeout during task execution"
                  solution={
                    <>
                      <p>
                        <strong>Cause:</strong> Required domain not in project allowlist.
                      </p>
                      <p>
                        <strong>Solution:</strong>
                      </p>
                      <ol className="troubleshooting-steps">
                        <li>Check task logs for denied domain (e.g., &quot;Connection refused: pypi.org&quot;)</li>
                        <li>Navigate to project detail page</li>
                        <li>Add the required domain to the allowlist</li>
                        <li>Resubmit the task</li>
                      </ol>
                      <div className="code-block">
                        <code>Example allowlist: pypi.org, npmjs.com, github.com</code>
                      </div>
                    </>
                  }
                />

                <TroubleshootingItem
                  problem="Docker container fails to start"
                  solution={
                    <>
                      <p>
                        <strong>Cause:</strong> Docker daemon not running or network configuration issue.
                      </p>
                      <p>
                        <strong>Solution:</strong>
                      </p>
                      <ol className="troubleshooting-steps">
                        <li>Verify Docker is running: <code>docker ps</code></li>
                        <li>Check compose services: <code>docker compose ps</code></li>
                        <li>Ensure codex-shared network exists: <code>docker network ls</code></li>
                        <li>Restart the backend: <code>make dev</code></li>
                      </ol>
                    </>
                  }
                />

                <TroubleshootingItem
                  problem="Task succeeds but no merge request created"
                  solution={
                    <>
                      <p>
                        <strong>Cause:</strong> Insufficient GitLab permissions or dry-run mode enabled.
                      </p>
                      <p>
                        <strong>Solution:</strong>
                      </p>
                      <ol className="troubleshooting-steps">
                        <li>Verify PAT has &quot;api&quot; scope (required for creating MRs)</li>
                        <li>Check if RUNNER_GIT_DRY_RUN is set in environment</li>
                        <li>Review task logs for push/MR creation errors</li>
                        <li>Ensure you have write access to the target repository</li>
                      </ol>
                    </>
                  }
                />

                <TroubleshootingItem
                  problem="Project cache refresh fails"
                  solution={
                    <>
                      <p>
                        <strong>Cause:</strong> Repository URL changed, PAT lacks access, or disk space issue.
                      </p>
                      <p>
                        <strong>Solution:</strong>
                      </p>
                      <ol className="troubleshooting-steps">
                        <li>Verify repository URL is correct and accessible</li>
                        <li>Check PAT has read_repository scope</li>
                        <li>Review disk space: <code>df -h</code></li>
                        <li>Manually refresh cache via CLI: <code>python3 scripts/project_cache.py --refresh --project-id [ID]</code></li>
                      </ol>
                    </>
                  }
                />

                <TroubleshootingItem
                  problem="OOMKilled - Container terminated due to memory"
                  solution={
                    <>
                      <p>
                        <strong>Cause:</strong> Task exceeded memory limit (default 2GB).
                      </p>
                      <p>
                        <strong>Solution:</strong>
                      </p>
                      <ol className="troubleshooting-steps">
                        <li>Increase RUNNER_MEM_LIMIT in .env file</li>
                        <li>Restart backend to apply changes</li>
                        <li>Consider optimizing the prompt to reduce memory usage</li>
                        <li>Check for memory leaks in agent code</li>
                      </ol>
                      <div className="code-block">
                        <code>RUNNER_MEM_LIMIT=4g  # Increase to 4GB</code>
                      </div>
                    </>
                  }
                />

                <TroubleshootingItem
                  problem="Session bundle expired or invalid"
                  solution={
                    <>
                      <p>
                        <strong>Cause:</strong> ChatGPT session tokens have limited lifetime.
                      </p>
                      <p>
                        <strong>Solution:</strong>
                      </p>
                      <ol className="troubleshooting-steps">
                        <li>Export a fresh session bundle from your browser</li>
                        <li>Navigate to Settings → ChatGPT Session Bundle</li>
                        <li>Import the new bundle</li>
                        <li>Resubmit failed tasks</li>
                      </ol>
                      <p className="troubleshooting-detail">
                        Session bundles typically expire after 24-48 hours. Regular refresh is recommended.
                      </p>
                    </>
                  }
                />

                <TroubleshootingItem
                  problem="Logs not streaming in real-time"
                  solution={
                    <>
                      <p>
                        <strong>Cause:</strong> Server-sent events (SSE) connection dropped or browser issue.
                      </p>
                      <p>
                        <strong>Solution:</strong>
                      </p>
                      <ol className="troubleshooting-steps">
                        <li>Refresh the browser page</li>
                        <li>Check browser console for errors</li>
                        <li>Verify backend is running: <code>curl http://localhost:8000/</code></li>
                        <li>Disable browser extensions that might block SSE</li>
                      </ol>
                    </>
                  }
                />
              </div>
            </div>
          </Card>
        </section>

        {/* Support Section */}
        <section className="help-section">
          <Card>
            <div className="section-header">
              <div className="section-icon section-icon-purple"><Icon type="info" size={24} /></div>
              <h3>Support & Resources</h3>
            </div>

            <div className="help-content">
              <InfoPanel
                title="Need Additional Help?"
                variant="info"
                iconColor="blue"
              >
                <p>
                  For issues not covered in this documentation, consult the following resources:
                </p>
              </InfoPanel>

              <div className="resource-list">
                <div className="resource-item">
                  <div className="resource-icon"><Icon type="folder" size={24} /></div>
                  <div className="resource-content">
                    <h4>CLAUDE.md Documentation</h4>
                    <p>
                      Comprehensive technical documentation covering architecture, development workflows, and
                      advanced configurations.
                    </p>
                    <div className="code-block">
                      <code>cat CLAUDE.md</code>
                    </div>
                  </div>
                </div>

                <div className="resource-item">
                  <div className="resource-icon"><Icon type="check" size={24} /></div>
                  <div className="resource-content">
                    <h4>Test Scripts</h4>
                    <p>
                      Use the built-in smoke test scripts to validate your setup and diagnose issues.
                    </p>
                    <div className="code-block">
                      <code>python3 scripts/test_docker_path.py --prompt &quot;test&quot;</code>
                    </div>
                  </div>
                </div>

                <div className="resource-item">
                  <div className="resource-icon"><Icon type="settings" size={24} /></div>
                  <div className="resource-content">
                    <h4>CLI Utilities</h4>
                    <p>
                      Command-line tools for credential management, cache operations, and system diagnostics.
                    </p>
                    <div className="code-block">
                      <code>scripts/codex pat store  # Store GitLab PAT</code>
                    </div>
                  </div>
                </div>

                <div className="resource-item">
                  <div className="resource-icon"><Icon type="alert" size={24} /></div>
                  <div className="resource-content">
                    <h4>Debug Mode</h4>
                    <p>
                      Run tasks with workspace preservation for detailed post-mortem analysis.
                    </p>
                    <div className="code-block">
                      <code>python3 scripts/test_docker_path.py --keep-workspace</code>
                    </div>
                  </div>
                </div>
              </div>

              <InfoPanel
                title="Security Best Practices"
                variant="warning"
                iconColor="orange"
              >
                <ul className="faq-list-items">
                  <li>Never commit .env files, PATs, or session bundles to version control</li>
                  <li>Rotate credentials regularly (recommended: every 30 days)</li>
                  <li>Use minimal required scopes for GitLab PATs (api, read_user, read_repository)</li>
                  <li>Keep allowlists restrictive - only add necessary domains</li>
                  <li>Monitor task logs for suspicious network activity</li>
                  <li>Review merge requests before merging agent-generated code</li>
                  <li>Session bundles are encrypted; PATs are loaded from .env (local deployments)</li>
                </ul>
              </InfoPanel>
            </div>
          </Card>
        </section>
      </div>
    </ErrorBoundary>
  );
}

export default HelpPage;
