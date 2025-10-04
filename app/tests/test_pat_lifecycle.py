import os
import sys
import tempfile
import unittest
from datetime import datetime, timezone
from pathlib import Path
from unittest.mock import patch

from fastapi.testclient import TestClient

from app.app.project_cache import project_cache_repo_path


class PatLifecycleTests(unittest.TestCase):
    def setUp(self) -> None:
        self.tmp_dir = tempfile.TemporaryDirectory()
        os.environ["APP_DATABASE_URL"] = f"sqlite:///{Path(self.tmp_dir.name) / 'pat.db'}"
        os.environ["RUNNER_DISABLE_DOCKER"] = "1"
        os.environ["PROJECT_CACHE_ROOT"] = str(Path(self.tmp_dir.name) / "cache")
        self.previous_pat = os.environ.get("GITLAB_PAT")
        os.environ.pop("GITLAB_PAT", None)
        for module in list(sys.modules.keys()):
            if module.startswith("app.app"):
                sys.modules.pop(module)
        from sqlmodel import SQLModel

        SQLModel.metadata.clear()
        from app.app import main as main_module

        self.main = main_module

    def tearDown(self) -> None:
        self.tmp_dir.cleanup()
        os.environ.pop("APP_DATABASE_URL", None)
        os.environ.pop("RUNNER_DISABLE_DOCKER", None)
        os.environ.pop("PROJECT_CACHE_ROOT", None)
        if self.previous_pat is None:
            os.environ.pop("GITLAB_PAT", None)
        else:
            os.environ["GITLAB_PAT"] = self.previous_pat

    def _register_project(self, client: TestClient) -> int:
        project_root = project_cache_repo_path("https://gitlab.example.com", "example/demo")
        project_root.mkdir(parents=True, exist_ok=True)
        (project_root / "README.md").write_text("demo\n", encoding="utf-8")
        (project_root / ".git").mkdir(parents=True, exist_ok=True)
        payload = {
            "name": "demo",
            "default_branch": "main",
            "gitlab_host": "https://gitlab.example.com",
            "gitlab_project_path": "example/demo",
        }
        response = client.post("/projects", json=payload)
        self.assertEqual(response.status_code, 201)
        project_body = response.json()
        self.assertEqual(project_body["cache_path"], str(project_root))
        self.assertEqual(project_body["cache_status"], "ready")
        return project_body["id"]

    def test_task_creation_blocked_without_pat(self) -> None:
        with TestClient(self.main.app) as client:
            project_id = self._register_project(client)
            task_resp = client.post(
                "/tasks",
                json={"project_id": project_id, "prompt": "should fail"},
            )
            self.assertEqual(task_resp.status_code, 400)
            self.assertIn("GitLab PAT", task_resp.json().get("detail", ""))

    def test_pat_rotation_updates_metadata(self) -> None:
        with TestClient(self.main.app) as client:
            rotate_resp = client.post(
                "/integrations/pat",
                json={"token": "gitlab-token", "updated_by": "tester"},
            )
            self.assertEqual(rotate_resp.status_code, 200)
            status_resp = client.get("/integrations/pat")
            self.assertEqual(status_resp.status_code, 200)
            status_payload = status_resp.json()
            self.assertTrue(status_payload["configured"])
            self.assertEqual(status_payload["updated_by"], "tester")
            self.assertIsNotNone(status_payload["updated_at"])

        from sqlmodel import Session, select
        from app.app.database import engine
        from app.app.integrations import GITLAB_PAT_KIND
        from app.app.models import AuditLog, IntegrationCredential

        with Session(engine) as session:
            credential = session.exec(
                select(IntegrationCredential).where(IntegrationCredential.kind == GITLAB_PAT_KIND)
            ).one()
            self.assertEqual(credential.token_encrypted, "gitlab-token")
            self.assertEqual(credential.updated_by, "tester")

            audit_entries = session.exec(
                select(AuditLog).where(AuditLog.action == "gitlab_pat.stored")
            ).all()
            self.assertTrue(audit_entries)

    def test_pat_clear_marks_pending_tasks_failed(self) -> None:
        with TestClient(self.main.app) as client:
            rotate_resp = client.post("/integrations/pat", json={"token": "gitlab-token"})
            self.assertEqual(rotate_resp.status_code, 200)
            project_id = self._register_project(client)

            from sqlmodel import Session
            from app.app.database import engine
            from app.app.models import Task, TaskStatus

            with Session(engine) as session:
                pending_task = Task(
                    project_id=project_id,
                    prompt="pending task",
                    status=TaskStatus.pending,
                    created_at=datetime.now(timezone.utc),
                )
                session.add(pending_task)
                session.commit()
                session.refresh(pending_task)
                task_id = pending_task.id

            worker = self.main.get_worker()
            worker.register_task(task_id)

            clear_resp = client.request(
                "DELETE",
                "/integrations/pat",
                json={"updated_by": "tester"},
            )
            self.assertEqual(clear_resp.status_code, 200)
            status_payload = clear_resp.json()
            self.assertFalse(status_payload["configured"])

            with Session(engine) as session:
                task = session.get(Task, task_id)
                assert task is not None
                self.assertEqual(task.status, TaskStatus.failed)
                self.assertIsNotNone(task.finished_at)

            logs_resp = client.get(f"/tasks/{task_id}/logs?follow=0")
            self.assertEqual(logs_resp.status_code, 200)
            snapshot_payload = logs_resp.json()
            entries = snapshot_payload.get("entries", [])
            self.assertEqual(snapshot_payload.get("status"), "failed")
            self.assertFalse(snapshot_payload.get("abort_requested", False))
            self.assertTrue(entries)
            self.assertTrue(any("Pending task failed" in entry for entry in entries))

    @patch("app.app.integrations._probe_gitlab_pat", return_value=(True, None))
    def test_pat_verify_success_updates_metadata(self, probe_mock) -> None:
        with TestClient(self.main.app) as client:
            rotate_resp = client.post(
                "/integrations/pat",
                json={"token": "gitlab-token", "updated_by": "tester"},
            )
            self.assertEqual(rotate_resp.status_code, 200)

            verify_resp = client.post(
                "/integrations/pat/verify",
                json={"gitlab_host": "https://gitlab.example.com", "actor": "auditor"},
            )
            self.assertEqual(verify_resp.status_code, 200)
            payload = verify_resp.json()
            self.assertEqual(payload["verification_status"], "verified")
            self.assertEqual(payload["verification_host"], "https://gitlab.example.com")
            self.assertIsNone(payload["verification_error"])
            self.assertIsNotNone(payload["verification_checked_at"])

        from sqlmodel import Session, select
        from app.app.database import engine
        from app.app.integrations import GITLAB_PAT_KIND, VERIFICATION_STATUS_VERIFIED
        from app.app.models import IntegrationCredential

        with Session(engine) as session:
            credential = session.exec(
                select(IntegrationCredential).where(IntegrationCredential.kind == GITLAB_PAT_KIND)
            ).one()
            self.assertEqual(credential.verification_status, VERIFICATION_STATUS_VERIFIED)
            self.assertEqual(credential.verification_host, "https://gitlab.example.com")
            self.assertIsNone(credential.verification_error)
            self.assertIsNotNone(credential.verification_checked_at)

        probe_mock.assert_called_once()

    @patch("app.app.integrations._probe_gitlab_pat", return_value=(False, "Network error: boom"))
    def test_pat_verify_failure_surfaces_error(self, probe_mock) -> None:
        with TestClient(self.main.app) as client:
            rotate_resp = client.post(
                "/integrations/pat",
                json={"token": "gitlab-token"},
            )
            self.assertEqual(rotate_resp.status_code, 200)

            verify_resp = client.post(
                "/integrations/pat/verify",
                json={"gitlab_host": "gitlab.internal"},
            )
            self.assertEqual(verify_resp.status_code, 200)
            payload = verify_resp.json()
            self.assertEqual(payload["verification_status"], "error")
            self.assertIn("Network error", payload["verification_error"] or "")
            self.assertEqual(payload["verification_host"], "https://gitlab.internal")

        from sqlmodel import Session, select
        from app.app.database import engine
        from app.app.integrations import GITLAB_PAT_KIND, VERIFICATION_STATUS_ERROR
        from app.app.models import IntegrationCredential

        with Session(engine) as session:
            credential = session.exec(
                select(IntegrationCredential).where(IntegrationCredential.kind == GITLAB_PAT_KIND)
            ).one()
            self.assertEqual(credential.verification_status, VERIFICATION_STATUS_ERROR)
            self.assertIsNotNone(credential.verification_error)
            self.assertEqual(credential.verification_host, "https://gitlab.internal")

        probe_mock.assert_called_once()

    def test_pat_verify_requires_token(self) -> None:
        with TestClient(self.main.app) as client:
            verify_resp = client.post("/integrations/pat/verify")
            self.assertEqual(verify_resp.status_code, 400)
            self.assertIn("not configured", verify_resp.json().get("detail", ""))

    def test_pat_verify_rejects_invalid_host(self) -> None:
        with TestClient(self.main.app) as client:
            rotate_resp = client.post("/integrations/pat", json={"token": "gitlab-token"})
            self.assertEqual(rotate_resp.status_code, 200)

            verify_resp = client.post(
                "/integrations/pat/verify",
                json={"gitlab_host": "ftp://example.com"},
            )
            self.assertEqual(verify_resp.status_code, 400)
            self.assertIn("http", verify_resp.json().get("detail", ""))

    def test_pat_status_reads_from_environment(self) -> None:
        previous = os.environ.get("GITLAB_PAT")
        os.environ["GITLAB_PAT"] = "env-token"
        try:
            with TestClient(self.main.app) as client:
                status_resp = client.get("/integrations/pat")
                self.assertEqual(status_resp.status_code, 200)
                snapshot = status_resp.json()
                self.assertTrue(snapshot["configured"])
                self.assertIsNone(snapshot["updated_at"])
                self.assertIsNone(snapshot["updated_by"])

            from sqlmodel import Session, select

            from app.app.database import engine
            from app.app.integrations import GITLAB_PAT_KIND
            from app.app.models import IntegrationCredential

            with Session(engine) as session:
                rows = session.exec(
                    select(IntegrationCredential).where(IntegrationCredential.kind == GITLAB_PAT_KIND)
                ).all()
                self.assertFalse(rows)
        finally:
            if previous is None:
                os.environ.pop("GITLAB_PAT", None)
            else:
                os.environ["GITLAB_PAT"] = previous


if __name__ == "__main__":
    unittest.main()
