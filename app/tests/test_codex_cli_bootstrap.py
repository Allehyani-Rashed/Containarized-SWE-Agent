import io
import json
from contextlib import redirect_stderr, redirect_stdout
from pathlib import Path
from importlib.machinery import SourceFileLoader
from types import ModuleType, SimpleNamespace
from typing import Any, Dict, List, Optional, Tuple
import unittest
from unittest import mock

# Load the scripts/codex module without requiring it to be on sys.path.
REPO_ROOT = Path(__file__).resolve().parents[2]
CODEX_PATH = REPO_ROOT / "scripts" / "codex"
_loader = SourceFileLoader("codex_cli", str(CODEX_PATH))
codex = ModuleType(_loader.name)
_loader.exec_module(codex)


class CodexProjectsBootstrapTests(unittest.TestCase):
    def _make_args(
        self,
        *,
        actor: Optional[str] = "cli-tester",
        gitlab_pat: Optional[str] = None,
        project_pat: Optional[str] = None,
        session_bundle: Optional[str] = None,
        allowlist: Optional[List[str]] = None,
        project_name: str = "Demo Project",
        gitlab_host: str = "https://gitlab.example.com",
        project_path: str = "example/demo",
        default_branch: str = "main",
    ) -> SimpleNamespace:
        return SimpleNamespace(
            api_base="http://api.local",
            actor=actor,
            gitlab_pat=gitlab_pat,
            project_pat=project_pat,
            session_bundle_path=None,
            session_bundle=session_bundle,
            project_name=project_name,
            gitlab_host=gitlab_host,
            project_path=project_path,
            default_branch=default_branch,
            allowlist=allowlist,
            json=True,
            ui_base_url=None,
        )

    def test_bootstrap_creates_project_and_credentials(self) -> None:
        call_log: List[Tuple[str, str, Optional[Dict[str, Any]]]] = []
        created_project: Dict[str, Any] = {}

        def fake_api_request(
            api_base: str,
            method: str,
            path: str,
            payload: Optional[Dict[str, Any]] = None,
        ) -> Any:
            call_log.append((method, path, payload))
            self.assertEqual(api_base, "http://api.local")

            if method == "POST" and path == "/integrations/pat":
                assert payload is not None
                self.assertEqual(payload.get("token"), "glpat-test-token")
                return {"configured": True, "session_configured": False}

            if method == "POST" and path == "/integrations/pat/session":
                assert payload is not None
                self.assertEqual(payload.get("bundle"), '{"session_token":"bundle"}')
                return {"configured": True, "session_configured": True}

            if method == "GET" and path == "/projects":
                return []

            if method == "POST" and path == "/projects":
                assert payload is not None
                self.assertEqual(payload.get("name"), "Demo Project")
                self.assertEqual(payload.get("allowlist"), ["example.com"])
                created_project.update({"id": 42, **payload})
                return created_project

            if method == "GET" and path == "/projects/42":
                return created_project

            self.fail(f"Unexpected API call: {method} {path}")

        args = self._make_args(
            gitlab_pat="glpat-test-token",
            session_bundle='{"session_token":"bundle"}',
            allowlist=["example.com"],
        )

        stdout = io.StringIO()
        stderr = io.StringIO()
        with mock.patch.object(codex, "_api_request", side_effect=fake_api_request):
            with redirect_stdout(stdout), redirect_stderr(stderr):
                exit_code = codex.projects_bootstrap(args)

        self.assertEqual(exit_code, 0)
        self.assertEqual(stderr.getvalue(), "")
        result = json.loads(stdout.getvalue())

        self.assertEqual(result["project"]["id"], 42)
        self.assertEqual(result["project"]["allowlist"], ["example.com"])
        self.assertTrue(result["pat"]["configured"])
        self.assertTrue(result["pat"]["session_configured"])
        self.assertEqual(result["allowlist"], ["example.com"])

        sequence = [(method, path) for method, path, _ in call_log]
        self.assertEqual(
            sequence,
            [
                ("POST", "/integrations/pat"),
                ("POST", "/integrations/pat/session"),
                ("GET", "/projects"),
                ("POST", "/projects"),
                ("GET", "/projects/42"),
            ],
        )

    def test_bootstrap_updates_existing_project(self) -> None:
        call_log: List[Tuple[str, str, Optional[Dict[str, Any]]]] = []
        existing_project = {
            "id": 7,
            "name": "Demo Project",
            "default_branch": "main",
            "gitlab_host": "https://gitlab.example.com",
            "gitlab_project_path": "example/demo",
            "allowlist": ["github.com"],
        }
        patched_project: Dict[str, Any] = {}

        def fake_api_request(
            api_base: str,
            method: str,
            path: str,
            payload: Optional[Dict[str, Any]] = None,
        ) -> Any:
            call_log.append((method, path, payload))
            self.assertEqual(api_base, "http://api.local")

            if method == "GET" and path == "/integrations/pat":
                return {"configured": True, "session_configured": True}

            if method == "GET" and path == "/projects":
                return [existing_project]

            if method == "PATCH" and path == "/projects/7":
                assert payload is not None
                self.assertEqual(payload.get("allowlist"), ["pypi.org"])
                self.assertEqual(payload.get("actor"), "cli-update")
                patched_project.update({**existing_project, "allowlist": ["pypi.org"]})
                return patched_project

            if method == "GET" and path == "/projects/7":
                return patched_project or existing_project

            self.fail(f"Unexpected API call: {method} {path}")

        args = self._make_args(
            actor="cli-update",
            gitlab_pat=None,
            allowlist=["pypi.org"],
        )

        stdout = io.StringIO()
        stderr = io.StringIO()
        with mock.patch.object(codex, "_api_request", side_effect=fake_api_request):
            with redirect_stdout(stdout), redirect_stderr(stderr):
                exit_code = codex.projects_bootstrap(args)

        self.assertEqual(exit_code, 0)
        self.assertEqual(stderr.getvalue(), "")
        payload = json.loads(stdout.getvalue())

        self.assertEqual(payload["project"]["id"], 7)
        self.assertEqual(payload["project"]["allowlist"], ["pypi.org"])
        self.assertTrue(payload["pat"]["configured"])
        self.assertEqual(payload["allowlist"], ["pypi.org"])

        sequence = [(method, path) for method, path, _ in call_log]
        self.assertEqual(
            sequence,
            [
                ("GET", "/integrations/pat"),
                ("GET", "/projects"),
                ("PATCH", "/projects/7"),
                ("GET", "/projects/7"),
            ],
        )


if __name__ == "__main__":  # pragma: no cover
    unittest.main()
