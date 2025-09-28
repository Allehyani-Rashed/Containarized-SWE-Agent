import os
import sys
import tempfile
import unittest
from datetime import datetime, timedelta, timezone
from pathlib import Path
from unittest.mock import patch

from fastapi.testclient import TestClient
from sqlmodel import Session, SQLModel, select


class TaskListFilterTests(unittest.TestCase):
    def setUp(self) -> None:
        self.tmp_dir = tempfile.TemporaryDirectory()
        os.environ["APP_DATABASE_URL"] = f"sqlite:///{Path(self.tmp_dir.name) / 'filters.db'}"
        os.environ["RUNNER_DISABLE_DOCKER"] = "1"
        os.environ["RUNNER_GIT_DRY_RUN"] = "1"
        for module_name in list(sys.modules.keys()):
            if module_name.startswith("app.app"):
                sys.modules.pop(module_name)
        SQLModel.metadata.clear()
        from app.app import main as main_module

        self.main = main_module

    def tearDown(self) -> None:
        self.tmp_dir.cleanup()
        os.environ.pop("APP_DATABASE_URL", None)
        os.environ.pop("RUNNER_DISABLE_DOCKER", None)
        os.environ.pop("RUNNER_GIT_DRY_RUN", None)

    def _create_project(self, client: TestClient) -> int:
        project_root = Path(self.tmp_dir.name) / "filters-project"
        project_root.mkdir(parents=True, exist_ok=True)
        (project_root / "README.md").write_text("filters demo\n", encoding="utf-8")
        payload = {
            "name": "filters-demo",
            "local_path": str(project_root),
            "default_branch": "main",
            "gitlab_host": "https://gitlab.example.com",
            "gitlab_project_path": "example/filters-demo",
        }
        response = client.post("/projects", json=payload)
        self.assertEqual(response.status_code, 201, response.text)
        return response.json()["id"]

    def _seed_tasks(self, client: TestClient, project_id: int) -> None:
        rotate_resp = client.post("/integrations/pat", json={"token": "filters-pat"})
        self.assertEqual(rotate_resp.status_code, 200, rotate_resp.text)

        with patch("app.app.worker.TaskQueueManager.enqueue", lambda self, task_id: None):
            first = client.post(
                "/tasks",
                json={
                    "project_id": project_id,
                    "prompt": "Finished task",
                    "branch_name": "feature/login",
                    "codex_model": "gpt-4o-mini",
                },
            )
            self.assertEqual(first.status_code, 201, first.text)
            second = client.post(
                "/tasks",
                json={
                    "project_id": project_id,
                    "prompt": "Failed task",
                    "branch_name": "hotfix/PATCH-99",
                },
            )
            self.assertEqual(second.status_code, 201, second.text)
            third = client.post(
                "/tasks",
                json={
                    "project_id": project_id,
                    "prompt": "Pending task",
                },
            )
            self.assertEqual(third.status_code, 201, third.text)

        from app.app.models import Task, TaskStatus

        ids = [first.json()["id"], second.json()["id"], third.json()["id"]]
        now = datetime.now(timezone.utc)
        with Session(self.main.engine) as session:
            rows = session.exec(select(Task).where(Task.id.in_(ids))).all()
            by_id = {row.id: row for row in rows if row.id is not None}
            task_done = by_id[ids[0]]
            task_done.status = TaskStatus.done
            task_done.created_at = now - timedelta(minutes=3)
            task_done.started_at = now - timedelta(minutes=2)
            task_done.finished_at = now - timedelta(minutes=1)

            task_failed = by_id[ids[1]]
            task_failed.status = TaskStatus.failed
            task_failed.created_at = now - timedelta(minutes=2)
            task_failed.started_at = now - timedelta(minutes=1, seconds=30)
            task_failed.finished_at = now - timedelta(minutes=1)

            task_pending = by_id[ids[2]]
            task_pending.status = TaskStatus.pending
            task_pending.created_at = now - timedelta(minutes=1)

            session.add(task_done)
            session.add(task_failed)
            session.add(task_pending)
            session.commit()

    def test_task_list_structure_and_pagination(self) -> None:
        with TestClient(self.main.app) as client:
            project_id = self._create_project(client)
            self._seed_tasks(client, project_id)

            response = client.get("/tasks", params={"limit": 2})
            self.assertEqual(response.status_code, 200, response.text)
            payload = response.json()
            self.assertIn("items", payload)
            self.assertEqual(payload["limit"], 2)
            self.assertEqual(payload["offset"], 0)
            self.assertEqual(payload["total"], 3)
            self.assertEqual(len(payload["items"]), 2)
            self.assertEqual(payload["next_offset"], 2)

            second_page = client.get("/tasks", params={"limit": 2, "offset": payload["next_offset"]})
            self.assertEqual(second_page.status_code, 200, second_page.text)
            second_payload = second_page.json()
            self.assertEqual(second_payload["offset"], 2)
            self.assertEqual(len(second_payload["items"]), 1)
            self.assertIsNone(second_payload["next_offset"])

    def test_status_and_model_filters(self) -> None:
        with TestClient(self.main.app) as client:
            project_id = self._create_project(client)
            self._seed_tasks(client, project_id)

            status_resp = client.get("/tasks", params={"statuses": "done,failed"})
            self.assertEqual(status_resp.status_code, 200)
            status_payload = status_resp.json()
            self.assertEqual(status_payload["total"], 2)
            statuses = {item["status"] for item in status_payload["items"]}
            self.assertSetEqual(statuses, {"done", "failed"})

            model_resp = client.get("/tasks", params={"codex_model": "gpt-4o-mini"})
            self.assertEqual(model_resp.status_code, 200)
            model_payload = model_resp.json()
            self.assertEqual(model_payload["total"], 1)
            self.assertEqual(model_payload["items"][0]["codex_model"], "gpt-4o-mini")

    def test_branch_filter_is_case_insensitive(self) -> None:
        with TestClient(self.main.app) as client:
            project_id = self._create_project(client)
            self._seed_tasks(client, project_id)

            branch_resp = client.get("/tasks", params={"branch": "PATCH"})
            self.assertEqual(branch_resp.status_code, 200)
            branch_payload = branch_resp.json()
            self.assertEqual(branch_payload["total"], 1)
            item = branch_payload["items"][0]
            self.assertEqual(item["branch"], "hotfix/PATCH-99")

    def test_invalid_status_filter_rejected(self) -> None:
        with TestClient(self.main.app) as client:
            project_id = self._create_project(client)
            self._seed_tasks(client, project_id)

            response = client.get("/tasks", params={"statuses": "done,unknown"})
            self.assertEqual(response.status_code, 400)
            detail = response.json().get("detail")
            self.assertIn("Invalid task status", detail)


if __name__ == "__main__":
    unittest.main()
