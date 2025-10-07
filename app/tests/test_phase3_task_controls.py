import os
import subprocess
import sys
import tempfile
import time
import unittest
from pathlib import Path
from unittest.mock import patch

from fastapi.testclient import TestClient

from app.app.project_cache import project_cache_repo_path


def _initialize_repo(path: Path) -> None:
    subprocess.run(["git", "init", "-b", "main"], cwd=path, check=True, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    subprocess.run(["git", "config", "user.email", "phase3@example.com"], cwd=path, check=True, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    subprocess.run(["git", "config", "user.name", "Phase3 Tester"], cwd=path, check=True, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    subprocess.run(["git", "add", "."], cwd=path, check=True, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    subprocess.run(["git", "commit", "-m", "Initial commit"], cwd=path, check=True, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)


class Phase3TaskLifecycleTests(unittest.TestCase):
    def setUp(self) -> None:
        self.tmp_dir = tempfile.TemporaryDirectory()
        self.db_path = Path(self.tmp_dir.name) / "phase3.db"
        os.environ["APP_DATABASE_URL"] = f"sqlite:///{self.db_path}"
        os.environ["RUNNER_DISABLE_DOCKER"] = "1"
        os.environ["RUNNER_GIT_DRY_RUN"] = "1"
        os.environ["PROJECT_CACHE_ROOT"] = str(Path(self.tmp_dir.name) / "cache")
        for module in list(sys.modules.keys()):
            if module.startswith("app.app"):
                sys.modules.pop(module)
        from sqlmodel import SQLModel

        SQLModel.metadata.clear()
        from app.app import main as main_module

        self.main = main_module

    def tearDown(self) -> None:
        os.environ.pop("APP_DATABASE_URL", None)
        os.environ.pop("RUNNER_DISABLE_DOCKER", None)
        os.environ.pop("RUNNER_GIT_DRY_RUN", None)
        os.environ.pop("PROJECT_CACHE_ROOT", None)
        self.tmp_dir.cleanup()

    def _create_project(self, client: TestClient) -> tuple[int, Path]:
        project_root = project_cache_repo_path("https://gitlab.example.com", "example/phase3")
        project_root.mkdir(parents=True, exist_ok=True)
        (project_root / "README.md").write_text("phase3 demo\n", encoding="utf-8")
        (project_root / "app.py").write_text("print('hello phase3')\n", encoding="utf-8")
        _initialize_repo(project_root)

        response = client.post("/integrations/pat", json={"token": "sk-phase3"})
        self.assertEqual(response.status_code, 200)
        project_payload = {
            "name": "phase3-project",
            "default_branch": "main",
            "gitlab_host": "https://gitlab.example.com",
            "gitlab_project_path": "example/phase3",
        }
        project_response = client.post("/projects", json=project_payload)
        self.assertEqual(project_response.status_code, 201)
        project_body = project_response.json()
        self.assertEqual(project_body["cache_path"], str(project_root))
        self.assertEqual(project_body["cache_status"], "ready")
        project_id = project_body["id"]
        return project_id, project_root

    def test_abort_pending_task_marks_aborted(self) -> None:
        with TestClient(self.main.app) as client:
            project_id, _ = self._create_project(client)
            with patch("app.app.worker.TaskQueueManager.enqueue", lambda self, task_id: None):
                create_response = client.post(
                    "/tasks",
                    json={
                        "project_id": project_id,
                        "prompt": "pending abort",
                    },
                )
            self.assertEqual(create_response.status_code, 201)
            task_id = create_response.json()["id"]

            abort_response = client.post(f"/tasks/{task_id}/abort", json={})
            self.assertEqual(abort_response.status_code, 200)
            payload = abort_response.json()
            self.assertEqual(payload["status"], "aborted")
            self.assertTrue(payload["abort_requested"])

            detail_response = client.get(f"/tasks/{task_id}")
            self.assertEqual(detail_response.status_code, 200)
            detail = detail_response.json()
            self.assertEqual(detail["status"], "aborted")
            self.assertIsNotNone(detail["finished_at"])

            logs_response = client.get(f"/tasks/{task_id}/logs?follow=0")
            self.assertEqual(logs_response.status_code, 200)
            snapshot_payload = logs_response.json()
            entries = snapshot_payload.get("entries", [])
            self.assertEqual(snapshot_payload.get("status"), "aborted")
            self.assertTrue(snapshot_payload.get("abort_requested"))
            joined = "\n".join(entries)
            self.assertIn("Abort requested by operator", joined)

        from sqlmodel import Session, select
        from app.app.models import AuditLog

        with Session(self.main.engine) as session:
            record = session.exec(
                select(AuditLog).where(AuditLog.action == "task.abort.pending")
            ).first()
            self.assertIsNotNone(record)
            self.assertIn(str(task_id), record.details or "")

    def test_abort_running_task_stops_execution(self) -> None:
        with TestClient(self.main.app) as client:
            project_id, _ = self._create_project(client)

            from app.app.codex_runner import CodexResult, CodexRunnerAborted

            def fake_run_codex(self, *args, **kwargs):  # type: ignore[no-untyped-def]
                abort_event = kwargs.get("abort_event")
                start = time.time()
                while time.time() - start < 2:
                    if abort_event is not None and abort_event.is_set():
                        raise CodexRunnerAborted("aborted by test")
                    time.sleep(0.05)
                return CodexResult(
                    exit_code=0,
                    used_docker=False,
                    branch=kwargs.get("branch_name"),
                    mr_url=None,
                    agent_version="test-agent",
                    invocation_flags=[],
                    codex_model=kwargs.get("codex_model"),
                    codex_reasoning_effort=kwargs.get("codex_reasoning_effort"),
                )

            with patch("app.app.worker.CodexExecutionService.execute", fake_run_codex):
                create_response = client.post(
                    "/tasks",
                    json={
                        "project_id": project_id,
                        "prompt": "running abort",
                    },
                )
            self.assertEqual(create_response.status_code, 201)
            task_id = create_response.json()["id"]

            deadline = time.time() + 5
            while time.time() < deadline:
                status_response = client.get(f"/tasks/{task_id}")
                self.assertEqual(status_response.status_code, 200)
                status = status_response.json()["status"]
                if status == "running":
                    break
                time.sleep(0.05)
            else:
                self.fail("Task never entered running state")

            abort_response = client.post(f"/tasks/{task_id}/abort", json={})
            self.assertEqual(abort_response.status_code, 200)

            deadline = time.time() + 5
            final_detail = None
            while time.time() < deadline:
                detail_response = client.get(f"/tasks/{task_id}")
                self.assertEqual(detail_response.status_code, 200)
                final_detail = detail_response.json()
                if final_detail["status"] == "aborted":
                    break
                time.sleep(0.05)
            else:
                self.fail("Task did not transition to aborted")

            assert final_detail is not None
            logs_response = client.get(f"/tasks/{task_id}/logs?follow=0")
            self.assertEqual(logs_response.status_code, 200)
            snapshot_payload = logs_response.json()
            entries = snapshot_payload.get("entries", [])
            self.assertEqual(snapshot_payload.get("status"), "aborted")
            self.assertTrue(snapshot_payload.get("abort_requested", False))
            joined = "\n".join(entries)
            self.assertIn("Abort requested by operator", joined)
            self.assertIn("Abort requested after workspace preparation", joined)

        from sqlmodel import Session, select
        from app.app.models import AuditLog

        with Session(self.main.engine) as session:
            record = session.exec(
                select(AuditLog).where(AuditLog.action == "task.abort.requested")
            ).first()
            self.assertIsNotNone(record)
            self.assertIn(str(task_id), record.details or "")

    def test_delete_task_removes_artifacts(self) -> None:
        with TestClient(self.main.app) as client:
            project_id, _ = self._create_project(client)

            from app.app.codex_runner import CodexResult

            def fast_run_codex(self, *args, **kwargs):  # type: ignore[no-untyped-def]
                return CodexResult(
                    exit_code=0,
                    used_docker=False,
                    branch=kwargs.get("branch_name"),
                    mr_url="https://gitlab.example.com/demo",
                    agent_version="test-agent",
                    invocation_flags=["--yolo"],
                    codex_model=kwargs.get("codex_model"),
                    codex_reasoning_effort=kwargs.get("codex_reasoning_effort"),
                )

            with patch("app.app.worker.CodexExecutionService.execute", fast_run_codex):
                create_response = client.post(
                    "/tasks",
                    json={
                        "project_id": project_id,
                        "prompt": "delete me",
                    },
                )
            self.assertEqual(create_response.status_code, 201)
            task_id = create_response.json()["id"]

            deadline = time.time() + 5
            detail_payload = None
            while time.time() < deadline:
                detail_response = client.get(f"/tasks/{task_id}")
                self.assertEqual(detail_response.status_code, 200)
                detail_payload = detail_response.json()
                if detail_payload["status"] == "done":
                    break
                time.sleep(0.05)
            else:
                self.fail("Task did not complete")

            assert detail_payload is not None
            workspace_path = detail_payload["workspace_path"]
            self.assertIsNotNone(workspace_path)
            if workspace_path:
                self.assertTrue(Path(workspace_path).exists())

            log_path = Path(self.main.WORKSPACES_ROOT) / "logs" / f"{task_id}.log"
            self.assertTrue(log_path.exists())

            delete_response = client.delete(f"/tasks/{task_id}")
            self.assertEqual(delete_response.status_code, 204)

            detail_response = client.get(f"/tasks/{task_id}")
            self.assertEqual(detail_response.status_code, 404)

            self.assertFalse(log_path.exists())
            if workspace_path:
                self.assertFalse(Path(workspace_path).exists())

        from sqlmodel import Session, select
        from app.app.models import AuditLog

        with Session(self.main.engine) as session:
            record = session.exec(
                select(AuditLog).where(AuditLog.action == "task.deleted")
            ).first()
            self.assertIsNotNone(record)
            self.assertIn(str(task_id), record.details or "")


if __name__ == "__main__":
    unittest.main()
