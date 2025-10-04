# Threat Model

This document summarizes the primary security risks for the local codex runner
and the mitigations implemented to address them. The focus is on the
single-user, local-first deployment described in the project objective.

## Secret Exfiltration from Host Machine

- **Risk**: Runner code attempts to exfiltrate credentials or private files
  from the developer workstation.
- **Mitigations**:
  - Tasks execute on a sanitized workspace copy mounted at `/work`; the host
    repository and home directory are never mounted into the container.
  - The container filesystem is read-only with explicit tmpfs mounts for
    transient paths, preventing writes outside `/work`.
  - Workspace sanitizer filters secrets listed in `.projectsanitize` (falling back to legacy `.codexignore` with a warning) before the
    run begins.
- **Residual Risk**: Secrets accidentally committed to the repository are still
  present inside the sanitized workspace.

## Overbroad Network Egress

- **Risk**: Task code reaches unauthorized network destinations to leak data or
  download untrusted binaries.
- **Mitigations**:
  - Traffic is forced through Tinyproxy with a deny-by-default allowlist.
  - Per-task allowlists merge project defaults with user overrides and are
    pushed to the proxy before each run.
  - `proxy/base_allowlist.conf` ships a minimal set of trusted domains
    (`gitlab.com`, `registry.npmjs.org`, `pypi.org`, `files.pythonhosted.org`,
    `chatgpt.com`), and the orchestrator emits the merged list to
    `proxy/filter.list` so Tinyproxy enforces the most recent policy.
  - `scripts/threat_scan.py` surfaces the enforced proxy configuration.
- **Residual Risk**: Allowed domains may host malicious payloads; operators
  should keep allowlists scoped to required services.

## Malicious Code Execution in the Repository

- **Risk**: The repository contains untrusted hooks or scripts that execute
  during the task and tamper with the run or leak data.
- **Mitigations**:
  - `finish_task.sh` disables git hooks via `core.hooksPath=/dev/null`.
  - The runner image is minimal and only includes required tooling (bash, git,
    curl, python3), reducing unexpected executables.
  - Runner commands run non-interactively and respect the sanitized workspace
    boundary.
- **Residual Risk**: The prompt-provided commands themselves are untrusted; the
  operator should review generated merge requests before merging.

## Privilege Escalation within the Runner

- **Risk**: Code attempts to escalate privileges inside the container to break
  isolation or mount host resources.
- **Mitigations**:
  - Containers run as the non-root `codex` user (`1000:1000`).
  - All Linux capabilities are dropped and `no-new-privileges` is enforced.
  - The root filesystem is read-only and critical writable paths are tmpfs,
    blocking writes to system directories.
  - Memory and PID limits limit resource exhaustion attacks.
- **Residual Risk**: Kernel-level container escapes remain in scope; keep the
  host kernel updated and consider stronger isolation (gVisor, firecracker) for
  higher-assurance deployments.

## GitLab Token Leakage

- **Risk**: Personal access tokens leak through logs, temp files, or network
  egress.
- **Mitigations**:
  - Tokens enter the container via environment variables but logs redact the
    values and the scripts avoid `set -x`.
  - `RUNNER_GIT_DRY_RUN=1` enables local smoke tests without pushing to GitLab.
  - Redacted logs are persisted on disk and surfaced through the UI. Snapshot endpoints return non-sensitive metadata (status, branch, model, abort flag) alongside log lines so tooling can audit runs without exposing credentials.
  - Tokens are stored in plaintext within the orchestrator's credential table for the local deployment profile; protect filesystem access to the SQLite database and `.env` file accordingly.
- **Residual Risk**: Operators must protect the persisted SQLite database and
  log files, and rotate credentials if compromise is suspected.

## ChatGPT Session Bundle Handling

- **Risk**: Session bundles imported from `codex login` include refresh tokens
  and long-lived cookies that could be replayed if exposed.
- **Mitigations**:
  - ChatGPT bundles remain encrypted at rest using the shared
    `IntegrationCredential` store, while the GitLab PAT stays in plaintext for
    local deployments.
  - The orchestrator decrypts bundles only in-process, base64 encodes them for
    transit, and redacts both raw and encoded forms from task logs.
  - Runner scripts decode the bundle into `~/.codex/auth.json` inside the
    container, set restrictive permissions, and unset the base64 environment
    variable to minimize exposure.
  - UI and CLI flows never echo bundle contents and require explicit operator
    confirmation before clearing stored sessions.
- **Residual Risk**: Session bundles expire; operators must monitor expiry
  timestamps, import fresh bundles as needed, and clear revoked sessions to
  avoid authentication failures.

## Availability & Resource Exhaustion

- **Risk**: Malicious prompts attempt to exhaust host resources (memory/PIDs)
  causing denial of service.
- **Mitigations**:
  - `mem_limit` and `pids_limit` defaults guard the container.
  - tmpfs-backed writable paths limit disk impact on the host.
  - The task queue runs one task at a time, containing blast radius.
- **Residual Risk**: Excessive CPU consumption is throttled only by the Docker
  runtime; operators can further limit via cgroup CPU quotas if necessary.

## Validation

- Run `make threat-scan` to verify the runner hardening flags and proxy
  enforcement remain in place, including a container breakout probe that
  attempts `/work/../../..` reads against a host sentinel file.
- Manual smoke tests (`make smoke-docker`) exercise the Docker runner with the
  Tinyproxy allowlist and git dry-run flow.
