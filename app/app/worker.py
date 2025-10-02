from __future__ import annotations

import asyncio
import base64
import logging
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
from .codex_models import (
    default_model_id,
    default_reasoning_effort,
    valid_model_ids,
    valid_reasoning_efforts,
)
from .codex_runner import CodexRunnerAborted, CodexRunnerError, run_codex
from .integrations import (
    ChatGPTSessionError,
    ChatGPTSessionMaterial,
    get_chatgpt_session_bundle,
    get_gitlab_pat_token,
)
from .models import Project, Task, TaskStatus
from .project_cache import (
    ProjectCacheError,
    bootstrap_project_cache,
    enforce_cache_policy,
    project_cache_identifier,
    project_cache_repo_path,
    refresh_project_cache,
    snapshot_project_cache,
)
from .proxy_runtime import ensure_proxy_stack
from .sanitizer import sanitize_workspace
from .secrets import SecretError

LOG_POLL_INTERVAL_SECONDS = 0.5
BRANCH_PREFIX = "codex/task"
REPO_ROOT = Path(__file__).resolve().parents[2]
LOG_STORAGE_DIR = REPO_ROOT / "workspaces" / "logs"
SENSITIVE_ENV_PATTERN = re.compile(r"(GITLAB_TOKEN=)([^\s]+)")


logger = logging.getLogger(__name__)


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


