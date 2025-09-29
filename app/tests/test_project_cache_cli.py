import base64
import os
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock


class ProjectCacheScriptTests(unittest.TestCase):
    def setUp(self) -> None:
        self.tmp_dir = tempfile.TemporaryDirectory()
        db_path = Path(self.tmp_dir.name) / "cache-script.db"
        os.environ["APP_DATABASE_URL"] = f"sqlite:///{db_path}"
        os.environ["APP_SECRET_KEY"] = base64.urlsafe_b64encode(
            b"env-sync-secret-key-32-bytes-ABC",
        ).decode()
        os.environ["PROJECT_CACHE_ROOT"] = str(Path(self.tmp_dir.name) / "cache")

        for module in list(sys.modules.keys()):
            if module.startswith("app.app"):
                sys.modules.pop(module)
        sys.modules.pop("scripts.project_cache", None)

        from sqlmodel import SQLModel

        SQLModel.metadata.clear()
        from app.app.database import engine, init_db

        init_db()
        self.engine = engine

    def tearDown(self) -> None:
        self.tmp_dir.cleanup()
        os.environ.pop("APP_DATABASE_URL", None)
        os.environ.pop("APP_SECRET_KEY", None)
        os.environ.pop("PROJECT_CACHE_ROOT", None)
        for module in list(sys.modules.keys()):
            if module.startswith("app.app"):
                sys.modules.pop(module)
        sys.modules.pop("scripts.project_cache", None)

    def _store_pat(self, token: str = "glpat-test-token") -> None:
        from sqlmodel import Session
        from app.app.integrations import set_gitlab_pat_token

        with Session(self.engine) as session:
            set_gitlab_pat_token(session, token, "tests")
            session.commit()

    def _create_project(
        self,
        *,
        slug: str = "example/demo",
        gitlab_token: str | None = None,
        ensure_repo_dir: bool = True,
    ):
        from sqlmodel import Session
        from app.app.models import Project
        from app.app.project_cache import project_cache_repo_path

        host = "https://gitlab.example.com"
        cache_path = project_cache_repo_path(host, slug)
        if ensure_repo_dir:
            cache_path.mkdir(parents=True, exist_ok=True)
        with Session(self.engine) as session:
            project = Project(
                name=slug.split("/")[-1],
                default_branch="main",
                gitlab_host=host,
                gitlab_project_path=slug,
                gitlab_token=gitlab_token,
            )
            session.add(project)
            session.commit()
            session.refresh(project)
            return project

    def test_refresh_all_projects_uses_global_pat(self) -> None:
        self._store_pat()
        project = self._create_project()

        from scripts import project_cache as cli

        with mock.patch.object(cli, "_refresh_single_project", return_value=True) as mock_refresh:
            exit_code = cli.main(["--refresh", "--project-id", str(project.id)])

        self.assertEqual(exit_code, 0)
        mock_refresh.assert_called_once()
        args, kwargs = mock_refresh.call_args
        self.assertEqual(args[0].id, project.id)
        self.assertEqual(kwargs["gitlab_pat"], "glpat-test-token")
        self.assertFalse(kwargs["dry_run"])
        self.assertFalse(kwargs["force"])

    def test_bootstrap_all_projects_uses_global_pat(self) -> None:
        self._store_pat()
        project = self._create_project(ensure_repo_dir=False)

        from scripts import project_cache as cli

        with mock.patch.object(cli, "_bootstrap_single_project", return_value=True) as mock_bootstrap:
            exit_code = cli.main(["--bootstrap", "--project-id", str(project.id)])

        self.assertEqual(exit_code, 0)
        mock_bootstrap.assert_called_once()
        args, kwargs = mock_bootstrap.call_args
        self.assertEqual(args[0].id, project.id)
        self.assertEqual(kwargs["gitlab_pat"], "glpat-test-token")
        self.assertFalse(kwargs["dry_run"])

    def test_refresh_falls_back_to_project_token(self) -> None:
        project = self._create_project(gitlab_token="project-specific-token")

        from scripts import project_cache as cli

        with mock.patch.object(cli, "refresh_project_cache", return_value="abc123") as mock_refresh, mock.patch.object(
            cli,
            "enforce_cache_policy",
        ) as mock_policy, mock.patch.object(cli, "snapshot_project_cache", return_value=None) as mock_snapshot:
            succeeded = cli._refresh_single_project(project, gitlab_pat=None, dry_run=False, force=False)

        self.assertTrue(succeeded)
        mock_refresh.assert_called_once()
        mock_policy.assert_called_once()
        mock_snapshot.assert_called_once()
        args, kwargs = mock_refresh.call_args
        from app.app.project_cache import project_cache_repo_path

        expected_path = project_cache_repo_path(project.gitlab_host, project.gitlab_project_path)
        self.assertEqual(Path(args[0]).resolve(), expected_path.resolve())
        self.assertEqual(args[1], "main")
        self.assertEqual(kwargs["gitlab_token"], "project-specific-token")
        self.assertIn("project_identifier", kwargs)

    def test_bootstrap_falls_back_to_project_token(self) -> None:
        project = self._create_project(gitlab_token="project-specific-token", ensure_repo_dir=False)

        from scripts import project_cache as cli

        with mock.patch.object(cli, "bootstrap_project_cache") as mock_bootstrap:
            succeeded = cli._bootstrap_single_project(project, gitlab_pat=None, dry_run=False)

        self.assertTrue(succeeded)
        args, kwargs = mock_bootstrap.call_args
        from app.app.project_cache import project_cache_repo_path

        expected_path = project_cache_repo_path(project.gitlab_host, project.gitlab_project_path)
        self.assertEqual(Path(args[0]).resolve(), expected_path.resolve())
        self.assertEqual(kwargs["gitlab_token"], "project-specific-token")

    def test_refresh_single_project_requires_credentials(self) -> None:
        project = self._create_project()

        from scripts import project_cache as cli

        with mock.patch.object(cli, "refresh_project_cache") as mock_refresh:
            succeeded = cli._refresh_single_project(project, gitlab_pat=None, dry_run=False, force=False)

        self.assertFalse(succeeded)
        mock_refresh.assert_not_called()

    def test_refresh_honours_dry_run_flag(self) -> None:
        self._store_pat()
        project = self._create_project(slug="example/dry-run")

        from scripts import project_cache as cli

        with mock.patch.object(cli, "_refresh_single_project", return_value=True) as mock_refresh:
            exit_code = cli.main(["--refresh", "--dry-run", "--project-id", str(project.id)])

        self.assertEqual(exit_code, 0)
        mock_refresh.assert_called_once()
        _, kwargs = mock_refresh.call_args
        self.assertTrue(kwargs["dry_run"])
        self.assertEqual(kwargs["gitlab_pat"], "glpat-test-token")
        self.assertFalse(kwargs["force"])

    def test_bootstrap_skips_refresh_when_bootstrap_fails(self) -> None:
        self._store_pat()
        project = self._create_project(ensure_repo_dir=False)

        from scripts import project_cache as cli

        with mock.patch.object(cli, "_bootstrap_single_project", return_value=False) as mock_bootstrap, mock.patch.object(
            cli,
            "_refresh_single_project",
        ) as mock_refresh:
            exit_code = cli.main(["--bootstrap", "--refresh", "--project-id", str(project.id)])

        self.assertEqual(exit_code, 1)
        mock_bootstrap.assert_called_once()
        mock_refresh.assert_not_called()

    def test_main_returns_failure_when_refresh_fails(self) -> None:
        self._store_pat()
        project = self._create_project(slug="example/failure")

        from scripts import project_cache as cli

        with mock.patch.object(cli, "_refresh_single_project", return_value=False):
            exit_code = cli.main(["--refresh", "--project-id", str(project.id)])

        self.assertEqual(exit_code, 1)

    def test_bootstrap_single_project_requires_credentials(self) -> None:
        project = self._create_project(ensure_repo_dir=False)

        from scripts import project_cache as cli

        with mock.patch.object(cli, "bootstrap_project_cache"):
            succeeded = cli._bootstrap_single_project(project, gitlab_pat=None, dry_run=False)

        self.assertFalse(succeeded)

    def test_bootstrap_honours_dry_run_flag_without_credentials(self) -> None:
        project = self._create_project(ensure_repo_dir=False)

        from scripts import project_cache as cli

        with mock.patch.object(cli, "bootstrap_project_cache") as mock_bootstrap:
            succeeded = cli._bootstrap_single_project(project, gitlab_pat=None, dry_run=True)

        self.assertTrue(succeeded)
        mock_bootstrap.assert_called_once()


if __name__ == "__main__":  # pragma: no cover
    unittest.main()
