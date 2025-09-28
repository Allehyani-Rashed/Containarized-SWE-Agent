import importlib
import os
import subprocess
import sys
import tempfile
import time
import unittest
from pathlib import Path

from fastapi.testclient import TestClient


def _initialize_git_repo(path: Path) -> None:
    path.mkdir(parents=True, exist_ok=True)
    (path / "README.md").write_text("phase6 demo\n", encoding="utf-8")
    subprocess.run(["git", "init", "-b", "main"], cwd=path, check=True, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    subprocess.run(["git", "config", "user.email", "phase6@example.com"], cwd=path, check=True, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    subprocess.run(["git", "config", "user.name", "Codex Phase6"], cwd=path, check=True, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    subprocess.run(["git", "add", "."], cwd=path, check=True, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    subprocess.run(["git", "commit", "-m", "Initial commit"], cwd=path, check=True, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)


class Phase6AllowlistTests(unittest.TestCase):
    def setUp(self) -> None:
        self.tmp_dir = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp_dir.cleanup)
        os.environ["APP_DATABASE_URL"] = f"sqlite:///{Path(self.tmp_dir.name) / 'phase6.db'}"
        os.environ["RUNNER_DISABLE_DOCKER"] = "1"
        os.environ["RUNNER_GIT_DRY_RUN"] = "1"
        os.environ["SKIP_PROXY_RELOAD"] = "1"

        self.proxy_dir = Path(self.tmp_dir.name) / "proxy"
        self.filter_path = self.proxy_dir / "filter.list"

        self.proxy_dir.mkdir(parents=True, exist_ok=True)

        os.environ["PROXY_DIR"] = str(self.proxy_dir)

        if "app.app.allowlist" in sys.modules:
            self.allowlist = importlib.reload(sys.modules["app.app.allowlist"])
        else:
            self.allowlist = importlib.import_module("app.app.allowlist")

        self.original_proxy_dir = self.allowlist.PROXY_DIR
        self.original_filter_path = self.allowlist.GENERATED_FILTER_PATH

        for module_name in list(sys.modules.keys()):
            if module_name.startswith("app.app") and module_name != "app.app.allowlist":
                sys.modules.pop(module_name)

        from sqlmodel import SQLModel

        SQLModel.metadata.clear()
        from app.app import main as main_module

        self.main = main_module
        self.assertEqual(self.allowlist.PROXY_DIR, self.proxy_dir)
        self.assertEqual(self.allowlist.GENERATED_FILTER_PATH, self.filter_path)

    def tearDown(self) -> None:
        self.allowlist.PROXY_DIR = self.original_proxy_dir
        self.allowlist.GENERATED_FILTER_PATH = self.original_filter_path
        os.environ.pop("PROXY_DIR", None)
        os.environ.pop("APP_DATABASE_URL", None)
        os.environ.pop("RUNNER_DISABLE_DOCKER", None)
        os.environ.pop("RUNNER_GIT_DRY_RUN", None)
        os.environ.pop("SKIP_PROXY_RELOAD", None)

    def test_allowlist_normalization_and_filter_generation(self) -> None:
        project_root = Path(self.tmp_dir.name) / "phase6-project"
        _initialize_git_repo(project_root)

        with TestClient(self.main.app) as client:
            rotate_resp = client.post(
                "/integrations/pat",
                json={"token": "test-token"},
            )
            self.assertEqual(rotate_resp.status_code, 200)
            project_resp = client.post(
                "/projects",
                json={
                    "name": "phase6-demo",
                    "local_path": str(project_root),
                    "default_branch": "main",
                    "gitlab_host": "https://gitlab.example.com",
                    "gitlab_project_path": "example/demo",
                },
            )
            self.assertEqual(project_resp.status_code, 201)
            project_data = project_resp.json()

            task_resp = client.post(
                "/tasks",
                json={
                    "project_id": project_data["id"],
                    "prompt": "Test allowlist",
                    "allowlist": [" HTTPS://Example.org/path ", "registry.NPMJS.org"],
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
            self.assertEqual(
                final_payload["allowlist"],
                ["example.org", "registry.npmjs.org"],
            )

            snapshot_resp = client.get(f"/tasks/{task_id}/logs?follow=0")
            self.assertEqual(snapshot_resp.status_code, 200)
            snapshot_payload = snapshot_resp.json()
            entries = snapshot_payload.get("entries", [])
            self.assertEqual(snapshot_payload.get("status"), "done")
            self.assertFalse(snapshot_payload.get("abort_requested", False))

        effective_lines = [entry for entry in entries if "Effective allowlist" in entry]
        self.assertTrue(effective_lines, "Expected effective allowlist log entry")


        proxy_lines = [entry for entry in entries if "proxy: Proxy filter updated at" in entry]
        self.assertTrue(proxy_lines, "Expected proxy filter update log entry")
        logged_path = Path(proxy_lines[-1].split("proxy: Proxy filter updated at", 1)[1].strip())
        self.assertEqual(logged_path, self.filter_path)
        self.assertTrue(logged_path.exists(), "Proxy filter file should be generated")

        contents = [line.strip() for line in logged_path.read_text(encoding="utf-8").splitlines() if line and not line.startswith("#")]
        self.assertIn("gitlab.com", contents)
        self.assertIn("gitlab.example.com", contents)
        self.assertIn("example.org", contents)
        self.assertIn("registry.npmjs.org", contents)

    def test_normalize_user_allowlist_helper(self) -> None:
        raw_entries = [
            " HTTP://GitLab.com/",
            "example.org ",
            "",
            "   ",
            "EXAMPLE.ORG",
            "*.wild.example.com",
            ".subdomain.example.com",
        ]
        normalized = self.allowlist.normalize_user_allowlist(raw_entries)
        self.assertEqual(
            normalized,
            [
                "gitlab.com",
                "example.org",
                "*.wild.example.com",
                ".subdomain.example.com",
            ],
        )


if __name__ == "__main__":
    unittest.main()
