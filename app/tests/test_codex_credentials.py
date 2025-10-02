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

from app.app.project_cache import project_cache_repo_path


class CodexCredentialTests(unittest.TestCase):
    def setUp(self) -> None:
        self.tmp_dir = tempfile.TemporaryDirectory()
        os.environ["APP_DATABASE_URL"] = f"sqlite:///{Path(self.tmp_dir.name) / 'creds.db'}"
        key_material = base64.urlsafe_b64encode(b"test-secret-fernet-key-for-cdx!!").decode("utf-8")
        os.environ["APP_SECRET_KEY"] = key_material
        os.environ["PROJECT_CACHE_ROOT"] = str(Path(self.tmp_dir.name) / "cache")
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
        os.environ.pop("PROJECT_CACHE_ROOT", None)
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

    def test_project_creation_exposes_cache_metadata_without_codex_token_fields(self) -> None:
        os.environ["RUNNER_DISABLE_DOCKER"] = "1"
        project_root = project_cache_repo_path("https://gitlab.example.com", "example/cred-demo")
        project_root.mkdir(parents=True, exist_ok=True)
        (project_root / "README.md").write_text("demo\n", encoding="utf-8")
        (project_root / ".git").mkdir(parents=True, exist_ok=True)

        with TestClient(self.main.app) as client:
            rotate_resp = client.post("/integrations/pat", json={"token": "gitlab-token"})
            self.assertEqual(rotate_resp.status_code, 200)
            payload = {
                "name": "cred-demo",
                "default_branch": "main",
                "gitlab_host": "https://gitlab.example.com",
                "gitlab_project_path": "example/cred-demo",
            }
            response = client.post("/projects", json=payload)
            self.assertEqual(response.status_code, 201)
            body = response.json()
            self.assertEqual(body["cache_path"], str(project_root))
            self.assertEqual(body["cache_status"], "ready")
            self.assertNotIn("codex_token_configured", body)
            self.assertNotIn("codex_token_updated_at", body)

    def test_missing_session_bundle_aborts_when_docker_enabled(self) -> None:
        os.environ.pop("RUNNER_DISABLE_DOCKER", None)
        project_root = project_cache_repo_path(
            "https://gitlab.example.com",
            "example/cred-missing-token",
        )
        project_root.mkdir(parents=True, exist_ok=True)
        (project_root / "README.md").write_text("demo\n", encoding="utf-8")
        (project_root / ".git").mkdir(parents=True, exist_ok=True)

        with TestClient(self.main.app) as client:
            rotate_resp = client.post("/integrations/pat", json={"token": "gitlab-token"})
            self.assertEqual(rotate_resp.status_code, 200)
            payload = {
                "name": "cred-missing-token",
                "default_branch": "main",
                "gitlab_host": "https://gitlab.example.com",
                "gitlab_project_path": "example/cred-missing-token",
            }
            response = client.post("/projects", json=payload)
            self.assertEqual(response.status_code, 201)
            project_body = response.json()
            self.assertEqual(project_body["cache_path"], str(project_root))
            self.assertEqual(project_body["cache_status"], "ready")
            project_id = project_body["id"]

            task_resp = client.post(
                "/tasks",
                json={
                    "project_id": project_id,
                    "prompt": "Attempt run without session",
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
                    "Codex credentials unavailable; import a ChatGPT session bundle" in entry
                    for entry in entries
                )
            )

    def test_session_bundle_enables_stub_execution(self) -> None:
        os.environ["RUNNER_DISABLE_DOCKER"] = "1"
        os.environ["RUNNER_GIT_DRY_RUN"] = "1"
        self.addCleanup(lambda: os.environ.pop("RUNNER_GIT_DRY_RUN", None))
        project_root = project_cache_repo_path(
            "https://gitlab.example.com",
            "example/cred-session-demo",
        )
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
                "default_branch": "main",
                "gitlab_host": "https://gitlab.example.com",
                "gitlab_project_path": "example/cred-session-demo",
            }
            response = client.post("/projects", json=payload)
            self.assertEqual(response.status_code, 201)
            project_body = response.json()
            self.assertEqual(project_body["cache_path"], str(project_root))
            self.assertEqual(project_body["cache_status"], "ready")
            project_id = project_body["id"]

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
