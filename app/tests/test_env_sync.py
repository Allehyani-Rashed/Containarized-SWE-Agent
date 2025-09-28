import base64
import os
import sys
import tempfile
import unittest
from pathlib import Path


class EnvSyncTests(unittest.TestCase):
    def setUp(self) -> None:
        self.tmp_dir = tempfile.TemporaryDirectory()
        db_path = Path(self.tmp_dir.name) / "env-sync.db"
        os.environ["APP_DATABASE_URL"] = f"sqlite:///{db_path}"
        os.environ["APP_SECRET_KEY"] = base64.urlsafe_b64encode(b"env-sync-secret-key-32-bytes-ABC").decode()
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
        os.environ.pop("APP_SECRET_KEY", None)
        for module in list(sys.modules.keys()):
            if module.startswith("app.app"):
                sys.modules.pop(module)

    def test_sync_stores_pat_and_codex_token(self) -> None:
        config = self.env_sync.EnvConfig(
            gitlab_pat="glpat-test-token",
            codex_token="sk-test-token",
            project_name="demo",
            project_local_path=str(Path(self.tmp_dir.name) / "project"),
            project_default_branch="main",
            gitlab_host="https://gitlab.example.com",
            gitlab_project_path="example/demo",
            session_bundle_path=None,
            session_bundle_inline=None,
            actor="env-sync-tests",
        )
        result = self.env_sync.sync_credentials(config, repo_root=Path(self.tmp_dir.name))
        self.assertTrue(result.gitlab_pat_updated)
        self.assertTrue(result.project_created)
        self.assertTrue(result.codex_token_updated)
        self.assertIsNotNone(result.project_id)

        from sqlmodel import Session, select
        from app.app.integrations import GITLAB_PAT_KIND
        from app.app.models import IntegrationCredential, Project
        from app.app.secrets import get_secret_manager

        with Session(self.engine) as session:
            credential = session.exec(
                select(IntegrationCredential).where(IntegrationCredential.kind == GITLAB_PAT_KIND)
            ).one()
            self.assertIsNotNone(credential.token_encrypted)

            project = session.get(Project, result.project_id)
            assert project is not None
            self.assertIsNotNone(project.codex_token_encrypted)
            manager = get_secret_manager()
            decrypted = manager.decrypt(project.codex_token_encrypted)
            self.assertEqual(decrypted, "sk-test-token")

    def test_parse_env_file_handles_quotes(self) -> None:
        env_file = Path(self.tmp_dir.name) / "sample.env"
        env_file.write_text(
            """
            # comment line
            export GITLAB_PAT='quoted-token'
            CODEX_ACCESS_TOKEN="quoted-sk"
            PROJECT_NAME=Demo Project
            
            """,
            encoding="utf-8",
        )

        values = self.env_sync.parse_env_file(env_file)
        self.assertEqual(values["GITLAB_PAT"], "quoted-token")
        self.assertEqual(values["CODEX_ACCESS_TOKEN"], "quoted-sk")
        self.assertEqual(values["PROJECT_NAME"], "Demo Project")

    def test_session_bundle_loaded_from_path(self) -> None:
        bundle_path = Path(self.tmp_dir.name) / "chatgpt.json"
        bundle_path.write_text('{"session_token": "token-123"}', encoding="utf-8")
        config = self.env_sync.EnvConfig(
            gitlab_pat=None,
            codex_token=None,
            project_name=None,
            project_local_path=None,
            project_default_branch=None,
            gitlab_host=None,
            gitlab_project_path=None,
            session_bundle_path=bundle_path,
            session_bundle_inline=None,
            actor="env-sync-tests",
        )
        result = self.env_sync.sync_credentials(config, repo_root=Path(self.tmp_dir.name))
        self.assertTrue(result.session_bundle_updated)

        from sqlmodel import Session
        from app.app.integrations import get_chatgpt_session_bundle

        with Session(self.engine) as session:
            material = get_chatgpt_session_bundle(session)
            assert material is not None
            self.assertEqual(material.raw, '{"session_token": "token-123"}')

    def test_sync_from_env_file_with_inline_session(self) -> None:
        env_file = Path(self.tmp_dir.name) / ".env"
        inline_bundle = '{"session_token":"inline-token"}'
        env_file.write_text(
            "\n".join(
                [
                    "APP_SECRET_KEY="
                    + base64.urlsafe_b64encode(b"env-sync-secret-key-32-bytes-ABC").decode(),
                    f"CHATGPT_SESSION_JSON='{inline_bundle}'",
                ]
            ),
            encoding="utf-8",
        )

        result = self.env_sync.sync_credentials_from_env_file(
            env_file,
            actor="env-sync-tests",
            repo_root=Path(self.tmp_dir.name),
        )

        self.assertIsNotNone(result)
        assert result is not None
        self.assertTrue(result.session_bundle_updated)

        from sqlmodel import Session
        from app.app.integrations import get_chatgpt_session_bundle

        with Session(self.engine) as session:
            material = get_chatgpt_session_bundle(session)
            assert material is not None
            self.assertEqual(material.raw, inline_bundle)


if __name__ == "__main__":  # pragma: no cover
    unittest.main()
