import os
import sys
import tempfile
import unittest
import warnings
from datetime import datetime, timedelta, timezone
from pathlib import Path

from sqlalchemy.exc import SAWarning
from sqlmodel import Session, SQLModel


class WorkerRecoveryTests(unittest.TestCase):
    def setUp(self) -> None:
        self.tmp_dir = tempfile.TemporaryDirectory()
        self.db_path = Path(self.tmp_dir.name) / "worker-recovery.db"
        os.environ["APP_DATABASE_URL"] = f"sqlite:///{self.db_path}"

        # Ensure a clean module import state for app components.
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

        from app.app.models import Project, Task, TaskStatus
        from app.app.worker import TaskQueueManager

        self.Project = Project
        self.Task = Task
        self.TaskStatus = TaskStatus
        self.TaskQueueManager = TaskQueueManager

    def tearDown(self) -> None:
        os.environ.pop("APP_DATABASE_URL", None)
        self.tmp_dir.cleanup()

    def test_restart_marks_existing_pending_tasks_failed(self) -> None:
        with Session(self.engine) as session:
            project = self.Project(
                name="demo",
                default_branch="main",
                gitlab_host="https://gitlab.example.com",
                gitlab_project_path="example/demo",
            )
            session.add(project)
            session.commit()
            session.refresh(project)

            task = self.Task(
                project_id=project.id,
                prompt="stale pending task",
                status=self.TaskStatus.pending,
            )
            # Ensure the record predates worker boot time.
            task.created_at = datetime.now(timezone.utc) - timedelta(minutes=5)
            session.add(task)
            session.commit()
            session.refresh(task)
            task_id = task.id

        worker = self.TaskQueueManager(self.engine)
        try:
            with Session(self.engine) as session:
                record = session.get(self.Task, task_id)
                self.assertIsNotNone(record)
                assert record is not None
                self.assertEqual(record.status, self.TaskStatus.failed)
                self.assertIsNotNone(record.finished_at)

            logs = worker.get_logs_snapshot(task_id)
            self.assertTrue(any("restart" in entry.lower() for entry in logs))
        finally:
            worker.shutdown()

    def test_restart_does_not_touch_newer_pending_tasks(self) -> None:
        with Session(self.engine) as session:
            project = self.Project(
                name="demo-two",
                default_branch="main",
                gitlab_host="https://gitlab.example.com",
                gitlab_project_path="example/demo-two",
            )
            session.add(project)
            session.commit()
            session.refresh(project)

            older_task = self.Task(
                project_id=project.id,
                prompt="older pending",
                status=self.TaskStatus.pending,
            )
            older_task.created_at = datetime.now(timezone.utc) - timedelta(minutes=10)
            session.add(older_task)

            newer_task = self.Task(
                project_id=project.id,
                prompt="newer pending",
                status=self.TaskStatus.pending,
            )
            newer_task.created_at = datetime.now(timezone.utc) + timedelta(minutes=10)
            session.add(newer_task)

            session.commit()
            session.refresh(older_task)
            session.refresh(newer_task)
            older_id = older_task.id
            newer_id = newer_task.id

        worker = self.TaskQueueManager(self.engine)
        try:
            with Session(self.engine) as session:
                older = session.get(self.Task, older_id)
                newer = session.get(self.Task, newer_id)
                self.assertIsNotNone(older)
                self.assertIsNotNone(newer)
                assert older is not None and newer is not None
                self.assertEqual(older.status, self.TaskStatus.failed)
                self.assertEqual(newer.status, self.TaskStatus.pending)

            logs_older = worker.get_logs_snapshot(older_id)
            self.assertTrue(any("restart" in entry.lower() for entry in logs_older))

            logs_newer = worker.get_logs_snapshot(newer_id)
            self.assertEqual(logs_newer, [])
        finally:
            worker.shutdown()


if __name__ == "__main__":
    unittest.main()
