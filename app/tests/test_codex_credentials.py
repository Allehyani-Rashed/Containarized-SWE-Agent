import base64
import json
import os
import shutil
import subprocess
import sys
import tempfile
import time
import unittest
from datetime import datetime, timedelta, timezone
from pathlib import Path

from fastapi.testclient import TestClient


class CodexCredentialTests(unittest.TestCase):
    def setUp(self) -> None:
        self.tmp_dir = tempfile.TemporaryDirectory()
        os.environ["APP_DATABASE_URL"] = f"sqlite:///{Path(self.tmp_dir.name) / 'creds.db'}"
        key_material = base64.urlsafe_b64encode(b"test-secret-fernet-key-for-cdx!!").decode("utf-8")
        os.environ["APP_SECRET_KEY"] = key_material
        for module in list(sys.modules.keys()):
            if module.startswith("app.app"):
                sys.modules.pop(module)
        from sqlmodel import SQLModel

        SQLModel.metadata.clear()
        from app.app import main as main_module
        from app.app import secrets

        secrets.reset_secret_manager()
        self.secrets = secrets
        self.main = main_module
        self.repo_root = Path(__file__).resolve().parents[2]
        workspaces_dir = self.repo_root / "workspaces"
        if workspaces_dir.exists():
            shutil.rmtree(workspaces_dir)

    def tearDown(self) -> None:
        self.tmp_dir.cleanup()
        os.environ.pop("APP_DATABASE_URL", None)
        os.environ.pop("APP_SECRET_KEY", None)
        os.environ.pop("RUNNER_DISABLE_DOCKER", None)
        self.secrets.reset_secret_manager()
        workspaces_dir = getattr(self, "repo_root", Path(__file__).resolve().parents[2]) / "workspaces"
        if workspaces_dir.exists():
            shutil.rmtree(workspaces_dir)

    def _session_bundle(self) -> str:
        future = datetime.now(timezone.utc) + timedelta(hours=2)
        payload = {
            "session": {
                "session_token": "session-token-demo",
                "expires_at": future.astimezone(timezone.utc).isoformat().replace("+00:00", "Z"),
            }
        }
        return json.dumps(payload)

    def test_project_creation_encrypts_codex_token(self) -> None:
        os.environ["RUNNER_DISABLE_DOCKER"] = "1"
        project_root = Path(self.tmp_dir.name) / "repo"
        project_root.mkdir(parents=True, exist_ok=True)
        (project_root / "README.md").write_text("demo\n", encoding="utf-8")
        (project_root / ".git").mkdir(parents=True, exist_ok=True)

        token_value = "codex-secret-token"
        with TestClient(self.main.app) as client:
            rotate_resp = client.post("/integrations/pat", json={"token": "gitlab-token"})
            self.assertEqual(rotate_resp.status_code, 200)
            payload = {
                "name": "cred-demo",
                "local_path": str(project_root),
                "default_branch": "main",
                "gitlab_host": "https://gitlab.example.com",
                "gitlab_project_path": "example/cred-demo",
                "codex_token": token_value,
            }
            response = client.post("/projects", json=payload)
            self.assertEqual(response.status_code, 201)
            body = response.json()
            self.assertTrue(body["codex_token_configured"])
            self.assertIsNotNone(body["codex_token_updated_at"])

        from sqlmodel import Session, select
        from app.app.database import engine
        from app.app.models import Project
        from app.app.secrets import get_secret_manager

        with Session(engine) as session:
            project = session.exec(select(Project)).first()
            self.assertIsNotNone(project)
            assert project is not None
            self.assertIsNotNone(project.codex_token_encrypted)
            self.assertNotEqual(project.codex_token_encrypted, token_value)
            manager = get_secret_manager()
            decrypted = manager.decrypt(project.codex_token_encrypted)
            self.assertEqual(decrypted, token_value)

    def test_missing_codex_token_aborts_when_docker_enabled(self) -> None:
        os.environ.pop("RUNNER_DISABLE_DOCKER", None)
        project_root = Path(self.tmp_dir.name) / "repo-missing-token"
        project_root.mkdir(parents=True, exist_ok=True)
        (project_root / "README.md").write_text("demo\n", encoding="utf-8")
        (project_root / ".git").mkdir(parents=True, exist_ok=True)

        with TestClient(self.main.app) as client:
            rotate_resp = client.post("/integrations/pat", json={"token": "gitlab-token"})
            self.assertEqual(rotate_resp.status_code, 200)
            payload = {
                "name": "cred-missing-token",
                "local_path": str(project_root),
                "default_branch": "main",
                "gitlab_host": "https://gitlab.example.com",
                "gitlab_project_path": "example/cred-missing-token",
            }
            response = client.post("/projects", json=payload)
            self.assertEqual(response.status_code, 201)
            project_id = response.json()["id"]

            task_resp = client.post(
                "/tasks",
                json={
                    "project_id": project_id,
                    "prompt": "Attempt run without codex token",
                },
            )
            self.assertEqual(task_resp.status_code, 201)
            task_id = task_resp.json()["id"]

            deadline = datetime.now() + timedelta(seconds=5)
            detail_payload = None
            while datetime.now() < deadline:
                detail = client.get(f"/tasks/{task_id}")
                self.assertEqual(detail.status_code, 200)
                detail_payload = detail.json()
                if detail_payload["status"] in {"done", "failed"}:
                    break
                time.sleep(0.2)

            self.assertIsNotNone(detail_payload)
            assert detail_payload is not None
            self.assertEqual(detail_payload["status"], "failed")
            logs = client.get(f"/tasks/{task_id}/logs?follow=0")
            self.assertEqual(logs.status_code, 200)
            snapshot_payload = logs.json()
            entries = snapshot_payload.get("entries", [])
            self.assertEqual(snapshot_payload.get("status"), "failed")
            self.assertFalse(snapshot_payload.get("abort_requested", False))
            self.assertTrue(
                any(
                    "Codex credentials unavailable" in entry or "configure a CODEX access token" in entry
                    for entry in entries
                )
            )

    def test_session_bundle_enables_stub_execution(self) -> None:
        os.environ["RUNNER_DISABLE_DOCKER"] = "1"
        os.environ["RUNNER_GIT_DRY_RUN"] = "1"
        self.addCleanup(lambda: os.environ.pop("RUNNER_GIT_DRY_RUN", None))
        project_root = Path(self.tmp_dir.name) / "repo-session"
        project_root.mkdir(parents=True, exist_ok=True)
        (project_root / "README.md").write_text("demo\n", encoding="utf-8")
        (project_root / ".git").mkdir(parents=True, exist_ok=True)

        subprocess.run(["git", "init", "-b", "main"], cwd=project_root, check=True, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        subprocess.run(["git", "config", "user.email", "codex@test.local"], cwd=project_root, check=True, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        subprocess.run(["git", "config", "user.name", "Codex Test"], cwd=project_root, check=True, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        subprocess.run(["git", "add", "."], cwd=project_root, check=True, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        subprocess.run(["git", "commit", "-m", "Initial commit"], cwd=project_root, check=True, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)

        bundle = self._session_bundle()

        with TestClient(self.main.app) as client:
            rotate_resp = client.post("/integrations/pat", json={"token": "gitlab-token"})
            self.assertEqual(rotate_resp.status_code, 200)

            session_resp = client.post(
                "/integrations/pat/session",
                json={"bundle": bundle, "updated_by": "tester"},
            )
            self.assertEqual(session_resp.status_code, 200)

            payload = {
                "name": "cred-session-demo",
                "local_path": str(project_root),
                "default_branch": "main",
                "gitlab_host": "https://gitlab.example.com",
                "gitlab_project_path": "example/cred-session-demo",
            }
            response = client.post("/projects", json=payload)
            self.assertEqual(response.status_code, 201)
            project_id = response.json()["id"]

            task_resp = client.post(
                "/tasks",
                json={
                    "project_id": project_id,
                    "prompt": "Execute with session bundle",
                },
            )
            self.assertEqual(task_resp.status_code, 201)
            task_id = task_resp.json()["id"]

            deadline = datetime.now() + timedelta(seconds=5)
            detail_payload = None
            while datetime.now() < deadline:
                detail = client.get(f"/tasks/{task_id}")
                self.assertEqual(detail.status_code, 200)
                detail_payload = detail.json()
                if detail_payload["status"] in {"done", "failed"}:
                    break
                time.sleep(0.2)

            logs_resp = client.get(f"/tasks/{task_id}/logs?follow=0")
            self.assertEqual(logs_resp.status_code, 200)
            snapshot_payload = logs_resp.json()
            entries = snapshot_payload.get("entries", [])
            self.assertEqual(snapshot_payload.get("status"), "done")
            self.assertFalse(snapshot_payload.get("abort_requested", False))
            self.assertIsNotNone(detail_payload)
            assert detail_payload is not None
            self.assertEqual(detail_payload["status"], "done", entries)
            self.assertTrue(any("ChatGPT session bundle" in entry for entry in entries))


if __name__ == "__main__":
    unittest.main()
