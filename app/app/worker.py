from __future__ import annotations

import asyncio
import base64
import os
import re
from datetime import datetime, timezone
from pathlib import Path
from queue import Empty, Queue
from threading import Event, Lock, Thread
from typing import AsyncGenerator, Dict, List, Optional, Tuple
from uuid import uuid4

from sqlmodel import Session, select

from .allowlist import merge_allowlists, refresh_proxy_allowlist
from .codex_runner import CodexRunnerError, run_codex
from .integrations import (
    ChatGPTSessionError,
    ChatGPTSessionMaterial,
    ClaudeSessionError,
    ClaudeSessionMaterial,
    get_chatgpt_session_bundle,
    get_claude_session_bundle,
    get_gitlab_pat_token,
)
from .models import Project, Task, TaskStatus
from .proxy_runtime import ensure_proxy_stack
from .sanitizer import sanitize_workspace
from .secrets import SecretError, get_secret_manager

LOG_POLL_INTERVAL_SECONDS = 0.5
BRANCH_PREFIX = "codex/task"
REPO_ROOT = Path(__file__).resolve().parents[2]
LOG_STORAGE_DIR = REPO_ROOT / "workspaces" / "logs"
SENSITIVE_ENV_PATTERN = re.compile(r"(GITLAB_TOKEN=)([^\s]+)")


def _generate_branch_name(task_id: int) -> str:
    """Return a deterministic-style branch name for the task run."""
    date_part = datetime.now(timezone.utc).strftime("%Y%m%d")
    short_id = uuid4().hex[:6]
    return f"{BRANCH_PREFIX}-{date_part}-{short_id}"


def _build_mr_title(task_id: int, prompt: str) -> str:
    """Construct a merge request title derived from the task prompt."""
    prompt_snippet = " ".join(prompt.strip().split())
    if not prompt_snippet:
        prompt_snippet = "Codex Task"
    if len(prompt_snippet) > 60:
        prompt_snippet = f"{prompt_snippet[:57]}..."
    return f"Codex Task {task_id}: {prompt_snippet}"


