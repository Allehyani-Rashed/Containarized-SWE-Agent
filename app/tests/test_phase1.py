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


class Phase1FlowTests(unittest.TestCase):
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

    def test_project_registration_and_task_completion(self) -> None:
        with TestClient(self.main.app) as client:
            project_root = Path(self.tmp_dir.name) / "phase1-project"
            project_root.mkdir(parents=True, exist_ok=True)
            (project_root / "README.md").write_text("phase1 demo\n", encoding="utf-8")
            _initialize_git_repo(project_root)

            rotate_resp = client.post(
                "/integrations/pat",
                json={"token": "test-token"},
            )
            self.assertEqual(rotate_resp.status_code, 200)

            project_payload = {
                "name": "demo-project",
                "local_path": str(project_root),
                "default_branch": "main",
                "gitlab_host": "https://gitlab.example.com",
                "gitlab_project_path": "example/demo",
            }
            project_resp = client.post("/projects", json=project_payload)
            self.assertEqual(project_resp.status_code, 201)
            project_data = project_resp.json()
            self.assertIn("id", project_data)

            projects_resp = client.get("/projects")
            self.assertEqual(projects_resp.status_code, 200)
            projects = projects_resp.json()
            self.assertEqual(len(projects), 1)

            task_resp = client.post(
                "/tasks",
                json={
                    "project_id": project_data["id"],
                    "prompt": "Simulate a codex task",
                    "allowlist": ["gitlab.example.com"],
                },
            )
            self.assertEqual(task_resp.status_code, 201)
            task_data = task_resp.json()
            self.assertEqual(task_data["status"], "pending")

            task_id = task_data["id"]
            deadline = time.time() + 8
            final_status = None
            while time.time() < deadline:
                detail_resp = client.get(f"/tasks/{task_id}")
                self.assertEqual(detail_resp.status_code, 200)
                final_status = detail_resp.json()["status"]
                if final_status == "done":
                    break
                time.sleep(0.2)

            self.assertEqual(final_status, "done", "Task did not reach done state in time")

            detail_resp = client.get(f"/tasks/{task_id}")
            self.assertEqual(detail_resp.status_code, 200)
            detail_payload = detail_resp.json()
            invocation_flags = detail_payload.get("codex_invocation") or ""
            self.assertIn("--yolo", invocation_flags)
            self.assertIn("--skip-git-repo-check", invocation_flags)
            self.assertEqual(detail_payload.get("codex_agent_version"), "codex-stub/0.3")

            logs_snapshot = client.get(f"/tasks/{task_id}/logs?follow=0")
            self.assertEqual(logs_snapshot.status_code, 200)
            entries = logs_snapshot.json().get("entries", [])
            self.assertTrue(entries, "Expected log snapshot entries")
            self.assertTrue(
                any("Codex SUCCESS" in entry for entry in entries),
                "Expected codex success log entry",
            )

            with client.stream("GET", f"/tasks/{task_id}/logs") as stream_resp:
                content_type = stream_resp.headers.get("content-type", "")
                self.assertIn("text/event-stream", content_type)
                streamed_lines = list(stream_resp.iter_lines())
            self.assertTrue(streamed_lines, "Expected streamed log lines")
            self.assertTrue(
                any(
                    "Codex SUCCESS" in line
                    for line in streamed_lines
                    if isinstance(line, str)
                ),
                "Expected codex success message in streamed logs",
            )


if __name__ == "__main__":
    unittest.main()
