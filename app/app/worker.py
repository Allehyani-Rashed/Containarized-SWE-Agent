from __future__ import annotations

import asyncio
import base64
import logging
import os
import re
from datetime import datetime, timezone
from pathlib import Path
from threading import RLock
from typing import Any, AsyncGenerator, Dict, Iterable, List, Optional, Tuple
from uuid import uuid4

from sqlmodel import Session, select

from .allowlist import apply_project_allowlist, clear_task_allowlist, merge_allowlists
from .codex_models import (
    default_model_id,
    default_reasoning_effort,
    valid_model_ids,
    valid_reasoning_efforts,
)
from .codex_runner import CodexExecutionService, CodexRunnerAborted, CodexRunnerError
from .integrations import ChatGPTSessionError, ChatGPTSessionMaterial, CredentialRuntimeCache
from .models import Project, Task, TaskChangeMode, TaskStatus
from .project_cache import (
    BreakoutEvent,
    ProjectCacheCallbacks,
    ProjectCacheError,
    ProjectCacheService,
    RefreshEvent,
    SnapshotPrunedEvent,
)
from .metrics import worker_metrics
from .proxy_runtime import preflight_proxy_stack
from .worker_scheduler import TaskScheduleMetadata, WorkerScheduler
from .worker_state import TaskRuntimeState
from .sanitizer import sanitize_workspace
from .settings_store import (
    default_project_concurrency,
    get_project_concurrency_limit,
    PROJECT_CONCURRENCY_DEFAULT,
    PROJECT_CONCURRENCY_ENV,
)

LOG_POLL_INTERVAL_SECONDS = 0.5
BRANCH_PREFIX = "codex/task"
REPO_ROOT = Path(__file__).resolve().parents[2]
LOG_STORAGE_DIR = REPO_ROOT / "workspaces" / "logs"
SENSITIVE_ENV_PATTERN = re.compile(r"(GITLAB_TOKEN=)([^\s]+)")

WORKER_MAX_CONCURRENCY_ENV = "WORKER_MAX_CONCURRENCY"
PROJECT_MAX_CONCURRENCY_DEFAULT_ENV = PROJECT_CONCURRENCY_ENV
WORKER_ENABLE_PARALLEL_ENV = "WORKER_ENABLE_PARALLEL"
DEFAULT_MAX_CONCURRENCY = 10
DEFAULT_PROJECT_CONCURRENCY = PROJECT_CONCURRENCY_DEFAULT


logger = logging.getLogger(__name__)