class TaskQueueManager:
    """Simple single-consumer worker that processes pending tasks sequentially."""

    def __init__(self, engine) -> None:
        self._engine = engine
        self._tasks: "Queue[int]" = Queue()
        self._stop_event = Event()
        self._lock = Lock()
        self._state_lock = Lock()
        self._cache_lock = Lock()
        self._logs: Dict[int, List[str]] = {}
        self._completed: Dict[int, bool] = {}
        self._log_paths: Dict[int, Path] = {}
        self._redactions: Dict[int, List[str]] = {}
        self._active_task_id: Optional[int] = None
        self._gitlab_token_cache: Optional[str] = None
        self._gitlab_token_present: bool = False
        self._chatgpt_session_cache: ChatGPTSessionMaterial | None = None
        self._chatgpt_session_known_missing: bool = False
        self._chatgpt_session_present: bool = False
        self._claude_session_cache: ClaudeSessionMaterial | None = None
        self._claude_session_known_missing: bool = False
        self._claude_session_present: bool = False
        LOG_STORAGE_DIR.mkdir(parents=True, exist_ok=True)
        self._thread = Thread(target=self._run, name="task-worker", daemon=True)
        self._thread.start()

    def enqueue(self, task_id: int) -> None:
        self._hydrate_logs_from_disk(task_id)
        with self._lock:
            self._logs.setdefault(task_id, [])
            self._completed.setdefault(task_id, False)
        self._tasks.put(task_id)

    def register_task(self, task_id: int) -> None:
        self._hydrate_logs_from_disk(task_id)
        with self._lock:
            self._logs.setdefault(task_id, [])
            self._completed.setdefault(task_id, False)

    def get_logs_snapshot(self, task_id: int) -> List[str]:
        self._hydrate_logs_from_disk(task_id)
        with self._lock:
            return list(self._logs.get(task_id, []))

    def is_complete(self, task_id: int) -> bool:
        with self._lock:
            return self._completed.get(task_id, False)

    async def stream_logs(self, task_id: int) -> AsyncGenerator[str, None]:
        """Yield log lines as Server-Sent Events with a small polling delay."""
        self._hydrate_logs_from_disk(task_id)
        cursor = 0
        while True:
            history, done = self._log_state(task_id)
            while cursor < len(history):
                yield history[cursor]
                cursor += 1
            if done:
                break
            await asyncio.sleep(LOG_POLL_INTERVAL_SECONDS)

    def shutdown(self) -> None:
        self._stop_event.set()
        self._tasks.put(-1)
        self._thread.join(timeout=2)

    # Internal helpers -----------------------------------------------------

    def _run(self) -> None:
        while not self._stop_event.is_set():
            try:
                task_id = self._tasks.get(timeout=0.25)
            except Empty:
                continue
            if task_id < 0:
                continue
            try:
                self._process_task(task_id)
            finally:
                self._tasks.task_done()

    def _process_task(self, task_id: int) -> None:
        self._set_active_task(task_id)
        project_root: Path | None = None
        task_prompt = ""
        task_allowlist: list[str] = []
        project_gitlab_host = ""
        gitlab_token = ""
        codex_token: str | None = None
        session_bundle: ChatGPTSessionMaterial | None = None
        session_bundle_error: str | None = None
        branch_name = ""
        mr_title = ""
        target_branch = ""
        gitlab_host = ""
        gitlab_project_path = ""
        try:
            with Session(self._engine) as session:
                task = session.get(Task, task_id)
                if task is None:
                    return
                project = session.get(Project, task.project_id)
                if project is None:
                    task.status = TaskStatus.failed
                    task.finished_at = datetime.now(timezone.utc)
                    session.add(task)
                    session.commit()
                    self._append_log(task_id, "Project not found for task; marking as failed")
                    self._mark_complete(task_id)
                    return
                if task.status != TaskStatus.pending:
                    return
                project_root = Path(project.local_path).expanduser()
                task.status = TaskStatus.running
                task.started_at = datetime.now(timezone.utc)
                task_prompt = task.prompt or ""
                task_allowlist = list(task.allowlist or [])
                task_agent_type = task.agent_type.value if hasattr(task.agent_type, 'value') else task.agent_type
                task_model = task.model
                target_branch = project.default_branch
                gitlab_host = project.gitlab_host
                gitlab_project_path = project.gitlab_project_path
                try:
                    gitlab_token = self._resolve_gitlab_token(session)
                except SecretError as exc:
                    self._append_log(task_id, f"GitLab credential decryption failed: {exc}")
                    task.status = TaskStatus.failed
                    task.finished_at = datetime.now(timezone.utc)
                    session.add(task)
                    session.commit()
                    self._mark_complete(task_id)
                    return
                if project.codex_token_encrypted:
                    try:
                        codex_token = get_secret_manager().decrypt(project.codex_token_encrypted)
                    except SecretError as exc:
                        self._append_log(task_id, f"Codex credential decryption failed: {exc}")
                        task.status = TaskStatus.failed
                        task.finished_at = datetime.now(timezone.utc)
                        session.add(task)
                        session.commit()
                        self._mark_complete(task_id)
                        return
                # Resolve agent-specific credentials
                session_bundle = None
                session_bundle_error = None
                claude_session = None
                claude_session_error = None

                if task_agent_type == "codex":
                    try:
                        session_bundle = self._resolve_chatgpt_session_bundle(session)
                    except ChatGPTSessionError as exc:
                        session_bundle_error = str(exc)
                else:  # claude-code
                    try:
                        claude_session = self._resolve_claude_session_bundle(session)
                    except ClaudeSessionError as exc:
                        claude_session_error = str(exc)

                project_gitlab_host = gitlab_host
                session.add(task)
                session.commit()

            if not gitlab_token:
                self._append_log(task_id, "GitLab PAT missing; configure a token via Settings -> Integrations")
                with Session(self._engine) as session:
                    task = session.get(Task, task_id)
                    if task is None:
                        return
                    task.status = TaskStatus.failed
                    task.finished_at = datetime.now(timezone.utc)
                    session.add(task)
                    session.commit()
                self._mark_complete(task_id)
                return

            require_credentials = os.environ.get("RUNNER_DISABLE_DOCKER", "0") != "1"

            # Handle Codex credentials
            session_bundle_raw: str | None = None
            session_bundle_expires_at: datetime | None = None
            if session_bundle is not None:
                session_bundle_raw = session_bundle.raw
                session_bundle_expires_at = session_bundle.expires_at
                if session_bundle_expires_at is not None and session_bundle_expires_at <= datetime.now(timezone.utc):
                    session_bundle_error = (
                        f"ChatGPT session bundle expired at {session_bundle_expires_at.isoformat()}; import a new session via codex login"
                    )
                    session_bundle_raw = None
                    session_bundle = None
                    session_bundle_expires_at = None

            # Handle Claude credentials
            claude_session_raw: str | None = None
            claude_session_expires_at: datetime | None = None
            if claude_session is not None:
                claude_session_raw = claude_session.raw
                claude_session_expires_at = claude_session.expires_at
                if claude_session_expires_at is not None and claude_session_expires_at <= datetime.now(timezone.utc):
                    claude_session_error = (
                        f"Claude session bundle expired at {claude_session_expires_at.isoformat()}; import a new session"
                    )
                    claude_session_raw = None
                    claude_session = None
                    claude_session_expires_at = None

            # Validate credentials based on agent type
            credential_error: str | None = None
            using_api_token = False
            using_session_bundle = False

            if task_agent_type == "codex":
                using_api_token = bool(codex_token)
                using_session_bundle = bool(session_bundle_raw) and not using_api_token
                if not using_api_token and not using_session_bundle and require_credentials:
                    credential_error = session_bundle_error or (
                        "Codex credentials unavailable; configure a CODEX access token or import a ChatGPT session bundle"
                    )
            else:  # claude-code
                using_session_bundle = bool(claude_session_raw)
                # Claude Code can work without credentials if ANTHROPIC_API_KEY is set in environment
                # So we don't strictly require credentials here

            if credential_error:
                self._append_log(task_id, credential_error)
                with Session(self._engine) as session:
                    task = session.get(Task, task_id)
                    if task is None:
                        return
                    task.status = TaskStatus.failed
                    task.finished_at = datetime.now(timezone.utc)
                    session.add(task)
                    session.commit()
                self._mark_complete(task_id)
                return

            credential_description: str | None = None
            if task_agent_type == "codex":
                if using_api_token:
                    if session_bundle_raw:
                        credential_description = "Codex credential: using API access token (ChatGPT session stored but not required)"
                    else:
                        credential_description = "Codex credential: using API access token"
                elif using_session_bundle:
                    credential_description = "Codex credential: using ChatGPT session bundle"
            else:  # claude-code
                if using_session_bundle:
                    credential_description = "Claude credential: using Claude session bundle"
                else:
                    credential_description = "Claude credential: using ANTHROPIC_API_KEY from environment"

            if credential_description:
                self._append_log(task_id, credential_description)

            # Log credential issues
            if task_agent_type == "codex" and session_bundle_error:
                if using_api_token:
                    self._append_log(
                        task_id,
                        f"ChatGPT session bundle unusable ({session_bundle_error}); proceeding with configured API token",
                    )
                elif not require_credentials:
                    self._append_log(
                        task_id,
                        f"ChatGPT session bundle unusable ({session_bundle_error}); continuing with local stub",
                    )
            elif task_agent_type == "claude-code" and claude_session_error:
                if not using_session_bundle:
                    self._append_log(
                        task_id,
                        f"Claude session bundle unusable ({claude_session_error}); proceeding with ANTHROPIC_API_KEY",
                    )

            redactions = [gitlab_token, codex_token or ""]
            if session_bundle_raw:
                redactions.append(session_bundle_raw)
                try:
                    redactions.append(base64.b64encode(session_bundle_raw.encode("utf-8")).decode("ascii"))
                except Exception:
                    # Base64 encoding failure should not block task execution; raw value already registered.
                    pass
            if claude_session_raw:
                redactions.append(claude_session_raw)
                try:
                    redactions.append(base64.b64encode(claude_session_raw.encode("utf-8")).decode("ascii"))
                except Exception:
                    pass
            self._register_redactions(task_id, redactions)
            branch_name = _generate_branch_name(task_id)
            mr_title = _build_mr_title(task_id, task_prompt)
            self._append_log(task_id, f"Proposed branch name: {branch_name}")

            self._append_log(task_id, "Task started; sanitizing workspace")
            if project_root is None:
                self._append_log(task_id, "Unable to determine project root; aborting")
                return

            try:
                sanitized_path = sanitize_workspace(project_root, task_id)
            except Exception as exc:  # noqa: BLE001 - bubble failure to task logs/state
                self._append_log(task_id, f"Workspace sanitization failed: {exc}")
                with Session(self._engine) as session:
                    task = session.get(Task, task_id)
                    if task is None:
                        return
                    task.status = TaskStatus.failed
                    task.finished_at = datetime.now(timezone.utc)
                    session.add(task)
                    session.commit()
                self._mark_complete(task_id)
                return

            self._append_log(task_id, f"Workspace ready at {sanitized_path}")
            with Session(self._engine) as session:
                task = session.get(Task, task_id)
                if task is None:
                    return
                task.workspace_path = str(sanitized_path)
                session.add(task)
                session.commit()

            docker_disabled = os.environ.get("RUNNER_DISABLE_DOCKER") == "1"
            if docker_disabled:
                self._append_log(task_id, "Skipping proxy preflight (Docker disabled)")
            else:
                self._append_log(task_id, "Verifying proxy stack readiness")

                def proxy_log(message: str) -> None:
                    self._append_log(task_id, f"proxy: {message}")

                if not ensure_proxy_stack(log_fn=proxy_log):
                    self._append_log(task_id, "Proxy preflight failed; aborting task execution")
                    with Session(self._engine) as session:
                        task = session.get(Task, task_id)
                        if task is None:
                            return
                        task.status = TaskStatus.failed
                        task.finished_at = datetime.now(timezone.utc)
                        session.add(task)
                        session.commit()
                    self._mark_complete(task_id)
                    return

            self._append_log(task_id, "Launching codex runner")
            try:
                effective_allowlist = merge_allowlists(project_gitlab_host, task_allowlist)
            except Exception as exc:  # noqa: BLE001 - capture normalization failures
                effective_allowlist = list(task_allowlist)
                self._append_log(task_id, f"Allowlist normalization failed ({exc}); using raw entries")
            else:
                joined_allowlist = ", ".join(effective_allowlist) or "<empty>"
                self._append_log(task_id, f"Effective allowlist: {joined_allowlist}")
                try:
                    refresh_proxy_allowlist(
                        effective_allowlist,
                        log_fn=lambda message: self._append_log(task_id, f"proxy: {message}"),
                    )
                except Exception as exc:  # noqa: BLE001 - log but continue
                    self._append_log(task_id, f"Proxy refresh failed: {exc}")
            try:
                result = run_codex(
                    sanitized_path,
                    prompt=task_prompt,
                    agent_type=task_agent_type,
                    model=task_model,
                    allowlist=effective_allowlist,
                    gitlab_host=gitlab_host,
                    gitlab_project_path=gitlab_project_path,
                    gitlab_token=gitlab_token,
                    codex_token=codex_token,
                    chatgpt_session_bundle=session_bundle_raw,
                    claude_api_key=os.environ.get("ANTHROPIC_API_KEY"),
                    claude_session_bundle=claude_session_raw,
                    target_branch=target_branch,
                    branch_name=branch_name,
                    mr_title=mr_title,
                    task_id=task_id,
                    log_fn=lambda message: self._append_log(task_id, f"codex: {message}"),
                )
            except (CodexRunnerError, Exception) as exc:  # noqa: BLE001 - surface failure to logs
                self._append_log(task_id, f"Codex execution error: {exc}")
                with Session(self._engine) as session:
                    task = session.get(Task, task_id)
                    if task is None:
                        return
                    task.status = TaskStatus.failed
                    task.finished_at = datetime.now(timezone.utc)
                    session.add(task)
                    session.commit()
                self._mark_complete(task_id)
                return

            runner_mode = "Docker" if result.used_docker else "local stub"
            self._append_log(task_id, f"Codex runner mode: {runner_mode}")
            if result.agent_version:
                self._append_log(task_id, f"Codex agent version: {result.agent_version}")
            if result.invocation_flags:
                flags_str = " ".join(result.invocation_flags)
                self._append_log(task_id, f"Codex invocation flags: {flags_str}")
            else:
                flags_str = ""

            if result.exit_code != 0:
                self._append_log(task_id, f"Codex FAIL (exit code {result.exit_code})")
                with Session(self._engine) as session:
                    task = session.get(Task, task_id)
                    if task is None:
                        return
                    task.status = TaskStatus.failed
                    task.finished_at = datetime.now(timezone.utc)
                    task.codex_agent_version = result.agent_version
                    task.codex_invocation = flags_str or None
                    session.add(task)
                    session.commit()
                self._mark_complete(task_id)
                return

            self._append_log(task_id, "Codex SUCCESS (exit code 0)")
            branch_record = result.branch or branch_name
            if branch_record:
                self._append_log(task_id, f"Branch pushed: {branch_record}")
            if result.mr_url:
                self._append_log(task_id, f"Merge request URL: {result.mr_url}")
            else:
                self._append_log(task_id, "Merge request URL unavailable; check runner output")
            self._append_log(task_id, "Task completed successfully")

            with Session(self._engine) as session:
                task = session.get(Task, task_id)
                if task is None:
                    return
                task.status = TaskStatus.done
                task.finished_at = datetime.now(timezone.utc)
                task.branch = branch_record or None
                task.mr_url = result.mr_url or None
                task.codex_agent_version = result.agent_version
                task.codex_invocation = flags_str or None
                session.add(task)
                session.commit()

            self._mark_complete(task_id)
        finally:
            self._set_active_task(None)
            self._clear_redactions(task_id)

    def _append_log(self, task_id: int, message: str) -> None:
        sanitized_message = self._sanitize_message(task_id, message)
        timestamp = datetime.now(timezone.utc).isoformat(timespec="seconds")
        line = f"[{timestamp}] {sanitized_message}"
        with self._lock:
            self._logs.setdefault(task_id, []).append(line)
        self._write_log_line(task_id, line)

    def _mark_complete(self, task_id: int) -> None:
        with self._lock:
            self._completed[task_id] = True

    def _log_state(self, task_id: int) -> Tuple[List[str], bool]:
        with self._lock:
            history = list(self._logs.get(task_id, []))
            done = self._completed.get(task_id, False)
        return history, done

    # Persistence & Redaction helpers ------------------------------------

    def _get_log_path(self, task_id: int) -> Path:
        path = self._log_paths.get(task_id)
        if path is None:
            path = LOG_STORAGE_DIR / f"{task_id}.log"
            self._log_paths[task_id] = path
        return path

    def _hydrate_logs_from_disk(self, task_id: int) -> None:
        path = self._get_log_path(task_id)
        if not path.exists():
            return
        try:
            with path.open("r", encoding="utf-8") as handle:
                persisted = [line.rstrip("\n") for line in handle]
        except OSError:
            return
        with self._lock:
            cache = self._logs.get(task_id)
            if not cache:
                self._logs[task_id] = persisted
            elif len(cache) < len(persisted):
                cache.extend(persisted[len(cache):])

    def _write_log_line(self, task_id: int, line: str) -> None:
        path = self._get_log_path(task_id)
        try:
            path.parent.mkdir(parents=True, exist_ok=True)
            with path.open("a", encoding="utf-8") as handle:
                handle.write(f"{line}\n")
        except OSError:
            # Disk persistence is best-effort; keep in-memory buffer if writes fail.
            pass

    def _sanitize_message(self, task_id: int, message: str) -> str:
        sanitized = SENSITIVE_ENV_PATTERN.sub(r"\1<redacted>", message)
        sanitized = sanitized.replace("GITLAB_TOKEN", "REDACTED_TOKEN")
        secrets = [value for value in self._redactions.get(task_id, []) if value]
        for secret in secrets:
            sanitized = sanitized.replace(secret, "<redacted>")
        return sanitized

    def _register_redactions(self, task_id: int, secrets: List[str]) -> None:
        filtered = [value for value in secrets if value]
        if not filtered:
            return
        augmented: List[str] = []
        for value in filtered:
            augmented.append(value)
            augmented.append(f"oauth2:{value}")
        with self._lock:
            existing = self._redactions.setdefault(task_id, [])
            for value in augmented:
                if value not in existing:
                    existing.append(value)

    def _clear_redactions(self, task_id: int) -> None:
        with self._lock:
            self._redactions.pop(task_id, None)

    # Credential + notification helpers ----------------------------------

    def _set_active_task(self, task_id: Optional[int]) -> None:
        with self._state_lock:
            self._active_task_id = task_id

    def _get_active_task_id(self) -> Optional[int]:
        with self._state_lock:
            return self._active_task_id

    def _clear_gitlab_token_cache(self) -> None:
        with self._cache_lock:
            self._gitlab_token_cache = None

    def _clear_chatgpt_session_cache(self) -> None:
        with self._cache_lock:
            self._chatgpt_session_cache = None
            self._chatgpt_session_known_missing = False
        with self._state_lock:
            self._chatgpt_session_present = False

    def _resolve_gitlab_token(self, session: Session) -> str:
        with self._cache_lock:
            cached = self._gitlab_token_cache
        if cached is not None:
            return cached

        token = get_gitlab_pat_token(session)
        value = token or ""
        with self._cache_lock:
            self._gitlab_token_cache = value
        with self._state_lock:
            self._gitlab_token_present = bool(value)
        return value

    def _resolve_chatgpt_session_bundle(self, session: Session) -> ChatGPTSessionMaterial | None:
        with self._cache_lock:
            cached = self._chatgpt_session_cache
            known_missing = self._chatgpt_session_known_missing
        if cached is not None:
            return cached
        if known_missing:
            with self._state_lock:
                self._chatgpt_session_present = False
            return None

        material = get_chatgpt_session_bundle(session)
        with self._cache_lock:
            if material is None:
                self._chatgpt_session_cache = None
                self._chatgpt_session_known_missing = True
            else:
                self._chatgpt_session_cache = material
                self._chatgpt_session_known_missing = False
        with self._state_lock:
            self._chatgpt_session_present = material is not None
        return material

    def _resolve_claude_session_bundle(self, session: Session) -> ClaudeSessionMaterial | None:
        with self._cache_lock:
            cached = self._claude_session_cache
            known_missing = self._claude_session_known_missing
        if cached is not None:
            return cached
        if known_missing:
            with self._state_lock:
                self._claude_session_present = False
            return None

        material = get_claude_session_bundle(session)
        with self._cache_lock:
            if material is None:
                self._claude_session_cache = None
                self._claude_session_known_missing = True
            else:
                self._claude_session_cache = material
                self._claude_session_known_missing = False
        with self._state_lock:
            self._claude_session_present = material is not None
        return material

    def notify_gitlab_pat_stored(self, actor: Optional[str], occurred_at: Optional[datetime]) -> None:
        self._clear_gitlab_token_cache()
        with self._state_lock:
            self._gitlab_token_present = True
        active_task = self._get_active_task_id()
        if active_task is None:
            return
        details: list[str] = []
        if actor:
            details.append(f"by {actor}")
        if occurred_at:
            details.append(f"at {occurred_at.isoformat()}")
        detail_str = " ".join(details)
        if detail_str:
            message = f"GitLab PAT stored {detail_str}; continuing with cached credential"
        else:
            message = "GitLab PAT stored; continuing with cached credential"
        self._append_log(active_task, message)

    def notify_gitlab_pat_cleared(self, actor: Optional[str], occurred_at: Optional[datetime]) -> None:
        self._clear_gitlab_token_cache()
        with self._state_lock:
            self._gitlab_token_present = False
        active_task = self._get_active_task_id()
        details: list[str] = []
        if actor:
            details.append(f"by {actor}")
        if occurred_at:
            details.append(f"at {occurred_at.isoformat()}")
        detail_str = " ".join(details)
        if active_task is not None:
            if detail_str:
                message = (
                    f"GitLab PAT cleared {detail_str}; new pushes will fail until a token is reconfigured"
                )
            else:
                message = "GitLab PAT cleared; new pushes will fail until a token is reconfigured"
            self._append_log(active_task, message)

    def fail_pending_tasks_due_to_missing_pat(
        self,
        actor: Optional[str],
        occurred_at: Optional[datetime],
    ) -> None:
        with Session(self._engine) as session:
            pending_tasks = session.exec(
                select(Task).where(Task.status == TaskStatus.pending)
            ).all()
            if not pending_tasks:
                return

            timestamp = datetime.now(timezone.utc)
            details: list[str] = []
            if actor:
                details.append(f"by {actor}")
            if occurred_at:
                details.append(f"at {occurred_at.isoformat()}")
            detail_str = " ".join(details)
            if detail_str:
                log_message = (
                    f"Pending task failed: GitLab PAT cleared {detail_str}; configure a token and retry"
                )
            else:
                log_message = "Pending task failed: GitLab PAT cleared; configure a token and retry"

            for task in pending_tasks:
                self._append_log(task.id, log_message)
                task.status = TaskStatus.failed
                task.finished_at = timestamp
                session.add(task)
                self._mark_complete(task.id)
            session.commit()

    def notify_chatgpt_session_rotated(
        self,
        actor: Optional[str],
        occurred_at: Optional[datetime],
    ) -> None:
        self._clear_chatgpt_session_cache()
        with self._state_lock:
            self._chatgpt_session_present = True
        active_task = self._get_active_task_id()
        if active_task is None:
            return
        details: list[str] = []
        if actor:
            details.append(f"by {actor}")
        if occurred_at:
            details.append(f"at {occurred_at.isoformat()}")
        detail_str = " ".join(details)
        if detail_str:
            message = f"ChatGPT session bundle rotated {detail_str}; future runs will refresh credentials"
        else:
            message = "ChatGPT session bundle rotated; future runs will refresh credentials"
        self._append_log(active_task, message)

    def notify_chatgpt_session_cleared(
        self,
        actor: Optional[str],
        occurred_at: Optional[datetime],
    ) -> None:
        self._clear_chatgpt_session_cache()
        active_task = self._get_active_task_id()
        details: list[str] = []
        if actor:
            details.append(f"by {actor}")
        if occurred_at:
            details.append(f"at {occurred_at.isoformat()}")
        detail_str = " ".join(details)
        if active_task is not None:
            if detail_str:
                message = (
                    f"ChatGPT session bundle cleared {detail_str}; tasks without API tokens will now fail until re-imported"
                )
            else:
                message = (
                    "ChatGPT session bundle cleared; tasks without API tokens will now fail until re-imported"
                )
            self._append_log(active_task, message)
