import os
import sys
import tempfile
import unittest
from pathlib import Path

from app.app.project_cache import project_cache_repo_path


class EnvSyncTests(unittest.TestCase):
    def setUp(self) -> None:
        self.tmp_dir = tempfile.TemporaryDirectory()
        db_path = Path(self.tmp_dir.name) / "env-sync.db"
        os.environ["APP_DATABASE_URL"] = f"sqlite:///{db_path}"
        os.environ["PROJECT_CACHE_ROOT"] = str(Path(self.tmp_dir.name) / "cache")
        self.previous_pat = os.environ.get("GITLAB_PAT")
        os.environ.pop("GITLAB_PAT", None)
        for module in list(sys.modules.keys()):
            if module.startswith("app.app"):
                sys.modules.pop(module)
        from sqlmodel import SQLModel

        SQLModel.metadata.clear()
        from app.app import env_sync as env_sync_module
        from app.app.database import engine, init_db

        init_db()
        self.env_sync = env_sync_module
        self.engine = engine

    def tearDown(self) -> None:
        self.tmp_dir.cleanup()
        os.environ.pop("APP_DATABASE_URL", None)
        os.environ.pop("PROJECT_CACHE_ROOT", None)
        if self.previous_pat is None:
            os.environ.pop("GITLAB_PAT", None)
        else:
            os.environ["GITLAB_PAT"] = self.previous_pat
        for module in list(sys.modules.keys()):
            if module.startswith("app.app"):
                sys.modules.pop(module)

    def test_sync_stores_pat_and_creates_project(self) -> None:
        config = self.env_sync.EnvConfig(
            gitlab_pat="glpat-test-token",
            project_name="demo",
            project_default_branch="main",
            gitlab_host="https://gitlab.example.com",
            gitlab_project_path="example/demo",
            session_bundle_path=None,
            session_bundle_json=None,
            actor="env-sync-tests",
        )
        result = self.env_sync.sync_credentials(config, repo_root=Path(self.tmp_dir.name))
        self.assertTrue(result.gitlab_pat_updated)
        self.assertTrue(result.project_created)
        self.assertIsNotNone(result.project_id)
        self.assertIsNone(result.session_bundle_error)
        self.assertEqual(os.environ.get("GITLAB_PAT"), "glpat-test-token")

        from sqlmodel import Session, select
        from app.app.integrations import GITLAB_PAT_KIND
        from app.app.models import IntegrationCredential, Project

        with Session(self.engine) as session:
            credential = session.exec(
                select(IntegrationCredential).where(IntegrationCredential.kind == GITLAB_PAT_KIND)
            ).one()
            self.assertIsNotNone(credential.token_encrypted)

            project = session.get(Project, result.project_id)
            assert project is not None
            expected_path = project_cache_repo_path("https://gitlab.example.com", "example/demo")
            computed_path = project_cache_repo_path(project.gitlab_host, project.gitlab_project_path)
            self.assertEqual(computed_path, expected_path)

    def test_parse_env_file_handles_quotes(self) -> None:
        env_file = Path(self.tmp_dir.name) / "sample.env"
        env_file.write_text(
            """
            # comment line
            export GITLAB_PAT='quoted-token'
            PROJECT_NAME=Demo Project

            """,
            encoding="utf-8",
        )

        values = self.env_sync.parse_env_file(env_file)
        self.assertEqual(values["GITLAB_PAT"], "quoted-token")
        self.assertEqual(values["PROJECT_NAME"], "Demo Project")

    def test_missing_session_bundle_allows_pat_sync(self) -> None:
        config = self.env_sync.EnvConfig(
            gitlab_pat="glpat-missing-session",
            project_name=None,
            project_default_branch=None,
            gitlab_host=None,
            gitlab_project_path=None,
            session_bundle_path=Path(self.tmp_dir.name) / "absent.json",
            session_bundle_json=None,
            actor="env-sync-tests",
        )
        result = self.env_sync.sync_credentials(config, repo_root=Path(self.tmp_dir.name))
        self.assertTrue(result.gitlab_pat_updated)
        self.assertFalse(result.session_bundle_updated)
        self.assertIsNotNone(result.session_bundle_error)

        from sqlmodel import Session, select
        from app.app.integrations import GITLAB_PAT_KIND
        from app.app.models import IntegrationCredential

        with Session(self.engine) as session:
            credential = session.exec(
                select(IntegrationCredential).where(IntegrationCredential.kind == GITLAB_PAT_KIND)
            ).one()
            self.assertIsNotNone(credential.token_encrypted)

    def test_session_bundle_loaded_from_path(self) -> None:
        bundle_path = Path(self.tmp_dir.name) / "chatgpt.json"
        bundle_path.write_text('{"session_token": "token-123"}', encoding="utf-8")
        config = self.env_sync.EnvConfig(
            gitlab_pat=None,
            project_name=None,
            project_default_branch=None,
            gitlab_host=None,
            gitlab_project_path=None,
            session_bundle_path=bundle_path,
            session_bundle_json=None,
            actor="env-sync-tests",
        )
        result = self.env_sync.sync_credentials(config, repo_root=Path(self.tmp_dir.name))
        self.assertTrue(result.session_bundle_updated)
        self.assertIsNone(result.session_bundle_error)

        from sqlmodel import Session
        from app.app.integrations import get_chatgpt_session_bundle

        with Session(self.engine) as session:
            material = get_chatgpt_session_bundle(session)
            assert material is not None
            self.assertEqual(material.raw, '{"session_token": "token-123"}')


if __name__ == "__main__":  # pragma: no cover
    unittest.main()