def _parse_positive_int_env(env_name: str, default: int) -> int:
    raw = os.environ.get(env_name)
    if raw is None:
        return default
    try:
        value = int(raw)
    except (TypeError, ValueError):
        logger.warning(
            "Invalid value '%s' for %s; falling back to default %s",
            raw,
            env_name,
            default,
        )
        return default
    if value <= 0:
        logger.warning(
            "%s must be a positive integer; received %s. Falling back to %s",
            env_name,
            value,
            default,
        )
        return default
    return value


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
    """Background worker manager that dispatches queued tasks to a thread pool."""

    def __init__(self, engine) -> None:
        self._engine = engine
        self._state_lock = RLock()
        self._runtime_state: Dict[int, TaskRuntimeState] = {}
        self._credential_cache = CredentialRuntimeCache()
        self._boot_time = datetime.now(timezone.utc)
        self._max_concurrency = _parse_positive_int_env(
            WORKER_MAX_CONCURRENCY_ENV,
            DEFAULT_MAX_CONCURRENCY,
        )

        self._project_cache_callbacks = ProjectCacheCallbacks(
            on_refresh_complete=self._handle_cache_refresh_event,
            on_snapshot_pruned=self._handle_cache_snapshot_pruned,
            on_breakout_detected=self._handle_cache_breakout,
        )
        self._project_cache_service = ProjectCacheService(
            callbacks=self._project_cache_callbacks,
            logger=logger,
        )
        parallel_env = os.environ.get(WORKER_ENABLE_PARALLEL_ENV)
        if parallel_env is None:
            self._parallel_enabled = True
        else:
            self._parallel_enabled = _is_truthy(parallel_env)
        if not self._parallel_enabled:
            if self._max_concurrency > 1:
                logger.warning(
                    "Parallel task execution disabled via %s=%s; clamping concurrency to 1",
                    WORKER_ENABLE_PARALLEL_ENV,
                    parallel_env,
                )
            self._max_concurrency = 1
        self._project_concurrency_limit = self._load_project_concurrency_limit()
        LOG_STORAGE_DIR.mkdir(parents=True, exist_ok=True)
        self._metrics = worker_metrics()
        self._project_last_reported_counts: Dict[int, int] = {}
        self._task_project_limits: Dict[int, Tuple[int, int]] = {}
        self._codex_service = CodexExecutionService()
        self._scheduler = WorkerScheduler(
            max_workers=self._max_concurrency,
            metrics=self._metrics,
            task_executor=self._run_task_wrapper,
            metadata_resolver=self._resolve_task_schedule,
            project_recorder=self._record_active_count,
            failure_handler=self._handle_scheduling_failure,
            completion_callback=self._handle_scheduler_completion,
            unexpected_error_handler=self._handle_worker_exception,
        )
        self._recover_interrupted_tasks()
        self._scheduler.start()

    def _handle_cache_refresh_event(self, event: RefreshEvent) -> None:
        short_hash = event.commit_hash[:12]
        logger.info(
            "Cache %s refreshed to %s in %.2fs (dry_run=%s)",
            event.identifier,
            short_hash,
            event.duration_seconds,
            int(event.dry_run),
        )

    def _handle_cache_snapshot_pruned(self, event: SnapshotPrunedEvent) -> None:
        logger.info("Pruned cache snapshot %s for %s", event.removed_path, event.identifier)

    def _handle_cache_breakout(self, event: BreakoutEvent) -> None:
        logger.error(
            "Breakout sentinel triggered for %s (%s); investigate container isolation",
            event.identifier,
            event.reason,
        )

    def _get_state(self, task_id: int) -> TaskRuntimeState | None:
        with self._state_lock:
            return self._runtime_state.get(task_id)

    def _ensure_state(self, task_id: int) -> TaskRuntimeState:
        state = self._get_state(task_id)
        if state is not None:
            return state
        self._hydrate_credential_cache()
        new_state = TaskRuntimeState(task_id=task_id, log_directory=LOG_STORAGE_DIR)
        with self._state_lock:
            state = self._runtime_state.setdefault(task_id, new_state)
        if state is new_state:
            state.hydrate_from_disk()
            state.initialize_credentials(
                gitlab_available=self._credential_cache.gitlab_available(),
                chatgpt_available=self._credential_cache.chatgpt_available(),
            )
        return state

    def _load_project_concurrency_limit(self) -> int:
        with Session(self._engine) as session:
            limit = get_project_concurrency_limit(session)
        return max(1, limit)

    def _teardown_runtime_state(self, task_id: int, *, remove_logs: bool = False) -> None:
        with self._state_lock:
            state = self._runtime_state.pop(task_id, None)
        if state is None:
            return
        if remove_logs:
            state.teardown()
        else:
            state.clear_redactions()

    def get_active_task_ids(self) -> List[int]:
        return self._scheduler.get_active_task_ids()

    def get_worker_pool_size(self) -> int:
        return self._max_concurrency

    @property
    def parallel_enabled(self) -> bool:
        return self._parallel_enabled

    def _update_runtime_credentials(
        self,
        *,
        gitlab_available: Optional[bool] = None,
        chatgpt_available: Optional[bool] = None,
        force: bool = False,
        task_ids: Optional[Iterable[int]] = None,
    ) -> None:
        if gitlab_available is None and chatgpt_available is None and not force:
            return
        with self._state_lock:
            if task_ids is None:
                states = list(self._runtime_state.values())
            else:
                states = [
                    self._runtime_state.get(task_id)
                    for task_id in task_ids
                    if task_id in self._runtime_state
                ]
        for state in states:
            if state is None:
                continue
            state.update_credentials(
                gitlab_available=gitlab_available,
                chatgpt_available=chatgpt_available,
                force=force,
            )

    def _hydrate_credential_cache(self) -> None:
        need_gitlab = not self._credential_cache.gitlab_loaded()
        need_chatgpt = not self._credential_cache.chatgpt_loaded()
        if not need_gitlab and not need_chatgpt:
            return

        gitlab_changed = False
        chatgpt_changed = False
        with Session(self._engine) as session:
            if need_gitlab:
                _, gitlab_changed = self._credential_cache.resolve_gitlab_token(session)
            if need_chatgpt:
                _, chatgpt_changed = self._credential_cache.resolve_chatgpt_session(session)

        if gitlab_changed or chatgpt_changed:
            self._update_runtime_credentials(
                gitlab_available=(
                    self._credential_cache.gitlab_available() if gitlab_changed else None
                ),
                chatgpt_available=(
                    self._credential_cache.chatgpt_available() if chatgpt_changed else None
                ),
            )

    def enqueue(self, task_id: int) -> None:
        state = self._ensure_state(task_id)
        state.hydrate_from_disk()
        state.reset_for_run()
        self._scheduler.enqueue(task_id)

    def register_task(self, task_id: int) -> None:
        state = self._ensure_state(task_id)
        state.hydrate_from_disk()

    def get_logs_snapshot(self, task_id: int) -> List[str]:
        state = self._ensure_state(task_id)
        state.hydrate_from_disk()
        history, _ = state.snapshot()
        return history

    def is_complete(self, task_id: int) -> bool:
        state = self._ensure_state(task_id)
        _, done = state.snapshot()
        return done

    def get_task_credentials(self, task_id: int) -> Dict[str, Any]:
        state = self._get_state(task_id)
        if state is not None:
            return state.credential_snapshot()
        self._hydrate_credential_cache()
        return {
            "task_id": task_id,
            "gitlab_pat_available": self._credential_cache.gitlab_available(),
            "gitlab_pat_last_updated": None,
            "chatgpt_session_available": self._credential_cache.chatgpt_available(),
            "chatgpt_session_last_updated": None,
        }

    async def stream_logs(self, task_id: int) -> AsyncGenerator[Dict[str, Any] | str, None]:
        """Yield log lines and structured events as Server-Sent Events."""
        state = self._ensure_state(task_id)
        state.hydrate_from_disk()
        cursor = 0
        while True:
            history, done = self._log_state(task_id)
            while cursor < len(history):
                yield history[cursor]
                cursor += 1
            events = self._drain_runtime_events(task_id)
            for event in events:
                yield event
            if done:
                if not events:
                    break
            else:
                await asyncio.sleep(LOG_POLL_INTERVAL_SECONDS)

    def _drain_runtime_events(self, task_id: int) -> List[Dict[str, Any]]:
        state = self._get_state(task_id)
        if state is None:
            return []
        return state.drain_events()

    def _prepare_cache_environment(
        self,
        workspace: Path,
        task_id: int,
        state: TaskRuntimeState,
    ) -> Dict[str, str]:
        state.clear_abort_file()
        cache_root = workspace / ".codex-cache" / str(task_id)
        directories = {
            "CODEX_CACHE_DIR": cache_root / "codex",
            "UV_CACHE_DIR": cache_root / "uv",
            "XDG_CACHE_HOME": cache_root / "xdg",
        }
        env: Dict[str, str] = {}
        for key, path in directories.items():
            try:
                path.mkdir(parents=True, exist_ok=True)
            except OSError as exc:
                self._log_for(task_id, f"cache: failed to create {path}: {exc}")
                continue
            env[key] = str(path)
            state.register_cache_directory(key, path)
        abort_file = cache_root / "abort.signal"
        try:
            abort_file.parent.mkdir(parents=True, exist_ok=True)
            abort_file.write_text("ready\n", encoding="utf-8")
        except OSError as exc:
            self._log_for(task_id, f"cache: failed to stage abort marker {abort_file}: {exc}")
        else:
            state.set_abort_file(abort_file)
            try:
                relative_abort = abort_file.relative_to(workspace)
            except ValueError:
                relative_abort = abort_file
            env["CODEX_ABORT_FILE"] = str(relative_abort)
        return env

    def _record_active_count(self, project_id: int, count: int) -> None:
        effective_count = max(count, 0)
        with self._state_lock:
            previous = self._project_last_reported_counts.get(project_id)
            if previous == effective_count:
                return
            self._project_last_reported_counts[project_id] = effective_count
        try:
            with Session(self._engine) as session:
                project = session.get(Project, project_id)
                if project is None:
                    return
                project.last_active_count = effective_count
                session.add(project)
                session.commit()
        except Exception as exc:  # noqa: BLE001 - persistence is best-effort
            logger.warning(
                "Failed to persist last_active_count=%s for project %s: %s",
                effective_count,
                project_id,
                exc,
            )

    def shutdown(self) -> None:
        self._scheduler.shutdown()

    # Scheduler integration -------------------------------------------------

    def _run_task_wrapper(self, task_id: int) -> None:
        self._process_task(task_id)

    def _handle_scheduler_completion(self, task_id: int) -> None:
        with self._state_lock:
            self._task_project_limits.pop(task_id, None)

    def _handle_worker_exception(self, task_id: int, exc: Exception) -> None:
        logger.exception("Task %s raised an unexpected error: %s", task_id, exc)

    def _handle_scheduling_failure(
        self,
        task_id: int,
        exc: Exception,
        *,
        stage: str,
    ) -> None:
        """Log scheduling failures, clean up state, and mark the task as failed."""

        try:
            self._log_for(task_id, f"Task scheduling failed during {stage}: {exc}")
        except Exception:  # noqa: BLE001 - logging should not block cleanup
            logger.debug("Failed to log scheduling failure for task %s", task_id, exc_info=True)

        with self._state_lock:
            self._task_project_limits.pop(task_id, None)

        marked_failed = False
        should_mark_aborted = False
        try:
            with Session(self._engine) as session:
                task = session.get(Task, task_id)
                if task is None:
                    task = None
                elif task.status == TaskStatus.aborted:
                    session.add(task)
                    session.commit()
                    should_mark_aborted = True
                elif task.status == TaskStatus.pending:
                    task.status = TaskStatus.failed
                    task.finished_at = datetime.now(timezone.utc)
                    session.add(task)
                    session.commit()
                    marked_failed = True
        except Exception as db_exc:  # noqa: BLE001 - keep worker alive on persistence issues
            logger.warning(
                "Failed to persist scheduling failure for task %s: %s",
                task_id,
                db_exc,
            )
            return

        if should_mark_aborted:
            self._mark_complete(task_id, terminal_event="aborted")
            return

        if marked_failed:
            self._mark_complete(task_id, terminal_event="failed")

    def get_project_concurrency_limit(self) -> int:
        with self._state_lock:
            return self._project_concurrency_limit

    def set_project_concurrency_limit(self, limit: int) -> None:
        if limit < 1:
            raise ValueError("Project concurrency limit must be at least 1")
        with self._state_lock:
            self._project_concurrency_limit = limit
            self._task_project_limits.clear()
        self._scheduler.clear_cached_metadata()

    def _get_task_project_limit(self, task_id: int) -> Optional[Tuple[int, int]]:
        with self._state_lock:
            cached = self._task_project_limits.get(task_id)
        if cached is not None:
            return cached

        with Session(self._engine) as session:
            task = session.get(Task, task_id)
            if task is None:
                logger.warning("Unable to locate task %s while scheduling", task_id)
                return None

            project = session.get(Project, task.project_id)
            if project is None:
                logger.warning(
                    "Unable to locate project %s for task %s; marking as failed",
                    task.project_id,
                    task_id,
                )
                self._log_for(
                    task_id,
                    "Task failed: project configuration missing; contact an operator",
                )
                task.status = TaskStatus.failed
                task.finished_at = datetime.now(timezone.utc)
                session.add(task)
                session.commit()
                self._mark_complete(task_id, terminal_event="failed")
                return None

            limit = self._project_concurrency_limit
            if limit < 1:
                limit = DEFAULT_PROJECT_CONCURRENCY
            info = (project.id, limit)

        with self._state_lock:
            self._task_project_limits[task_id] = info

        return info

    def _resolve_task_schedule(self, task_id: int) -> TaskScheduleMetadata | None:
        scheduling_info = self._get_task_project_limit(task_id)
        if scheduling_info is None:
            return None
        project_id, project_limit = scheduling_info
        return TaskScheduleMetadata(project_id, project_limit)

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
                self._log_for(task.id, message)
                task.status = TaskStatus.failed
                task.finished_at = timestamp
                session.add(task)
                marked.append(task.id)
            session.commit()

        for task_id in marked:
            self._mark_complete(task_id, terminal_event="failed")

    def _process_task(self, task_id: int) -> None:
        state = self._ensure_state(task_id)
        state.reset_for_run()
        abort_signal = state.abort_event
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
        change_mode = TaskChangeMode.merge_request
        proxy_log = None
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
                    self._log_for(task_id, "Project not found for task; marking as failed")
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
                gitlab_host = project.gitlab_host or ""
                gitlab_project_path = project.gitlab_project_path or ""
                project_root = self._project_cache_service.repo_path_for(gitlab_host, gitlab_project_path)
                cache_identifier = self._project_cache_service.identifier_for(gitlab_host, gitlab_project_path)
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
                branch_name = (task.branch or "").strip() or _generate_branch_name(task_id)
                branch_was_provided = bool(task.branch)
                if not branch_was_provided:
                    task.branch = branch_name
                change_mode = task.change_mode or TaskChangeMode.merge_request
                task.change_mode = change_mode
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
                gitlab_token = self._resolve_gitlab_token(session)
                try:
                    session_bundle = self._resolve_chatgpt_session_bundle(session)
                except ChatGPTSessionError as exc:
                    session_bundle_error = str(exc)
                project_gitlab_host = gitlab_host
                session.add(task)
                session.commit()

            effective_gitlab_token = (
                (project_gitlab_token_value or "").strip()
                or (gitlab_token or "").strip()
            )

            if not effective_gitlab_token:
                self._log_for(task_id, "GitLab PAT missing; configure a token via Settings -> Integrations")
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
                self._log_for(task_id, credential_error)
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
                self._log_for(task_id, credential_description)

            if session_bundle_error:
                if not require_codex_session:
                    self._log_for(
                        task_id,
                        f"ChatGPT session bundle unusable ({session_bundle_error}); continuing with local stub",
                    )

            with Session(self._engine) as session:
                if self._abort_if_requested(
                    task_id,
                    session,
                    message="Abort requested before workspace preparation; stopping task",
                ):
                    return

            redactions: list[str] = []
            if gitlab_token:
                redactions.append(gitlab_token)
            if project_gitlab_token_value:
                redactions.append(project_gitlab_token_value)
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
            self._log_for(task_id, f"Merge request title: {mr_title_display}")
            if target_branch:
                if project_default_branch and target_branch != project_default_branch:
                    self._log_for(task_id, f"Base branch override: {target_branch}")
                else:
                    self._log_for(task_id, f"Base branch: {target_branch}")
            else:
                self._log_for(task_id, "Base branch unavailable; falling back to project default")
            self._log_for(task_id, f"Change mode: {change_mode.value}")
            if branch_was_provided:
                self._log_for(task_id, f"Using requested branch: {branch_name}")
            else:
                self._log_for(task_id, f"Proposed branch name: {branch_name}")
            self._log_for(
                task_id,
                f"Codex model: {codex_model} (reasoning effort: {codex_reasoning_effort})",
            )

            if project_root is None:
                self._log_for(task_id, "Unable to determine project root; aborting")
                return

            dry_run_enabled = _is_truthy(os.environ.get("RUNNER_GIT_DRY_RUN"))
            self._log_for(
                task_id,
                f"RUNNER_GIT_DRY_RUN evaluated to {int(dry_run_enabled)} for cache root {project_root}",
            )

            self._log_for(task_id, f"Ensuring project cache {cache_identifier} at {project_root}")
            try:
                self._project_cache_service.bootstrap(
                    gitlab_host=gitlab_host,
                    project_path=gitlab_project_path,
                    default_branch=target_branch or "",
                    gitlab_token=effective_gitlab_token or None,
                    dry_run=dry_run_enabled,
                    log_fn=lambda message: self._log_for(task_id, message),
                )
            except ProjectCacheError as exc:
                self._log_for(task_id, str(exc))
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

            self._log_for(task_id, f"Refreshing project cache at {project_root}")
            try:
                commit_hash = self._project_cache_service.refresh(
                    gitlab_host=gitlab_host,
                    project_path=gitlab_project_path,
                    default_branch=target_branch or "",
                    gitlab_token=effective_gitlab_token or None,
                    dry_run=dry_run_enabled,
                    log_fn=lambda message: self._log_for(task_id, message),
                    identifier_override=cache_identifier,
                )
                self._project_cache_service.enforce_policy(
                    gitlab_host=gitlab_host,
                    project_path=gitlab_project_path,
                    quota_mb=project_cache_quota_mb,
                    prune_after_hours=project_cache_prune_after_hours,
                    dry_run=dry_run_enabled,
                    log_fn=lambda message: self._log_for(task_id, message),
                )
                snapshot_outcome = self._project_cache_service.snapshot(
                    gitlab_host=gitlab_host,
                    project_path=gitlab_project_path,
                    commit_hash=commit_hash or "",
                    branch=target_branch or project_default_branch or "",
                    dry_run=dry_run_enabled,
                    log_fn=lambda message: self._log_for(task_id, message),
                )
                if snapshot_outcome.created_path is not None and not dry_run_enabled:
                    self._log_for(task_id, f"Cache snapshot stored at {snapshot_outcome.created_path}")
            except ProjectCacheError as exc:
                self._log_for(task_id, str(exc))
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

            self._log_for(
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
                self._log_for(task_id, f"Workspace sanitization failed: {exc}")
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
                self._log_for(
                    task_id,
                    f"Sanitized workspace {sanitized_path} missing .git directory",
                )

            self._log_for(task_id, f"Workspace ready at {sanitized_path}")
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
            proxy_log = lambda message: self._log_for(task_id, f"proxy: {message}")
            if not preflight_proxy_stack(docker_disabled=docker_disabled, log_fn=proxy_log):
                self._log_for(task_id, "Proxy preflight failed; aborting task execution")
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

            self._log_for(task_id, "Launching codex runner")
            try:
                effective_allowlist = apply_project_allowlist(
                    task_id,
                    project_gitlab_host,
                    project_allowlist,
                    log_fn=proxy_log,
                )
            except Exception as exc:  # noqa: BLE001 - capture normalization failures
                effective_allowlist = merge_allowlists(project_gitlab_host, project_allowlist)
                message = (
                    f"Allowlist preparation failed ({exc}); using merged base entries without proxy refresh"
                )
                self._log_for(task_id, message)
            joined_allowlist = ", ".join(effective_allowlist) or "<empty>"
            self._log_for(task_id, f"Effective allowlist: {joined_allowlist}")
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
            cache_env = self._prepare_cache_environment(Path(sanitized_path), task_id, state)
            try:
                result = self._codex_service.execute(
                    Path(sanitized_path),
                    prompt=task_prompt,
                    allowlist=effective_allowlist,
                    gitlab_host=gitlab_host,
                    gitlab_project_path=gitlab_project_path,
                    gitlab_token=effective_gitlab_token,
                    chatgpt_session_bundle=session_bundle_raw,
                    target_branch=target_branch,
                    branch_name=branch_name,
                    mr_title=mr_title,
                    change_mode=change_mode.value,
                    task_id=task_id,
                    codex_model=codex_model,
                    codex_reasoning_effort=codex_reasoning_effort,
                    log_fn=lambda message: self._log_for(task_id, f"codex: {message}"),
                    extra_env=cache_env,
                    abort_event=abort_signal,
                )
            except CodexRunnerAborted:
                self._log_for(task_id, "Abort acknowledged by codex runner; stopping task")
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
                self._log_for(task_id, f"Codex execution error: {exc}")
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
            self._log_for(task_id, f"Codex runner mode: {runner_mode}")
            if result.agent_version:
                self._log_for(task_id, f"Codex agent version: {result.agent_version}")
            if result.invocation_flags:
                flags_str = " ".join(result.invocation_flags)
                self._log_for(task_id, f"Codex invocation flags: {flags_str}")
            else:
                flags_str = ""

            if result.exit_code != 0:
                self._log_for(task_id, f"Codex FAIL (exit code {result.exit_code})")
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
                    task.change_mode = change_mode
                    task.commit_sha = result.commit_sha
                    task.commit_url = result.commit_url
                    if change_mode == TaskChangeMode.merge_request:
                        task.mr_url = result.mr_url or None
                    else:
                        task.mr_url = None
                    session.add(task)
                    session.commit()
                self._mark_complete(task_id)
                return

            self._log_for(task_id, "Codex SUCCESS (exit code 0)")
            branch_record = result.branch or branch_name
            if branch_record:
                self._log_for(task_id, f"Branch pushed: {branch_record}")
            if change_mode == TaskChangeMode.merge_request:
                if result.mr_url:
                    self._log_for(task_id, f"Merge request URL: {result.mr_url}")
                else:
                    self._log_for(task_id, "Merge request URL unavailable; check runner output")
            else:
                if result.commit_sha:
                    self._log_for(task_id, f"Commit pushed: {result.commit_sha}")
                else:
                    self._log_for(task_id, "Commit metadata unavailable; check runner output")
                if result.commit_url:
                    self._log_for(task_id, f"Commit URL: {result.commit_url}")
            self._log_for(task_id, "Task completed successfully")

            with Session(self._engine) as session:
                task = session.get(Task, task_id)
                if task is None:
                    return
                task.status = TaskStatus.done
                task.finished_at = datetime.now(timezone.utc)
                task.branch = branch_record or None
                if change_mode == TaskChangeMode.merge_request:
                    task.mr_url = result.mr_url or None
                else:
                    task.mr_url = None
                task.change_mode = change_mode
                task.commit_sha = result.commit_sha
                task.commit_url = result.commit_url
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
            cleanup_log = proxy_log or (
                lambda message: self._log_for(task_id, f"proxy: {message}")
            )
            try:
                clear_task_allowlist(task_id, log_fn=cleanup_log)
            except Exception as exc:  # noqa: BLE001 - do not mask task teardown
                self._log_for(task_id, f"proxy: Failed to clear allowlist: {exc}")
            state.remove_cache_directories()
            self._clear_redactions(task_id)

    def _log_for(self, task_id: int, message: str, *, level: int = logging.INFO) -> None:
        state = self._ensure_state(task_id)
        sanitized_message = self._sanitize_message(state, message)
        timestamp = datetime.now(timezone.utc).isoformat(timespec="seconds")
        level_name = logging.getLevelName(level)
        line = f"[{timestamp}] [{level_name}] {sanitized_message}"
        state.append_log(line)

    def _mark_complete(self, task_id: int, *, terminal_event: str = "done") -> None:
        state = self._ensure_state(task_id)
        state.mark_complete(terminal_event)

    def _log_state(self, task_id: int) -> Tuple[List[str], bool]:
        state = self._ensure_state(task_id)
        return state.snapshot()

    def record_task_log(self, task_id: int, message: str) -> None:
        self._log_for(task_id, message)

    def request_abort(self, task_id: int) -> None:
        state = self._ensure_state(task_id)
        state.abort_event.set()
        state.signal_abort_marker()

    def mark_task_aborted(self, task_id: int) -> None:
        state = self._ensure_state(task_id)
        state.abort_event.set()
        state.signal_abort_marker()
        self._mark_complete(task_id, terminal_event="aborted")

    def handle_task_deleted(self, task_id: int) -> None:
        self._mark_complete(task_id, terminal_event="deleted")
        self._teardown_runtime_state(task_id, remove_logs=True)

    def get_terminal_event(self, task_id: int) -> Optional[str]:
        state = self._get_state(task_id)
        if state is None:
            return None
        return state.get_terminal_reason()

    def _abort_if_requested(
        self,
        task_id: int,
        session: Session,
        message: Optional[str] = None,
    ) -> bool:
        task = session.get(Task, task_id)
        if task is None:
            return False
        state = self._ensure_state(task_id)
        signal = state.abort_event
        if not (task.abort_requested or signal.is_set()):
            return False
        if message:
            self._log_for(task_id, message)
        task.status = TaskStatus.aborted
        task.finished_at = datetime.now(timezone.utc)
        session.add(task)
        session.commit()
        state.signal_abort_marker()
        self._mark_complete(task_id, terminal_event="aborted")
        return True

    # Persistence & Redaction helpers ------------------------------------

    def _sanitize_message(self, state: TaskRuntimeState, message: str) -> str:
        sanitized = SENSITIVE_ENV_PATTERN.sub(r"\1<redacted>", message)
        sanitized = sanitized.replace("GITLAB_TOKEN", "REDACTED_TOKEN")
        for secret in state.get_redactions():
            sanitized = sanitized.replace(secret, "<redacted>")
        return sanitized

    def _register_redactions(self, task_id: int, secrets: List[str]) -> None:
        state = self._ensure_state(task_id)
        state.register_redactions(secrets)

    def _clear_redactions(self, task_id: int) -> None:
        state = self._get_state(task_id)
        if state is not None:
            state.clear_redactions()

    # Credential + notification helpers ----------------------------------

    def _clear_gitlab_token_cache(self) -> None:
        self._credential_cache.clear_gitlab_cache()

    def _clear_chatgpt_session_cache(self) -> None:
        self._credential_cache.clear_chatgpt_cache()

    def _resolve_gitlab_token(self, session: Session) -> str:
        token, changed = self._credential_cache.resolve_gitlab_token(session)
        if changed:
            self._update_runtime_credentials(
                gitlab_available=self._credential_cache.gitlab_available(),
            )
        return token

    def _resolve_chatgpt_session_bundle(self, session: Session) -> ChatGPTSessionMaterial | None:
        material, changed = self._credential_cache.resolve_chatgpt_session(session)
        if changed:
            self._update_runtime_credentials(
                chatgpt_available=self._credential_cache.chatgpt_available(),
            )
        return material

    def notify_gitlab_pat_stored(self, actor: Optional[str], occurred_at: Optional[datetime]) -> None:
        self._clear_gitlab_token_cache()
        with Session(self._engine) as session:
            token, _ = self._credential_cache.resolve_gitlab_token(session)
        availability = bool(token)
        recipients = self._scheduler.get_active_task_ids()
        if not recipients:
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
        self._update_runtime_credentials(
            gitlab_available=availability,
            force=True,
            task_ids=recipients,
        )
        for task_id in recipients:
            self._log_for(task_id, message)

    def notify_gitlab_pat_cleared(self, actor: Optional[str], occurred_at: Optional[datetime]) -> None:
        self._clear_gitlab_token_cache()
        recipients = self._scheduler.get_active_task_ids()
        details: list[str] = []
        if actor:
            details.append(f"by {actor}")
        if occurred_at:
            details.append(f"at {occurred_at.isoformat()}")
        detail_str = " ".join(details)
        if recipients:
            if detail_str:
                message = (
                    f"GitLab PAT cleared {detail_str}; new pushes will fail until a token is reconfigured"
                )
            else:
                message = "GitLab PAT cleared; new pushes will fail until a token is reconfigured"
            self._update_runtime_credentials(
                gitlab_available=False,
                force=True,
                task_ids=recipients,
            )
            for task_id in recipients:
                self._log_for(task_id, message)

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
                self._log_for(task.id, log_message)
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
        with Session(self._engine) as session:
            self._credential_cache.resolve_chatgpt_session(session)
        availability = self._credential_cache.chatgpt_available()
        recipients = self._scheduler.get_active_task_ids()
        if not recipients:
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
        self._update_runtime_credentials(
            chatgpt_available=availability,
            force=True,
            task_ids=recipients,
        )
        for task_id in recipients:
            self._log_for(task_id, message)

    def notify_chatgpt_session_cleared(
        self,
        actor: Optional[str],
        occurred_at: Optional[datetime],
    ) -> None:
        self._clear_chatgpt_session_cache()
        recipients = self._scheduler.get_active_task_ids()
        details: list[str] = []
        if actor:
            details.append(f"by {actor}")
        if occurred_at:
            details.append(f"at {occurred_at.isoformat()}")
        detail_str = " ".join(details)
        if recipients:
            if detail_str:
                message = (
                    f"ChatGPT session bundle cleared {detail_str}; Docker-backed runs will fail until a new bundle is imported"
                )
            else:
                message = (
                    "ChatGPT session bundle cleared; Docker-backed runs will fail until a new bundle is imported"
                )
            message += ". Stub-only runs (RUNNER_DISABLE_DOCKER=1) remain available."
            self._update_runtime_credentials(
                chatgpt_available=False,
                force=True,
                task_ids=recipients,
            )
            for task_id in recipients:
                self._log_for(task_id, message)
