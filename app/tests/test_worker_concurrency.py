from __future__ import annotations

import json
import os
import sys
import tempfile
import unittest
import warnings
from datetime import datetime, timedelta, timezone
from pathlib import Path
from threading import Event
from time import monotonic, sleep
from unittest.mock import patch

from sqlalchemy.exc import SAWarning
from sqlmodel import Session, SQLModel

from app.app.integrations import set_chatgpt_session_bundle, set_gitlab_pat_token
from app.app.secrets import reset_secret_manager
from app.app.settings_store import set_project_concurrency_limit


class WorkerConcurrencyConfigurationTests(unittest.TestCase):
    def setUp(self) -> None:
        self.tmp_dir = tempfile.TemporaryDirectory()
        self.db_path = Path(self.tmp_dir.name) / "worker-concurrency.db"
        os.environ["APP_DATABASE_URL"] = f"sqlite:///{self.db_path}"
        metrics_module = sys.modules.get("app.app.metrics")
        if metrics_module is not None:
            reset = getattr(metrics_module, "reset_metrics_registry", None)
            if callable(reset):
                reset()
        for env_var in (
            "WORKER_MAX_CONCURRENCY",
            "PROJECT_MAX_CONCURRENCY_DEFAULT",
            "WORKER_ENABLE_PARALLEL",
        ):
            os.environ.pop(env_var, None)

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
        for env_var in (
            "WORKER_MAX_CONCURRENCY",
            "PROJECT_MAX_CONCURRENCY_DEFAULT",
            "WORKER_ENABLE_PARALLEL",
        ):
            os.environ.pop(env_var, None)
        os.environ.pop("GITLAB_PAT", None)
        os.environ.pop("CHATGPT_SESSION_BUNDLE", None)
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

    def _create_task(self, prompt: str = "scheduler test") -> int:
        with Session(self.engine) as session:
            project = self.Project(
                name=f"proj-{prompt}",
                default_branch="main",
                gitlab_host="https://gitlab.example.com",
                gitlab_project_path=f"example/{prompt}",
            )
            session.add(project)
            session.commit()
            session.refresh(project)

            task = self.Task(project_id=project.id, prompt=prompt)
            session.add(task)
            session.commit()
            session.refresh(task)
            return task.id

    def test_invalid_worker_concurrency_env_falls_back_to_default(self) -> None:
        os.environ["WORKER_MAX_CONCURRENCY"] = "not-a-number"
        worker = self._create_worker()
        self.assertEqual(worker._max_concurrency, 10)

    def test_negative_worker_concurrency_env_falls_back_to_default(self) -> None:
        os.environ["WORKER_MAX_CONCURRENCY"] = "-3"
        worker = self._create_worker()
        self.assertEqual(worker._max_concurrency, 10)

    def test_worker_honors_max_concurrency_when_parallel_enabled(self) -> None:
        os.environ["WORKER_MAX_CONCURRENCY"] = "5"
        worker = self._create_worker()
        self.assertEqual(worker._max_concurrency, 5)

    def test_project_default_concurrency_env_applies(self) -> None:
        os.environ["PROJECT_MAX_CONCURRENCY_DEFAULT"] = "3"
        worker = self._create_worker()
        self.assertEqual(worker.get_project_concurrency_limit(), 3)

    def test_disabling_parallel_execution_clamps_concurrency(self) -> None:
        os.environ["WORKER_ENABLE_PARALLEL"] = "0"
        os.environ["WORKER_MAX_CONCURRENCY"] = "3"
        worker = self._create_worker()
        self.assertEqual(worker._max_concurrency, 1)

    def test_project_default_applies_when_project_limit_missing(self) -> None:
        os.environ["PROJECT_MAX_CONCURRENCY_DEFAULT"] = "7"
        with Session(self.engine) as session:
            project = self.Project(
                name="proj-default",
                default_branch="main",
                gitlab_host="https://gitlab.example.com",
                gitlab_project_path="example/proj-default",
            )
            session.add(project)
            session.commit()
            session.refresh(project)
            project_id = project.id

            task = self.Task(project_id=project.id, prompt="uses default limit")
            session.add(task)
            session.commit()
            session.refresh(task)
            task_id = task.id

        worker = self._create_worker()
        limit_info = worker._get_task_project_limit(task_id)
        self.assertEqual(limit_info, (project_id, 7))

    def test_worker_respects_persisted_concurrency_setting(self) -> None:
        with Session(self.engine) as session:
            set_project_concurrency_limit(session, 5)

        worker = self._create_worker()
        self.assertEqual(worker.get_project_concurrency_limit(), 5)

    def test_updating_worker_concurrency_limit_applies_immediately(self) -> None:
        worker = self._create_worker()
        worker.set_project_concurrency_limit(6)
        self.assertEqual(worker.get_project_concurrency_limit(), 6)

    def test_record_active_count_persists_in_db(self) -> None:
        with Session(self.engine) as session:
            project = self.Project(
                name="active-metrics",
                default_branch="main",
                gitlab_host="https://gitlab.example.com",
                gitlab_project_path="example/metrics",
            )
            session.add(project)
            session.commit()
            session.refresh(project)
            project_id = project.id

        worker = self._create_worker()
        worker._record_active_count(project_id, 5)

        with Session(self.engine) as session:
            refreshed = session.get(self.Project, project_id)
            self.assertIsNotNone(refreshed)
            self.assertEqual(refreshed.last_active_count, 5)

    def test_record_active_count_ignores_stale_updates(self) -> None:
        with Session(self.engine) as session:
            project = self.Project(
                name="active-metrics-stale",
                default_branch="main",
                gitlab_host="https://gitlab.example.com",
                gitlab_project_path="example/metrics-stale",
                last_active_count=0,
            )
            session.add(project)
            session.commit()
            session.refresh(project)
            project_id = project.id

        worker = self._create_worker()
        # Simulate teardown clearing all active tasks before a delayed schedule write.
        worker._project_last_reported_counts[project_id] = 0

        # An update with a new value should persist.
        worker._record_active_count(project_id, 1)

        with Session(self.engine) as session:
            refreshed = session.get(self.Project, project_id)
            self.assertIsNotNone(refreshed)
            self.assertEqual(refreshed.last_active_count, 1)

    def test_notify_gitlab_pat_stored_emits_credential_event(self) -> None:
        worker = self._create_worker()
        task_id = self._create_task("pat-notify")
        worker.register_task(task_id)
        state = worker._ensure_state(task_id)
        state.drain_events()

        with patch.object(worker._scheduler, "get_active_task_ids", return_value=[task_id]), patch.object(worker._credential_cache, "resolve_gitlab_token", return_value=("token", True)), patch.object(worker._credential_cache, "gitlab_available", return_value=True):
            worker.notify_gitlab_pat_stored(actor="tester", occurred_at=None)

        events = state.drain_events()
        cred_events = [event for event in events if event["event"] == "credential-event"]
        self.assertTrue(cred_events)
        self.assertTrue(cred_events[-1]["payload"].get("gitlab_pat_available"))

    def test_notify_chatgpt_session_cleared_emits_credential_event(self) -> None:
        worker = self._create_worker()
        task_id = self._create_task("chatgpt-clear")
        worker.register_task(task_id)
        state = worker._ensure_state(task_id)
        state.drain_events()

        with patch.object(worker._scheduler, "get_active_task_ids", return_value=[task_id]):
            worker.notify_chatgpt_session_cleared(actor=None, occurred_at=None)

        events = state.drain_events()
        cred_events = [event for event in events if event["event"] == "credential-event"]
        self.assertTrue(cred_events)
        self.assertFalse(cred_events[-1]["payload"].get("chatgpt_session_available", True))

    def test_notify_chatgpt_session_rotated_emits_credential_event(self) -> None:
        worker = self._create_worker()
        task_id = self._create_task("chatgpt-rotate")
        with Session(self.engine) as session:
            task = session.get(self.Task, task_id)
            self.assertIsNotNone(task)
            project_id = task.project_id
        worker.register_task(task_id)
        state = worker._ensure_state(task_id)
        state.drain_events()

        with patch.object(worker._scheduler, "get_active_task_ids", return_value=[task_id]), patch.object(worker._credential_cache, "resolve_chatgpt_session", return_value=("bundle", True)), patch.object(worker._credential_cache, "chatgpt_available", return_value=True):
            worker.notify_chatgpt_session_rotated(actor="tester", occurred_at=None)

        events = state.drain_events()
        cred_events = [event for event in events if event["event"] == "credential-event"]
        self.assertTrue(cred_events)
        self.assertTrue(cred_events[-1]["payload"].get("chatgpt_session_available"))

        # A subsequent stale update should be ignored.
        worker._record_active_count(project_id, 1)

        with Session(self.engine) as session:
            refreshed = session.get(self.Project, project_id)
            self.assertIsNotNone(refreshed)
            self.assertEqual(refreshed.last_active_count, 1)

    def test_get_task_credentials_snapshot(self) -> None:
        with Session(self.engine) as session:
            project = self.Project(
                name="cred-proj",
                default_branch="main",
                gitlab_host="https://gitlab.example.com",
                gitlab_project_path="example/cred",
            )
            session.add(project)
            session.commit()
            session.refresh(project)

            task = self.Task(project_id=project.id, prompt="inspect credentials")
            session.add(task)
            session.commit()
            session.refresh(task)
            task_id = task.id

        worker = self._create_worker()
        worker.register_task(task_id)
        state = worker._ensure_state(task_id)
        state.update_credentials(gitlab_available=True, chatgpt_available=False, force=True)

        snapshot = worker.get_task_credentials(task_id)
        self.assertTrue(snapshot["gitlab_pat_available"])
        self.assertFalse(snapshot["chatgpt_session_available"])
        self.assertEqual(snapshot["task_id"], task_id)

    def test_get_task_credentials_hydrates_cache_from_persisted_credentials(self) -> None:
        future_expiry = (datetime.now(timezone.utc) + timedelta(days=1)).isoformat()
        session_bundle = json.dumps({
            "session_token": "session-token-value",
            "expires_at": future_expiry,
        })

        with Session(self.engine) as session:
            project = self.Project(
                name="cred-hydrate",
                default_branch="main",
                gitlab_host="https://gitlab.example.com",
                gitlab_project_path="example/cred-hydrate",
            )
            session.add(project)
            session.commit()
            session.refresh(project)

            task = self.Task(project_id=project.id, prompt="check credentials")
            session.add(task)
            session.commit()
            session.refresh(task)
            task_id = task.id

        with Session(self.engine) as session:
            set_gitlab_pat_token(session, "sk-hydrate", "tests")
            set_chatgpt_session_bundle(session, session_bundle, "tests")
            session.commit()

        worker = self._create_worker()

        snapshot = worker.get_task_credentials(task_id)
        self.assertTrue(snapshot["gitlab_pat_available"])
        self.assertTrue(snapshot["chatgpt_session_available"])
        self.assertEqual(snapshot["task_id"], task_id)

    def test_deferred_tasks_do_not_starve_other_projects(self) -> None:
        os.environ["WORKER_ENABLE_PARALLEL"] = "1"
        os.environ["WORKER_MAX_CONCURRENCY"] = "2"

        with Session(self.engine) as session:
            project_a = self.Project(
                name="proj-a",
                default_branch="main",
                gitlab_host="https://gitlab.example.com",
                gitlab_project_path="example/a",
            )
            project_b = self.Project(
                name="proj-b",
                default_branch="main",
                gitlab_host="https://gitlab.example.com",
                gitlab_project_path="example/b",
            )
            session.add(project_a)
            session.add(project_b)
            session.commit()
            session.refresh(project_a)
            session.refresh(project_b)

            task_a1 = self.Task(project_id=project_a.id, prompt="a1")
            task_a2 = self.Task(project_id=project_a.id, prompt="a2")
            task_b = self.Task(project_id=project_b.id, prompt="b1")
            session.add(task_a1)
            session.add(task_a2)
            session.add(task_b)
            session.commit()
            session.refresh(task_a1)
            session.refresh(task_a2)
            session.refresh(task_b)

        self.assertIsNotNone(task_a1.id)
        self.assertIsNotNone(task_a2.id)
        self.assertIsNotNone(task_b.id)

        task_a1_id = int(task_a1.id)
        task_a2_id = int(task_a2.id)
        task_b_id = int(task_b.id)

        worker = self._create_worker()
        worker.set_project_concurrency_limit(1)

        for task_id in (task_a1_id, task_a2_id, task_b_id):
            worker.register_task(task_id)

        execution_order: list[int] = []
        a1_started = Event()
        b_started = Event()
        release_a1 = Event()

        original_process = worker._process_task

        def _fake_process(task_id: int) -> None:
            execution_order.append(task_id)
            if task_id == task_a1_id:
                a1_started.set()
                release_a1.wait(timeout=2)
            elif task_id == task_b_id:
                b_started.set()
            sleep(0.01)

        try:
            worker._process_task = _fake_process  # type: ignore[assignment]
            worker.enqueue(task_a1_id)
            worker.enqueue(task_a2_id)
            worker.enqueue(task_b_id)

            self.assertTrue(a1_started.wait(timeout=1.5), "Primary project task never started")
            self.assertTrue(
                b_started.wait(timeout=1.5),
                "Task from a different project never began while deferred tasks existed",
            )
            release_a1.set()

            deadline = monotonic() + 3
            while len(execution_order) < 3 and monotonic() < deadline:
                sleep(0.05)

            self.assertGreaterEqual(len(execution_order), 2)
            self.assertEqual(execution_order[0], task_a1_id)
            self.assertEqual(execution_order[1], task_b_id)

            self.assertEqual(len(execution_order), 3, "Deferred task never resumed after capacity freed")
            self.assertEqual(execution_order[2], task_a2_id)
        finally:
            release_a1.set()
            worker._process_task = original_process  # type: ignore[assignment]
            os.environ.pop("WORKER_ENABLE_PARALLEL", None)
            os.environ.pop("WORKER_MAX_CONCURRENCY", None)


if __name__ == "__main__":
    unittest.main()
