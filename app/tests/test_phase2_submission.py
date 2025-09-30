import os
import subprocess
import sys
import tempfile
import time
import unittest
from pathlib import Path

from fastapi.testclient import TestClient

from app.app.project_cache import project_cache_repo_path


def _initialize_repo(path: Path) -> None:
    subprocess.run(["git", "init", "-b", "main"], cwd=path, check=True, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    subprocess.run(["git", "config", "user.email", "phase2@example.com"], cwd=path, check=True, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    subprocess.run(["git", "config", "user.name", "Phase2 Tester"], cwd=path, check=True, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    subprocess.run(["git", "add", "."], cwd=path, check=True, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    subprocess.run(["git", "commit", "-m", "Initial commit"], cwd=path, check=True, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)


class Phase2TaskSubmissionTests(unittest.TestCase):
    def setUp(self) -> None:
        self.tmp_dir = tempfile.TemporaryDirectory()
        self.db_path = Path(self.tmp_dir.name) / "phase2.db"
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

    def _prepare_project(self) -> tuple[Path, int]:
        project_root = project_cache_repo_path("https://gitlab.example.com", "example/phase2")
        project_root.mkdir(parents=True, exist_ok=True)
        (project_root / "README.md").write_text("phase2 demo\n", encoding="utf-8")
        (project_root / "app.py").write_text("print('hello')\n", encoding="utf-8")
        _initialize_repo(project_root)

        with TestClient(self.main.app) as client:
            rotate_resp = client.post("/integrations/pat", json={"token": "sk-phase2"})
            self.assertEqual(rotate_resp.status_code, 200)
            project_payload = {
                "name": "phase2-project",
                "default_branch": "main",
                "gitlab_host": "https://gitlab.example.com",
                "gitlab_project_path": "example/phase2",
            }
            project_resp = client.post("/projects", json=project_payload)
            self.assertEqual(project_resp.status_code, 201)
            project_data = project_resp.json()
            self.assertEqual(project_data["cache_path"], str(project_root))
            self.assertEqual(project_data["cache_status"], "ready")
            project_id = project_data["id"]
        return project_root, project_id

    def test_task_records_branch_and_model(self) -> None:
        _, project_id = self._prepare_project()

        with TestClient(self.main.app) as client:
            models_resp = client.get("/models")
            self.assertEqual(models_resp.status_code, 200)
            models = models_resp.json()
            self.assertTrue(models, "Expected models endpoint to return at least one model")
            chosen_model = models[0]["id"]

            task_resp = client.post(
                "/tasks",
                json={
                    "project_id": project_id,
                    "prompt": "Add demo file",
                    "allowlist": [],
                    "branch_name": "feature/custom-branch",
                    "codex_model": chosen_model,
                    "codex_reasoning_effort": "high",
                },
            )
            self.assertEqual(task_resp.status_code, 201)
            task_id = task_resp.json()["id"]

            deadline = time.time() + 30
            final_payload = None
            while time.time() < deadline:
                detail_resp = client.get(f"/tasks/{task_id}")
                self.assertEqual(detail_resp.status_code, 200)
                final_payload = detail_resp.json()
                if final_payload["status"] in {"done", "failed"}:
                    break
                time.sleep(0.2)

            self.assertIsNotNone(final_payload)
            assert final_payload is not None
            self.assertEqual(final_payload["status"], "done")
            self.assertEqual(final_payload["branch"], "feature/custom-branch")
            self.assertEqual(final_payload["codex_model"], chosen_model)
            self.assertEqual(final_payload["codex_reasoning_effort"], "high")

            logs_resp = client.get(f"/tasks/{task_id}/logs?follow=0")
            self.assertEqual(logs_resp.status_code, 200)
            snapshot_payload = logs_resp.json()
            entries = snapshot_payload.get("entries", [])
            self.assertEqual(snapshot_payload.get("status"), "done")
            self.assertEqual(snapshot_payload.get("branch"), "feature/custom-branch")
            self.assertEqual(snapshot_payload.get("codex_model"), chosen_model)
            self.assertEqual(snapshot_payload.get("codex_reasoning_effort"), "high")
            self.assertFalse(snapshot_payload.get("abort_requested", False))
            joined = "\n".join(entries)
            self.assertIn("Using requested branch: feature/custom-branch", joined)
            self.assertIn(
                f"Codex model: {chosen_model} (reasoning effort: high)",
                joined,
            )

    def test_rejects_invalid_branch(self) -> None:
        _, project_id = self._prepare_project()

        with TestClient(self.main.app) as client:
            response = client.post(
                "/tasks",
                json={
                    "project_id": project_id,
                    "prompt": "Invalid branch",
                    "allowlist": [],
                    "branch_name": "invalid branch name",
                },
            )
            self.assertEqual(response.status_code, 400)
            detail = response.json().get("detail")
            self.assertIn("Branch name", detail)

    def test_rejects_invalid_reasoning_effort(self) -> None:
        _, project_id = self._prepare_project()

        with TestClient(self.main.app) as client:
            response = client.post(
                "/tasks",
                json={
                    "project_id": project_id,
                    "prompt": "Invalid reasoning effort",
                    "allowlist": [],
                    "codex_reasoning_effort": "extreme",
                },
            )
            self.assertEqual(response.status_code, 400)
            detail = response.json().get("detail")
            self.assertIn("reasoning effort", detail)

    def test_rejects_unknown_model(self) -> None:
        _, project_id = self._prepare_project()

        with TestClient(self.main.app) as client:
            response = client.post(
                "/tasks",
                json={
                    "project_id": project_id,
                    "prompt": "Invalid model",
                    "allowlist": [],
                    "codex_model": "totally-unknown",
                },
            )
            self.assertEqual(response.status_code, 400)
            detail = response.json().get("detail")
            self.assertIn("Codex model", detail)


if __name__ == "__main__":
    unittest.main()
