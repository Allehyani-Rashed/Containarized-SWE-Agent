import os
import sys
import tempfile
import unittest
from datetime import datetime, timezone
from pathlib import Path
from unittest.mock import patch

from fastapi.testclient import TestClient

from app.app.project_cache import project_cache_repo_path


class ProjectCrudTests(unittest.TestCase):
    def setUp(self) -> None:
        self.tmp_dir = tempfile.TemporaryDirectory()
        db_path = Path(self.tmp_dir.name) / "projects.db"
        os.environ["APP_DATABASE_URL"] = f"sqlite:///{db_path}"
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

    def _register_pat(self, client: TestClient) -> None:
        response = client.post(
            "/integrations/pat",
            json={"token": "sk-test-token", "updated_by": "tester"},
        )
        self.assertEqual(response.status_code, 200, response.text)

    def _create_project(self, client: TestClient) -> int:
        project_root = project_cache_repo_path("https://gitlab.test", "group/demo")
        project_root.mkdir(parents=True, exist_ok=True)
        (project_root / "README.md").write_text("demo\n", encoding="utf-8")
        payload = {
            "name": "demo",
            "default_branch": "main",
            "gitlab_host": "https://gitlab.test",
            "gitlab_project_path": "group/demo",
        }
        response = client.post("/projects", json=payload)
        self.assertEqual(response.status_code, 201, response.text)
        project_data = response.json()
        self.assertEqual(project_data["cache_path"], str(project_root))
        self.assertIn(project_data["cache_status"], {"present", "ready"})
        return project_data["id"]

    def test_project_detail_includes_recent_tasks_and_metrics(self) -> None:
        with TestClient(self.main.app) as client:
            self._register_pat(client)
            project_id = self._create_project(client)

            with patch("app.app.worker.TaskQueueManager.enqueue", lambda self, task_id: None):
                first_task = client.post(
                    "/tasks",
                    json={
                        "project_id": project_id,
                        "prompt": "seed task",
                        "allowlist": [],
                    },
                )
                self.assertEqual(first_task.status_code, 201, first_task.text)

                second_task = client.post(
                    "/tasks",
                    json={
                        "project_id": project_id,
                        "prompt": "custom allowlist",
                        "allowlist": ["src/"],
                        "codex_model": "gpt-5-codex",
                        "codex_reasoning_effort": "low",
                    },
                )
                self.assertEqual(second_task.status_code, 201, second_task.text)

            from sqlmodel import Session
            from app.app.models import Task, TaskStatus

            with Session(self.main.engine) as session:
                task1 = session.get(Task, first_task.json()["id"])
                task2 = session.get(Task, second_task.json()["id"])
                self.assertIsNotNone(task1)
                self.assertIsNotNone(task2)
                assert task1 is not None and task2 is not None

                now = datetime.now(timezone.utc)
                task1.status = TaskStatus.done
                task1.finished_at = now
                task2.status = TaskStatus.failed
                task2.started_at = now
                task2.finished_at = now
                session.add(task1)
                session.add(task2)
                session.commit()

            detail = client.get(f"/projects/{project_id}")
            self.assertEqual(detail.status_code, 200, detail.text)
            payload = detail.json()
            self.assertEqual(payload["id"], project_id)
            self.assertEqual(payload["repository_url"], "https://gitlab.test/group/demo")
            self.assertEqual(payload["total_task_count"], 2)
            self.assertEqual(payload["active_task_count"], 0)
            self.assertEqual(payload["last_task_status"], "failed")
            self.assertEqual(payload["allowlist_status"], "custom")
            self.assertIsNotNone(payload["last_task_at"])
            self.assertEqual(len(payload["recent_tasks"]), 2)
            latest_task = payload["recent_tasks"][0]
            self.assertEqual(latest_task["codex_model"], "gpt-5-codex")
            self.assertEqual(latest_task["codex_reasoning_effort"], "low")
            self.assertEqual(latest_task["allowlist_size"], 1)

    def test_update_project_supports_field_changes_and_token_management(self) -> None:
        with TestClient(self.main.app) as client:
            project_id = self._create_project(client)

            update_response = client.patch(
                f"/projects/{project_id}",
                json={
                    "name": "demo-updated",
                    "default_branch": "release",
                    "gitlab_host": "https://gitlab.example",
                    "gitlab_project_path": "example/demo",
                    "codex_token": "sk-updated",
                    "actor": "tester",
                },
            )
            self.assertEqual(update_response.status_code, 200, update_response.text)
            payload = update_response.json()
            self.assertEqual(payload["name"], "demo-updated")
            self.assertEqual(payload["default_branch"], "release")
            self.assertTrue(payload["codex_token_configured"])
            self.assertIsNotNone(payload["codex_token_updated_at"])

            clear_response = client.patch(
                f"/projects/{project_id}",
                json={"clear_codex_token": True, "actor": "tester"},
            )
            self.assertEqual(clear_response.status_code, 200, clear_response.text)
            cleared = clear_response.json()
            self.assertFalse(cleared["codex_token_configured"])

            invalid_response = client.patch(
                f"/projects/{project_id}",
                json={"default_branch": "  "},
            )
            self.assertEqual(invalid_response.status_code, 400)

    def test_delete_project_blocks_active_tasks_then_cleans_records(self) -> None:
        with TestClient(self.main.app) as client:
            self._register_pat(client)
            project_id = self._create_project(client)

            with patch("app.app.worker.TaskQueueManager.enqueue", lambda self, task_id: None):
                task_response = client.post(
                    "/tasks",
                    json={"project_id": project_id, "prompt": "pending", "allowlist": []},
                )
            self.assertEqual(task_response.status_code, 201, task_response.text)
            task_id = task_response.json()["id"]

            blocked = client.delete(f"/projects/{project_id}")
            self.assertEqual(blocked.status_code, 409)

            from sqlmodel import Session
            from app.app.models import Task, TaskStatus

            with Session(self.main.engine) as session:
                task = session.get(Task, task_id)
                assert task is not None
                task.status = TaskStatus.done
                task.finished_at = datetime.now(timezone.utc)
                session.add(task)
                session.commit()

            deleted = client.request("DELETE", f"/projects/{project_id}", json={"actor": "tester"})
            self.assertEqual(deleted.status_code, 204, deleted.text)

            missing = client.get(f"/projects/{project_id}")
            self.assertEqual(missing.status_code, 404)


if __name__ == "__main__":
    unittest.main()