def _is_truthy(value: str | None) -> bool:
    if value is None:
        return False
    return value.strip().lower() in {"1", "true", "yes", "on"}


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
        self._abort_signals: Dict[int, Event] = {}
        self._terminal_events: Dict[int, str] = {}
        self._active_task_id: Optional[int] = None
        self._gitlab_token_cache: Optional[str] = None
        self._gitlab_token_present: bool = False
        self._chatgpt_session_cache: ChatGPTSessionMaterial | None = None
        self._chatgpt_session_known_missing: bool = False
        self._chatgpt_session_present: bool = False
        self._boot_time = datetime.now(timezone.utc)
        LOG_STORAGE_DIR.mkdir(parents=True, exist_ok=True)
        self._thread = Thread(target=self._run, name="task-worker", daemon=True)
        self._recover_interrupted_tasks()
        self._thread.start()

    def enqueue(self, task_id: int) -> None:
        self._hydrate_logs_from_disk(task_id)
        self._ensure_abort_signal(task_id)
        with self._lock:
            self._logs.setdefault(task_id, [])
            self._completed.setdefault(task_id, False)
        self._tasks.put(task_id)

    def register_task(self, task_id: int) -> None:
        self._hydrate_logs_from_disk(task_id)
        self._ensure_abort_signal(task_id)
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
            except Exception as exc:  # noqa: BLE001 - surface unexpected crashes without killing the worker
                self._append_log(task_id, f"Task execution crashed: {exc}")
                with Session(self._engine) as session:
                    task = session.get(Task, task_id)
                    if task is not None and task.status not in {
                        TaskStatus.done,
                        TaskStatus.failed,
                        TaskStatus.aborted,
                    }:
                        task.status = TaskStatus.failed
                        task.finished_at = datetime.now(timezone.utc)
                        session.add(task)
                        session.commit()
                self._mark_complete(task_id)
            finally:
                self._tasks.task_done()

    def _recover_interrupted_tasks(self) -> None:
        with Session(self._engine) as session:
            stuck_tasks = session.exec(
                select(Task)
                .where(Task.status.in_([TaskStatus.pending, TaskStatus.running]))
                .where(Task.created_at < self._boot_time)
            ).all()
            if not stuck_tasks:
                return

            timestamp = datetime.now(timezone.utc)
            marked: list[int] = []
            for task in stuck_tasks:
                if task.id is None:
                    continue
                previous_status = task.status
                self.register_task(task.id)
                if previous_status == TaskStatus.running:
                    message = (
                        "Task interrupted by orchestrator restart; marking as failed so it can be resubmitted"
                    )
                else:
                    message = (
                        "Task never started before orchestrator restart; marking as failed so it can be resubmitted"
                    )
                self._append_log(task.id, message)
                task.status = TaskStatus.failed
                task.finished_at = timestamp
                session.add(task)
                marked.append(task.id)
            session.commit()

        for task_id in marked:
            self._mark_complete(task_id, terminal_event="failed")

    def _process_task(self, task_id: int) -> None:
        self._set_active_task(task_id)
        abort_signal = self._get_abort_signal(task_id)
        project_root: Path | None = None
        task_prompt = ""
        project_allowlist: list[str] = []
        project_gitlab_host = ""
        gitlab_token = ""
        project_default_branch = ""
        project_gitlab_token_value = ""
        project_cache_quota_mb: int | None = None
        project_cache_prune_after_hours: int | None = None
        session_bundle: ChatGPTSessionMaterial | None = None
        session_bundle_error: str | None = None
        branch_name = ""
        branch_was_provided = False
        mr_title = ""
        target_branch = ""
        gitlab_host = ""
        gitlab_project_path = ""
        codex_model = default_model_id() or None
        codex_reasoning_effort = default_reasoning_effort()
        try:
            with Session(self._engine) as session:
                task = session.get(Task, task_id)
                if task is None:
                    return
                if task.status == TaskStatus.aborted:
                    self._mark_complete(task_id, terminal_event="aborted")
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
                if self._abort_if_requested(
                    task_id,
                    session,
                    message="Abort requested before task start; skipping execution",
                ):
                    return
                project_root = project_cache_repo_path(project.gitlab_host, project.gitlab_project_path)
                cache_identifier = project_cache_identifier(project.gitlab_host, project.gitlab_project_path)
                project_default_branch = project.default_branch
                project_gitlab_token_value = (project.gitlab_token or "").strip()
                project_cache_quota_mb = project.cache_quota_mb
                project_cache_prune_after_hours = project.cache_prune_after_hours
                task.status = TaskStatus.running
                task.started_at = datetime.now(timezone.utc)
                task_prompt = task.prompt or ""
                stored_mr_title = (task.mr_title or "").strip()
                if stored_mr_title:
                    mr_title = stored_mr_title
                else:
                    mr_title = _build_mr_title(task_id, task_prompt)
                    task.mr_title = mr_title
                project_allowlist = list(project.allowlist or [])
                stored_target_branch = (task.target_branch or "").strip()
                if stored_target_branch:
                    target_branch = stored_target_branch
                else:
                    target_branch = project_default_branch
                    if target_branch:
                        task.target_branch = target_branch
                        session.add(task)
                        session.commit()
                gitlab_host = project.gitlab_host
                gitlab_project_path = project.gitlab_project_path
                branch_name = (task.branch or "").strip() or _generate_branch_name(task_id)
                branch_was_provided = bool(task.branch)
                if not branch_was_provided:
                    task.branch = branch_name
                task_model = (task.codex_model or "").strip()
                if not task_model:
                    codex_model = default_model_id()
                elif task_model not in valid_model_ids():
                    codex_model = default_model_id()
                else:
                    codex_model = task_model
                task_effort = (task.codex_reasoning_effort or "").strip().lower()
                if task_effort in valid_reasoning_efforts():
                    codex_reasoning_effort = task_effort
                else:
                    codex_reasoning_effort = default_reasoning_effort()
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
                try:
                    session_bundle = self._resolve_chatgpt_session_bundle(session)
                except ChatGPTSessionError as exc:
                    session_bundle_error = str(exc)
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

            require_codex_session = os.environ.get("RUNNER_DISABLE_DOCKER", "0") != "1"
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

            using_session_bundle = bool(session_bundle_raw)
            credential_error: str | None = None
            if not using_session_bundle and require_codex_session:
                credential_error = (
                    session_bundle_error
                    or "Codex credentials unavailable; import a ChatGPT session bundle via Settings -> Integrations"
                )

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
            if using_session_bundle:
                if session_bundle_expires_at is not None:
                    credential_description = (
                        "Codex credential: using ChatGPT session bundle (expires "
                        f"{session_bundle_expires_at.isoformat()})"
                    )
                else:
                    credential_description = "Codex credential: using ChatGPT session bundle"
            elif not require_codex_session:
                credential_description = "Codex credential: not required (Docker disabled)"

            if credential_description:
                self._append_log(task_id, credential_description)

            if session_bundle_error:
                if not require_codex_session:
                    self._append_log(
                        task_id,
                        f"ChatGPT session bundle unusable ({session_bundle_error}); continuing with local stub",
                    )

            if self._abort_if_requested(
                task_id,
                session,
                message="Abort requested before workspace preparation; stopping task",
            ):
                return

            redactions = [gitlab_token]
            if session_bundle_raw:
                redactions.append(session_bundle_raw)
                try:
                    redactions.append(base64.b64encode(session_bundle_raw.encode("utf-8")).decode("ascii"))
                except Exception:
                    # Base64 encoding failure should not block task execution; raw value already registered.
                    pass
            self._register_redactions(task_id, redactions)
            if not mr_title:
                mr_title = _build_mr_title(task_id, task_prompt)
            mr_title_display = " ".join(str(mr_title).splitlines())
            self._append_log(task_id, f"Merge request title: {mr_title_display}")
            if target_branch:
                if project_default_branch and target_branch != project_default_branch:
                    self._append_log(task_id, f"Base branch override: {target_branch}")
                else:
                    self._append_log(task_id, f"Base branch: {target_branch}")
            else:
                self._append_log(task_id, "Base branch unavailable; falling back to project default")
            if branch_was_provided:
                self._append_log(task_id, f"Using requested branch: {branch_name}")
            else:
                self._append_log(task_id, f"Proposed branch name: {branch_name}")
            self._append_log(
                task_id,
                f"Codex model: {codex_model} (reasoning effort: {codex_reasoning_effort})",
            )

            if project_root is None:
                self._append_log(task_id, "Unable to determine project root; aborting")
                return

            dry_run_enabled = _is_truthy(os.environ.get("RUNNER_GIT_DRY_RUN"))
            effective_gitlab_token = (gitlab_token or "").strip() or project_gitlab_token_value

            self._append_log(
                task_id,
                f"RUNNER_GIT_DRY_RUN evaluated to {int(dry_run_enabled)} for cache root {project_root}",
            )

            self._append_log(task_id, f"Ensuring project cache {cache_identifier} at {project_root}")
            try:
                bootstrap_project_cache(
                    project_root,
                    gitlab_host=gitlab_host,
                    gitlab_project_path=gitlab_project_path,
                    default_branch=target_branch,
                    gitlab_token=effective_gitlab_token or None,
                    dry_run=dry_run_enabled,
                    log_fn=lambda message: self._append_log(task_id, message),
                )
            except ProjectCacheError as exc:
                self._append_log(task_id, str(exc))
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

            commit_hash: str | None = None

            self._append_log(task_id, f"Refreshing project cache at {project_root}")
            try:
                commit_hash = refresh_project_cache(
                    project_root,
                    target_branch,
                    gitlab_token=effective_gitlab_token or None,
                    dry_run=dry_run_enabled,
                    log_fn=lambda message: self._append_log(task_id, message),
                    project_identifier=cache_identifier,
                )
                enforce_cache_policy(
                    project_root,
                    quota_mb=project_cache_quota_mb,
                    prune_after_hours=project_cache_prune_after_hours,
                    dry_run=dry_run_enabled,
                    log_fn=lambda message: self._append_log(task_id, message),
                )
                snapshot_path = snapshot_project_cache(
                    project_root,
                    commit_hash=commit_hash or "",
                    branch=target_branch or project_default_branch or "",
                    dry_run=dry_run_enabled,
                    log_fn=lambda message: self._append_log(task_id, message),
                )
                if snapshot_path is not None and not dry_run_enabled:
                    self._append_log(task_id, f"Cache snapshot stored at {snapshot_path}")
            except ProjectCacheError as exc:
                self._append_log(task_id, str(exc))
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

            if commit_hash and commit_hash not in {"dry-run-skip"}:
                short_hash = commit_hash[:12]
                revision_note = f"{target_branch}@{short_hash} ({commit_hash})"
            elif commit_hash == "dry-run-skip":
                revision_note = "dry-run skip (no commit)"
            else:
                revision_note = "revision unavailable"

            self._append_log(
                task_id,
                f"Task started; sanitizing workspace from cache {cache_identifier} at {project_root} using {revision_note}",
            )

            try:
                sanitized_path = sanitize_workspace(
                    project_root,
                    task_id,
                    default_branch=target_branch,
                    gitlab_token=effective_gitlab_token or None,
                )
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

            git_dir = Path(sanitized_path) / ".git"
            if not git_dir.exists():
                self._append_log(
                    task_id,
                    f"Sanitized workspace {sanitized_path} missing .git directory",
                )

            self._append_log(task_id, f"Workspace ready at {sanitized_path}")
            with Session(self._engine) as session:
                task = session.get(Task, task_id)
                if task is None:
                    return
                task.workspace_path = str(sanitized_path)
                task.cache_commit = commit_hash
                session.add(task)
                session.commit()
                if self._abort_if_requested(
                    task_id,
                    session,
                    message="Abort requested after workspace preparation; stopping task",
                ):
                    return

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
                effective_allowlist = merge_allowlists(project_gitlab_host, project_allowlist)
            except Exception as exc:  # noqa: BLE001 - capture normalization failures
                effective_allowlist = list(project_allowlist)
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
            with Session(self._engine) as session:
                task = session.get(Task, task_id)
                if task is None:
                    return
                if self._abort_if_requested(
                    task_id,
                    session,
                    message="Abort requested before codex launch; stopping task",
                ):
                    return
            try:
                result = run_codex(
                    sanitized_path,
                    prompt=task_prompt,
                    allowlist=effective_allowlist,
                    gitlab_host=gitlab_host,
                    gitlab_project_path=gitlab_project_path,
                    gitlab_token=gitlab_token,
                    chatgpt_session_bundle=session_bundle_raw,
                    target_branch=target_branch,
                    branch_name=branch_name,
                    mr_title=mr_title,
                    task_id=task_id,
                    codex_model=codex_model,
                    codex_reasoning_effort=codex_reasoning_effort,
                    log_fn=lambda message: self._append_log(task_id, f"codex: {message}"),
                    abort_event=abort_signal,
                )
            except CodexRunnerAborted:
                self._append_log(task_id, "Abort acknowledged by codex runner; stopping task")
                with Session(self._engine) as session:
                    task = session.get(Task, task_id)
                    if task is None:
                        return
                    task.status = TaskStatus.aborted
                    task.finished_at = datetime.now(timezone.utc)
                    session.add(task)
                    session.commit()
                self._mark_complete(task_id, terminal_event="aborted")
                return
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
                    task.codex_model = result.codex_model or codex_model
                    task.codex_reasoning_effort = (
                        result.codex_reasoning_effort or codex_reasoning_effort
                    )
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
                task.codex_model = result.codex_model or codex_model
                task.codex_reasoning_effort = (
                    result.codex_reasoning_effort or codex_reasoning_effort
                )
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

    def _mark_complete(self, task_id: int, *, terminal_event: str = "done") -> None:
        with self._lock:
            self._completed[task_id] = True
            self._terminal_events[task_id] = terminal_event
        signal = self._abort_signals.pop(task_id, None)
        if signal is not None:
            signal.set()

    def _log_state(self, task_id: int) -> Tuple[List[str], bool]:
        with self._lock:
            history = list(self._logs.get(task_id, []))
            done = self._completed.get(task_id, False)
        return history, done

    def _ensure_abort_signal(self, task_id: int) -> Event:
        with self._lock:
            signal = self._abort_signals.get(task_id)
            if signal is None:
                signal = Event()
                self._abort_signals[task_id] = signal
        return signal

    def _get_abort_signal(self, task_id: int) -> Event:
        return self._ensure_abort_signal(task_id)

    def record_task_log(self, task_id: int, message: str) -> None:
        self._append_log(task_id, message)

    def request_abort(self, task_id: int) -> None:
        signal = self._ensure_abort_signal(task_id)
        signal.set()

    def mark_task_aborted(self, task_id: int) -> None:
        self._ensure_abort_signal(task_id).set()
        self._mark_complete(task_id, terminal_event="aborted")

    def handle_task_deleted(self, task_id: int) -> None:
        self._mark_complete(task_id, terminal_event="deleted")
        with self._lock:
            self._logs.pop(task_id, None)
        self._remove_log_file(task_id)

    def get_terminal_event(self, task_id: int) -> Optional[str]:
        with self._lock:
            return self._terminal_events.get(task_id)

    def _abort_if_requested(
        self,
        task_id: int,
        session: Session,
        message: Optional[str] = None,
    ) -> bool:
        task = session.get(Task, task_id)
        if task is None:
            return False
        signal = self._ensure_abort_signal(task_id)
        if not (task.abort_requested or signal.is_set()):
            return False
        if message:
            self._append_log(task_id, message)
        task.status = TaskStatus.aborted
        task.finished_at = datetime.now(timezone.utc)
        session.add(task)
        session.commit()
        self._mark_complete(task_id, terminal_event="aborted")
        return True

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
        except OSError as exc:
            logger.warning(
                "Failed to read persisted logs for task %s from %s: %s",
                task_id,
                path,
                exc,
                exc_info=True,
            )
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
        except OSError as exc:
            logger.warning(
                "Failed to append task %s log entry to %s: %s",
                task_id,
                path,
                exc,
                exc_info=True,
            )
            # Disk persistence is best-effort; keep in-memory buffer if writes fail.

    def _remove_log_file(self, task_id: int) -> None:
        path = self._log_paths.pop(task_id, None)
        if path is None:
            path = LOG_STORAGE_DIR / f"{task_id}.log"
        try:
            path.unlink()
        except OSError:
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
                    f"ChatGPT session bundle cleared {detail_str}; Docker-backed runs will fail until a new bundle is imported"
                )
            else:
                message = (
                    "ChatGPT session bundle cleared; Docker-backed runs will fail until a new bundle is imported"
                )
            message += ". Stub-only runs (RUNNER_DISABLE_DOCKER=1) remain available."
            self._append_log(active_task, message)
