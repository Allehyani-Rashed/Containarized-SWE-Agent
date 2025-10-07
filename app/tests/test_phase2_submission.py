import json
import os
import subprocess
import sys
import tempfile
import time
import unittest
from pathlib import Path
from unittest.mock import MagicMock, patch

from fastapi.testclient import TestClient

from app.app.project_cache import project_cache_repo_path
from app.app.worker import _build_mr_title


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
        os.environ.pop("GITLAB_PAT", None)
        self.tmp_dir.cleanup()

    def _prepare_project(self, *, configure_pat: bool = True) -> tuple[Path, int]:
        project_root = project_cache_repo_path("https://gitlab.example.com", "example/phase2")
        project_root.mkdir(parents=True, exist_ok=True)
        (project_root / "README.md").write_text("phase2 demo\n", encoding="utf-8")
        (project_root / "app.py").write_text("print('hello')\n", encoding="utf-8")
        _initialize_repo(project_root)
        subprocess.run(
            ["git", "branch", "release"],
            cwd=project_root,
            check=True,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
        )

        with TestClient(self.main.app) as client:
            if configure_pat:
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

    def test_list_project_branches_fetches_from_gitlab(self) -> None:
        _, project_id = self._prepare_project()

        with TestClient(self.main.app) as client, patch("app.app.api.projects.urlopen") as mock_urlopen:
            mock_response = MagicMock()
            mock_response.getcode.return_value = 200
            mock_response.read.return_value = json.dumps(
                [
                    {"name": "main", "default": True},
                    {"name": "release", "default": False},
                ]
            ).encode("utf-8")
            mock_response.headers = {"X-Next-Page": "3"}
            mock_urlopen.return_value.__enter__.return_value = mock_response

            response = client.get(f"/projects/{project_id}/branches?search=rel&per_page=5&page=2")
            self.assertEqual(response.status_code, 200)
            payload = response.json()
            self.assertEqual(payload.get("next_page"), 3)
            self.assertEqual([item["name"] for item in payload.get("items", [])], ["main", "release"])

            called_request = mock_urlopen.call_args[0][0]
            self.assertTrue(
                called_request.full_url.startswith(
                    "https://gitlab.example.com/api/v4/projects/example%2Fphase2/repository/branches",
                )
            )
            headers = {key.lower(): value for key, value in called_request.header_items()}
            self.assertEqual(headers.get("private-token"), "sk-phase2")
            self.assertIn("per_page=5", called_request.full_url)
            self.assertIn("page=2", called_request.full_url)
            self.assertIn("search=rel", called_request.full_url)

    def test_list_project_branches_requires_pat(self) -> None:
        _, project_id = self._prepare_project(configure_pat=False)

        with TestClient(self.main.app) as client:
            response = client.get(f"/projects/{project_id}/branches")
            self.assertEqual(response.status_code, 409)
            detail = response.json().get("detail", "")
            self.assertIn("PAT", detail)

    def test_project_response_includes_concurrency_fields(self) -> None:
        _, project_id = self._prepare_project()

        with TestClient(self.main.app) as client:
            response = client.get("/projects")
            self.assertEqual(response.status_code, 200)
            payload = response.json()
            self.assertIsInstance(payload, list)
            project_summary = next((item for item in payload if item.get("id") == project_id), None)
            self.assertIsNotNone(project_summary)
            self.assertNotIn("max_concurrency", project_summary)
            self.assertIn("last_active_count", project_summary)

    def test_concurrency_settings_endpoint(self) -> None:
        self._prepare_project()

        with TestClient(self.main.app) as client:
            show_resp = client.get("/settings/concurrency")
            self.assertEqual(show_resp.status_code, 200)
            settings = show_resp.json()
            self.assertIn("project_limit", settings)
            self.assertIn("effective_project_limit", settings)

            update_resp = client.patch(
                "/settings/concurrency",
                json={"project_limit": 3, "actor": "unittest"},
            )
            self.assertEqual(update_resp.status_code, 200)
            updated = update_resp.json()
            self.assertEqual(updated.get("project_limit"), 3)
            self.assertEqual(updated.get("updated_by"), "unittest")

    def test_task_response_includes_credentials(self) -> None:
        _, project_id = self._prepare_project()

        with TestClient(self.main.app) as client:
            task_resp = client.post(
                "/tasks",
                json={"project_id": project_id, "prompt": "Check credentials"},
            )
            self.assertEqual(task_resp.status_code, 201)
            task_payload = task_resp.json()
            task_id = task_payload["id"]

            detail_resp = client.get(f"/tasks/{task_id}")
            self.assertEqual(detail_resp.status_code, 200)
            detail = detail_resp.json()
            self.assertIn("credentials", detail)
            credentials = detail["credentials"]
            self.assertIn("gitlab_pat_available", credentials)
            self.assertIn("chatgpt_session_available", credentials)

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
                    "branch_name": "feature/custom-branch",
                    "codex_model": chosen_model,
                    "codex_reasoning_effort": "high",
                    "mr_title": "Phase 2 Custom Title",
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
            self.assertEqual(final_payload["target_branch"], "main")
            self.assertEqual(final_payload["codex_model"], chosen_model)
            self.assertEqual(final_payload["codex_reasoning_effort"], "high")
            self.assertEqual(final_payload["mr_title"], "Phase 2 Custom Title")
            self.assertEqual(final_payload["change_mode"], "merge_request")
            self.assertTrue(final_payload.get("commit_sha"))
            self.assertTrue(final_payload.get("commit_url"))

            logs_resp = client.get(f"/tasks/{task_id}/logs?follow=0")
            self.assertEqual(logs_resp.status_code, 200)
            snapshot_payload = logs_resp.json()
            entries = snapshot_payload.get("entries", [])
            self.assertEqual(snapshot_payload.get("status"), "done")
            self.assertEqual(snapshot_payload.get("branch"), "feature/custom-branch")
            self.assertEqual(snapshot_payload.get("target_branch"), "main")
            self.assertEqual(snapshot_payload.get("change_mode"), "merge_request")
            self.assertEqual(snapshot_payload.get("codex_model"), chosen_model)
            self.assertEqual(snapshot_payload.get("codex_reasoning_effort"), "high")
            self.assertFalse(snapshot_payload.get("abort_requested", False))
            joined = "\n".join(entries)
            self.assertIn("Base branch: main", joined)
            self.assertIn("Using requested branch: feature/custom-branch", joined)
            self.assertIn(
                f"Codex model: {chosen_model} (reasoning effort: high)",
                joined,
            )
            self.assertIn("Change mode: merge_request", joined)
            self.assertIn("Merge request title: Phase 2 Custom Title", joined)

    def test_task_allows_target_branch_override(self) -> None:
        _, project_id = self._prepare_project()

        with TestClient(self.main.app) as client:
            task_resp = client.post(
                "/tasks",
                json={
                    "project_id": project_id,
                    "prompt": "Work off release branch",
                    "target_branch": "release",
                },
            )
            self.assertEqual(task_resp.status_code, 201, task_resp.text)
            task_id = task_resp.json()["id"]

            final_payload = None
            deadline = time.time() + 30
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
            self.assertEqual(final_payload["target_branch"], "release")
            self.assertTrue(final_payload["branch"].startswith("codex/task"))
            self.assertEqual(
                final_payload["mr_title"],
                _build_mr_title(task_id, "Work off release branch"),
            )
            self.assertEqual(final_payload["change_mode"], "merge_request")
            self.assertTrue(final_payload.get("commit_sha"))
            self.assertTrue(final_payload.get("commit_url"))

            logs_resp = client.get(f"/tasks/{task_id}/logs?follow=0")
            self.assertEqual(logs_resp.status_code, 200)
            snapshot_payload = logs_resp.json()
            entries = snapshot_payload.get("entries", [])
            self.assertEqual(snapshot_payload.get("target_branch"), "release")
            self.assertEqual(snapshot_payload.get("change_mode"), "merge_request")
            joined = "\n".join(entries)
            self.assertIn("Base branch override: release", joined)
            self.assertIn(
                f"Merge request title: {_build_mr_title(task_id, 'Work off release branch')}",
                joined,
            )
            self.assertIn("Change mode: merge_request", joined)

    def test_branch_commit_mode_creates_commit(self) -> None:
        _, project_id = self._prepare_project()

        with TestClient(self.main.app) as client:
            task_resp = client.post(
                "/tasks",
                json={
                    "project_id": project_id,
                    "prompt": "Update docs on existing branch",
                    "branch_name": "docs/improve-readme",
                    "change_mode": "branch_commit",
                    "mr_title": "Improve README guidance",
                },
            )
            self.assertEqual(task_resp.status_code, 201, task_resp.text)
            task_id = task_resp.json()["id"]

            deadline = time.time() + 30
            final_payload: dict | None = None
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
            self.assertEqual(final_payload["branch"], "docs/improve-readme")
            self.assertEqual(final_payload["change_mode"], "branch_commit")
            self.assertIsNone(final_payload.get("mr_url"))
            self.assertTrue(final_payload.get("commit_sha"))
            self.assertTrue(final_payload.get("commit_url"))

            logs_resp = client.get(f"/tasks/{task_id}/logs?follow=0")
            self.assertEqual(logs_resp.status_code, 200)
            snapshot_payload = logs_resp.json()
            entries = snapshot_payload.get("entries", [])
            self.assertEqual(snapshot_payload.get("change_mode"), "branch_commit")
            joined = "\n".join(entries)
            self.assertIn("Change mode: branch_commit", joined)
            self.assertIn("Commit pushed:", joined)

    def test_rejects_invalid_branch(self) -> None:
        _, project_id = self._prepare_project()

        with TestClient(self.main.app) as client:
            response = client.post(
                "/tasks",
                json={
                    "project_id": project_id,
                    "prompt": "Invalid branch",
                    "branch_name": "invalid branch name",
                },
            )
            self.assertEqual(response.status_code, 400)
            detail = response.json().get("detail")
            self.assertIn("Branch name", detail)

    def test_rejects_blank_mr_title(self) -> None:
        _, project_id = self._prepare_project()

        with TestClient(self.main.app) as client:
            response = client.post(
                "/tasks",
                json={
                    "project_id": project_id,
                    "prompt": "Missing title",
                    "mr_title": "   \n",
                },
            )
            self.assertEqual(response.status_code, 400)
            detail = response.json().get("detail", "")
            self.assertIn("Merge request title", detail)

    def test_rejects_long_mr_title(self) -> None:
        _, project_id = self._prepare_project()
        too_long = "x" * 241

        with TestClient(self.main.app) as client:
            response = client.post(
                "/tasks",
                json={
                    "project_id": project_id,
                    "prompt": "Title too long",
                    "mr_title": too_long,
                },
            )
            self.assertEqual(response.status_code, 400)
            detail = response.json().get("detail", "")
            self.assertIn("Merge request title", detail)

    def test_rejects_invalid_reasoning_effort(self) -> None:
        _, project_id = self._prepare_project()

        with TestClient(self.main.app) as client:
            response = client.post(
                "/tasks",
                json={
                    "project_id": project_id,
                    "prompt": "Invalid reasoning effort",
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
                    "codex_model": "totally-unknown",
                },
            )
            self.assertEqual(response.status_code, 400)
            detail = response.json().get("detail")
            self.assertIn("Codex model", detail)


if __name__ == "__main__":
    unittest.main()
