import os
import shutil
import subprocess
import sys
import tempfile
import time
import unittest
from pathlib import Path

from fastapi.testclient import TestClient

from app.app.project_cache import project_cache_repo_path


def _initialize_git_repo(path: Path) -> None:
    subprocess.run(["git", "init", "-b", "main"], cwd=path, check=True, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    subprocess.run(["git", "config", "user.email", "test@example.com"], cwd=path, check=True, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    subprocess.run(["git", "config", "user.name", "Codex Test"], cwd=path, check=True, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    subprocess.run(["git", "add", "."], cwd=path, check=True, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    subprocess.run(["git", "commit", "-m", "Initial commit"], cwd=path, check=True, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)


class Phase5NegativeTokenTests(unittest.TestCase):
    def setUp(self) -> None:
        self.tmp_dir = tempfile.TemporaryDirectory()
        self.original_path = os.environ.get("PATH", "")
        os.environ["APP_DATABASE_URL"] = f"sqlite:///{Path(self.tmp_dir.name) / 'test.db'}"
        os.environ["RUNNER_DISABLE_DOCKER"] = "1"
        os.environ.pop("RUNNER_GIT_DRY_RUN", None)
        os.environ["PROJECT_CACHE_ROOT"] = str(Path(self.tmp_dir.name) / "cache")
        for module in list(sys.modules.keys()):
            if module.startswith("app.app"):
                sys.modules.pop(module)
        from sqlmodel import SQLModel

        SQLModel.metadata.clear()
        from app.app import main as main_module

        self.main = main_module
        self.bad_token = "invalid-token-123"
        self._install_git_wrapper()

    def tearDown(self) -> None:
        os.environ.pop("APP_DATABASE_URL", None)
        os.environ.pop("RUNNER_DISABLE_DOCKER", None)
        os.environ.pop("RUNNER_GIT_DRY_RUN", None)
        os.environ.pop("PROJECT_CACHE_ROOT", None)
        if self.original_path:
            os.environ["PATH"] = self.original_path
        else:
            os.environ.pop("PATH", None)
        self.tmp_dir.cleanup()

    def _install_git_wrapper(self) -> None:
        real_git = shutil.which("git")
        if not real_git:
            raise RuntimeError("git executable not found")
        wrapper_dir = Path(self.tmp_dir.name) / "fakegit"
        wrapper_dir.mkdir(parents=True, exist_ok=True)
        script_path = wrapper_dir / "git"
        script_path.write_text(
            f"""#!/usr/bin/env bash
set -euo pipefail
if [[ ${{1:-}} == push ]]; then
  >&2 echo "remote: HTTP Basic: Access denied"
  >&2 echo "fatal: Authentication failed for 'https://oauth2:{self.bad_token}@gitlab.example.com/example/demo.git'"
  exit 128
fi
exec "{real_git}" "$@"
""",
            encoding="utf-8",
        )
        script_path.chmod(0o755)
        os.environ["PATH"] = f"{script_path.parent}:{self.original_path}"

    def _build_sample_project(self) -> Path:
        project_root = project_cache_repo_path("https://gitlab.example.com", "example/demo")
        project_root.mkdir(parents=True, exist_ok=True)
        (project_root / "README.md").write_text("phase5 demo\n", encoding="utf-8")
        (project_root / "main.txt").write_text("hello\n", encoding="utf-8")
        _initialize_git_repo(project_root)
        return project_root

    def test_invalid_token_marks_task_failed_and_redacts_logs(self) -> None:
        project_root = self._build_sample_project()
        sanitized_root: Path | None = None

        with TestClient(self.main.app) as client:
            rotate_resp = client.post(
                "/integrations/pat",
                json={"token": self.bad_token},
            )
            self.assertEqual(rotate_resp.status_code, 200)

            project_payload = {
                "name": "phase5-negative",
                "default_branch": "main",
                "gitlab_host": "https://gitlab.example.com",
                "gitlab_project_path": "example/demo",
            }
            project_resp = client.post("/projects", json=project_payload)
            self.assertEqual(project_resp.status_code, 201)
            project_body = project_resp.json()
            self.assertEqual(project_body["cache_path"], str(project_root))
            self.assertEqual(project_body["cache_status"], "ready")
            project_id = project_body["id"]

            task_resp = client.post(
                "/tasks",
                json={"project_id": project_id, "prompt": "Trigger invalid token"},
            )
            self.assertEqual(task_resp.status_code, 201)
            task_id = task_resp.json()["id"]

            deadline = time.time() + 15
            final_payload = None
            while time.time() < deadline:
                detail_resp = client.get(f"/tasks/{task_id}")
                self.assertEqual(detail_resp.status_code, 200)
                final_payload = detail_resp.json()
                if final_payload["status"] in {"done", "failed"}:
                    break
                time.sleep(0.25)

            self.assertIsNotNone(final_payload, "Expected task detail payload")
            self.assertEqual(final_payload["status"], "failed", "Task should fail with invalid token")
            workspace_path = final_payload.get("workspace_path")
            self.assertIsNotNone(workspace_path, "Workspace path should be recorded")
            sanitized_root = Path(workspace_path)

            logs_resp = client.get(f"/tasks/{task_id}/logs?follow=0")
            self.assertEqual(logs_resp.status_code, 200)
            snapshot_payload = logs_resp.json()
            entries = snapshot_payload.get("entries", [])
            self.assertEqual(snapshot_payload.get("status"), "failed")
            self.assertFalse(snapshot_payload.get("abort_requested", False))
            self.assertTrue(
                any("codex agent: invalid token supplied" in entry.lower() for entry in entries)
                or any("git push failed" in entry.lower() for entry in entries)
            )
            self.assertTrue(any("Codex FAIL" in entry for entry in entries))
            for entry in entries:
                self.assertNotIn(self.bad_token, entry)

        if sanitized_root:
            shutil.rmtree(sanitized_root.parent, ignore_errors=True)


if __name__ == "__main__":
    unittest.main()
