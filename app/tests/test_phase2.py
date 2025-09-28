import os
import shutil
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


class Phase2SanitizeTests(unittest.TestCase):
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

    def _build_sample_project(self) -> Path:
        project_root = Path(self.tmp_dir.name) / "demo-project"
        project_root.mkdir(parents=True, exist_ok=True)
        (project_root / "README.md").write_text("demo project\n", encoding="utf-8")
        (project_root / "codex.txt").write_text("codex content\n", encoding="utf-8")

        (project_root / ".gitignore").write_text("app/build/\n", encoding="utf-8")

        app_dir = project_root / "app"
        app_dir.mkdir(parents=True, exist_ok=True)
        (app_dir / "MainActivity.kt").write_text("// demo\n", encoding="utf-8")

        build_dir = app_dir / "build" / "outputs"
        build_dir.mkdir(parents=True, exist_ok=True)
        (build_dir / "demo.apk").write_text("apk\n", encoding="utf-8")
        intermediates_dir = app_dir / "build" / "intermediates" / "res"
        intermediates_dir.mkdir(parents=True, exist_ok=True)
        (intermediates_dir / "values.xml").write_text("<resources/>\n", encoding="utf-8")

        (project_root / ".env").write_text("SECRET=top-secret\n", encoding="utf-8")
        node_modules = project_root / "node_modules" / "pkg"
        node_modules.mkdir(parents=True, exist_ok=True)
        (node_modules / "index.js").write_text("console.log('ignore');\n", encoding="utf-8")

        logs_dir = project_root / "logs"
        logs_dir.mkdir(parents=True, exist_ok=True)
        (logs_dir / "run.log").write_text("nothing to see\n", encoding="utf-8")

        aws_dir = project_root / ".aws"
        aws_dir.mkdir(parents=True, exist_ok=True)
        (aws_dir / "credentials").write_text("[default]\naws_access_key_id=DEMO\n", encoding="utf-8")

        gradle_cache = project_root / ".gradle" / "caches"
        gradle_cache.mkdir(parents=True, exist_ok=True)
        (gradle_cache / "build-cache.bin").write_bytes(b"cache")

        _initialize_git_repo(project_root)
        return project_root

    def test_sanitized_workspace_excludes_sensitive_content(self) -> None:
        project_root = self._build_sample_project()
        expected_workspace_parent = Path(self.main.__file__).resolve().parents[2] / "workspaces"

        sanitized_root: Path | None = None

        with TestClient(self.main.app) as client:
            rotate_resp = client.post(
                "/integrations/pat",
                json={"token": "test-token"},
            )
            self.assertEqual(rotate_resp.status_code, 200)

            project_payload = {
                "name": "demo-phase2",
                "local_path": str(project_root),
                "default_branch": "main",
                "gitlab_host": "https://gitlab.example.com",
                "gitlab_project_path": "example/demo",
            }
            project_resp = client.post("/projects", json=project_payload)
            self.assertEqual(project_resp.status_code, 201)
            project_data = project_resp.json()
            self.assertIn("codex_token_configured", project_data)
            self.assertFalse(project_data["codex_token_configured"])

            task_resp = client.post(
                "/tasks",
                json={
                    "project_id": project_data["id"],
                    "prompt": "Sanitize the workspace",
                },
            )
            self.assertEqual(task_resp.status_code, 201)
            task_data = task_resp.json()
            task_id = task_data["id"]

            deadline = time.time() + 10
            final_payload = None
            while time.time() < deadline:
                detail_resp = client.get(f"/tasks/{task_id}")
                self.assertEqual(detail_resp.status_code, 200)
                final_payload = detail_resp.json()
                if final_payload["status"] in {"done", "failed"}:
                    break
                time.sleep(0.25)

            self.assertIsNotNone(final_payload, "Expected task detail payload")
            self.assertEqual(final_payload["status"], "done", "Task did not succeed")
            workspace_path = final_payload.get("workspace_path")
            self.assertIsNotNone(workspace_path, "Workspace path should be persisted")

            sanitized_root = Path(workspace_path)
            self.assertTrue(sanitized_root.exists(), "Sanitized workspace missing")
            self.assertTrue(sanitized_root.is_dir(), "Workspace path is not a directory")
            expected_safe_dir = expected_workspace_parent / str(task_id) / "safe"
            self.assertEqual(sanitized_root, expected_safe_dir)

            # Expected files are copied
            self.assertTrue((sanitized_root / "README.md").exists())
            self.assertTrue((sanitized_root / "codex.txt").exists())
            self.assertTrue((sanitized_root / ".git" / "config").exists())

            # Secret and bulky directories are excluded
            self.assertFalse((sanitized_root / ".env").exists())
            self.assertFalse((sanitized_root / "node_modules").exists())
            self.assertFalse((sanitized_root / "logs").exists())
            self.assertFalse((sanitized_root / ".aws").exists())
            self.assertFalse((sanitized_root / "app" / "build").exists())
            self.assertFalse((sanitized_root / "app" / "build" / "intermediates").exists())
            self.assertFalse((sanitized_root / ".gradle").exists())

            # Logs mention the sanitized workspace
            snapshot = client.get(f"/tasks/{task_id}/logs?follow=0")
            self.assertEqual(snapshot.status_code, 200)
            snapshot_payload = snapshot.json()
            entries = snapshot_payload.get("entries", [])
            self.assertEqual(snapshot_payload.get("status"), "done")
            self.assertFalse(snapshot_payload.get("abort_requested", False))
            self.assertTrue(
                any("Workspace ready" in entry for entry in entries),
                "Expected workspace sanitization log entry",
            )

        # Cleanup sanitized workspace artefacts
        if sanitized_root is not None:
            shutil.rmtree(sanitized_root.parent, ignore_errors=True)


if __name__ == "__main__":
    unittest.main()
