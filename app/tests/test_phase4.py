import os
import subprocess
import sys
import tempfile
import time
import unittest
from pathlib import Path

from fastapi.testclient import TestClient


def _initialize_git_repo(path: Path) -> None:
    subprocess.run(["git", "init", "-b", "main"], cwd=path, check=True, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    subprocess.run(["git", "config", "user.email", "test@example.com"], cwd=path, check=True, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    subprocess.run(["git", "config", "user.name", "Codex Test"], cwd=path, check=True, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    subprocess.run(["git", "add", "."], cwd=path, check=True, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    subprocess.run(["git", "commit", "-m", "Initial commit"], cwd=path, check=True, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)


class Phase4CodexIntegrationTests(unittest.TestCase):
    def setUp(self) -> None:
        self.tmp_dir = tempfile.TemporaryDirectory()
        os.environ["APP_DATABASE_URL"] = f"sqlite:///{Path(self.tmp_dir.name) / 'test.db'}"
        os.environ["RUNNER_DISABLE_DOCKER"] = "1"
        os.environ["RUNNER_GIT_DRY_RUN"] = "1"
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
        os.environ.pop("RUNNER_GIT_DRY_RUN", None)

    def test_codex_placeholder_creates_change_log(self) -> None:
        with TestClient(self.main.app) as client:
            project_root = Path(self.tmp_dir.name) / "phase4-project"
            project_root.mkdir(parents=True, exist_ok=True)
            (project_root / "README.md").write_text("phase4 demo\n", encoding="utf-8")
            _initialize_git_repo(project_root)

            rotate_resp = client.post(
                "/integrations/pat",
                json={"token": "test-token"},
            )
            self.assertEqual(rotate_resp.status_code, 200)

            project_payload = {
                "name": "phase4-demo",
                "local_path": str(project_root),
                "default_branch": "main",
                "gitlab_host": "https://gitlab.example.com",
                "gitlab_project_path": "example/demo",
            }
            project_resp = client.post("/projects", json=project_payload)
            self.assertEqual(project_resp.status_code, 201)
            project_data = project_resp.json()

            task_resp = client.post(
                "/tasks",
                json={
                    "project_id": project_data["id"],
                    "prompt": "Run placeholder codex",
                },
            )
            self.assertEqual(task_resp.status_code, 201)
            task_id = task_resp.json()["id"]

            deadline = time.time() + 10
            final_payload = None
            while time.time() < deadline:
                detail_resp = client.get(f"/tasks/{task_id}")
                self.assertEqual(detail_resp.status_code, 200)
                final_payload = detail_resp.json()
                if final_payload["status"] in {"done", "failed"}:
                    break
                time.sleep(0.25)

            self.assertIsNotNone(final_payload)
            self.assertEqual(final_payload["status"], "done")
            self.assertEqual(final_payload["codex_agent_version"], "codex-stub/0.3")
            invocation_flags = final_payload.get("codex_invocation") or ""
            self.assertIn("--yolo", invocation_flags)
            self.assertIn("--skip-git-repo-check", invocation_flags)
            workspace_path = Path(final_payload["workspace_path"])
            change_log = workspace_path / "CODEX_CHANGE.log"
            self.assertTrue(change_log.exists(), "Expected placeholder change log")
            contents = change_log.read_text(encoding="utf-8")
            self.assertIn("codex placeholder executed", contents)

            snapshot = client.get(f"/tasks/{task_id}/logs?follow=0")
            self.assertEqual(snapshot.status_code, 200)
            snapshot_payload = snapshot.json()
            entries = snapshot_payload.get("entries", [])
            self.assertEqual(snapshot_payload.get("status"), "done")
            self.assertFalse(snapshot_payload.get("abort_requested", False))
            self.assertTrue(any("Codex SUCCESS" in entry for entry in entries))
            self.assertTrue(any("codex placeholder wrote change log" in entry for entry in entries))


if __name__ == "__main__":
    unittest.main()
