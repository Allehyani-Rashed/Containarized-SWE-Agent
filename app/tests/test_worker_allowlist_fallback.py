from __future__ import annotations

import os
import sys
import tempfile
import unittest
import warnings
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

from sqlalchemy.exc import SAWarning
from sqlmodel import Session, SQLModel

from app.app.secrets import reset_secret_manager


class WorkerAllowlistFallbackTests(unittest.TestCase):
    def setUp(self) -> None:
        self.tmp_dir = tempfile.TemporaryDirectory()
        self.db_path = Path(self.tmp_dir.name) / "worker-allowlist.db"
        os.environ["APP_DATABASE_URL"] = f"sqlite:///{self.db_path}"
        os.environ["RUNNER_DISABLE_DOCKER"] = "1"
        metrics_module = sys.modules.get("app.app.metrics")
        if metrics_module is not None:
            reset = getattr(metrics_module, "reset_metrics_registry", None)
            if callable(reset):
                reset()
        for module in list(sys.modules.keys()):
            if module.startswith("app.app"):
                sys.modules.pop(module)

        warnings.filterwarnings(
            "ignore",
            message="This declarative base already contains a class with the same class name",
            category=SAWarning,
        )
        SQLModel.metadata.clear()

        from app.app.database import engine, init_db

        init_db()
        self.engine = engine

        from app.app.models import Project, Task
        from app.app.worker import TaskQueueManager

        self.Project = Project
        self.Task = Task
        self.TaskQueueManager = TaskQueueManager
        self._workers: list[TaskQueueManager] = []

    def tearDown(self) -> None:
        for worker in self._workers:
            worker.shutdown()
        os.environ.pop("APP_DATABASE_URL", None)
        os.environ.pop("RUNNER_DISABLE_DOCKER", None)
        metrics_module = sys.modules.get("app.app.metrics")
        if metrics_module is not None:
            reset = getattr(metrics_module, "reset_metrics_registry", None)
            if callable(reset):
                reset()
        reset_secret_manager()
        self.tmp_dir.cleanup()

    def _create_worker(self) -> "TaskQueueManager":
        worker = self.TaskQueueManager(self.engine)
        self._workers.append(worker)
        return worker

    def test_fallback_merges_base_allowlist_when_proxy_refresh_fails(self) -> None:
        repo_path = Path(self.tmp_dir.name) / "repo"
        repo_path.mkdir(parents=True, exist_ok=True)
        sanitized_path = Path(self.tmp_dir.name) / "workspace"
        sanitized_path.mkdir(parents=True, exist_ok=True)

        worker = self._create_worker()
        cache_service = MagicMock()
        cache_service.repo_path_for.return_value = repo_path
        cache_service.identifier_for.return_value = "cache-id"
        cache_service.bootstrap.return_value = None
        cache_service.refresh.return_value = "commit123"
        cache_service.enforce_policy.return_value = None
        cache_service.snapshot.return_value = SimpleNamespace(created_path=None)
        worker._project_cache_service = cache_service

        runner_result = SimpleNamespace(
            used_docker=False,
            agent_version="test-agent",
            invocation_flags=[],
            exit_code=0,
            codex_model=None,
            codex_reasoning_effort=None,
            commit_sha=None,
            commit_url=None,
            branch="feature/allowlist-fallback",
            mr_url="https://gitlab.example.com/mr/1",
        )
        worker._codex_service = MagicMock()
        worker._codex_service.execute.return_value = runner_result
        worker._resolve_gitlab_token = MagicMock(return_value="gitlab-token")
        worker._resolve_chatgpt_session_bundle = MagicMock(return_value=None)

        with Session(self.engine) as session:
            project = self.Project(
                name="allowlist-fallback",
                default_branch="main",
                gitlab_host="https://gitlab.example.com",
                gitlab_project_path="example/allowlist",
                allowlist=["extra.example.com"],
            )
            session.add(project)
            session.commit()
            session.refresh(project)

            task = self.Task(project_id=project.id, prompt="trigger fallback")
            session.add(task)
            session.commit()
            session.refresh(task)
            task_id = task.id

        with (
            patch("app.app.worker.apply_project_allowlist", side_effect=RuntimeError("proxy error")),
            patch("app.app.worker.sanitize_workspace", return_value=str(sanitized_path)),
            patch("app.app.worker.preflight_proxy_stack", return_value=True),
            patch("app.app.worker.clear_task_allowlist", return_value=[]),
            patch.object(self.TaskQueueManager, "_prepare_cache_environment", return_value={}),
        ):
            worker._process_task(task_id)

        self.assertTrue(worker._codex_service.execute.called, "Codex runner was not invoked")
        _, kwargs = worker._codex_service.execute.call_args
        allowlist = kwargs.get("allowlist", [])
        self.assertIn("gitlab.example.com", allowlist)
        self.assertIn("gitlab.com", allowlist)
        self.assertIn("extra.example.com", allowlist)
