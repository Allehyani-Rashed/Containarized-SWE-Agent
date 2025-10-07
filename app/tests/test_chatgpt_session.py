import json
import os
import sys
import tempfile
import unittest
from datetime import datetime, timedelta, timezone
from pathlib import Path

from fastapi.testclient import TestClient


class ChatGPTSessionTests(unittest.TestCase):
    def setUp(self) -> None:
        metrics_module = sys.modules.get("app.app.metrics")
        if metrics_module is not None:
            reset = getattr(metrics_module, "reset_metrics_registry", None)
            if callable(reset):
                reset()
        self.tmp_dir = tempfile.TemporaryDirectory()
        os.environ["APP_DATABASE_URL"] = f"sqlite:///{Path(self.tmp_dir.name) / 'session.db'}"
        os.environ["RUNNER_DISABLE_DOCKER"] = "1"
        for module in list(sys.modules.keys()):
            if module.startswith("app.app"):
                sys.modules.pop(module)
        from sqlmodel import SQLModel

        SQLModel.metadata.clear()
        from app.app import main as main_module
        from app.app import secrets

        secrets.reset_secret_manager()
        self.main = main_module
        self.secrets = secrets

    def tearDown(self) -> None:
        self.tmp_dir.cleanup()
        os.environ.pop("APP_DATABASE_URL", None)
        os.environ.pop("RUNNER_DISABLE_DOCKER", None)
        self.secrets.reset_secret_manager()

    def _build_session_bundle(self, expires_at: datetime) -> str:
        payload = {
            "session": {
                "session_token": "session-token-demo",
                "expires_at": expires_at.astimezone(timezone.utc).isoformat().replace("+00:00", "Z"),
            }
        }
        return json.dumps(payload)

    def test_import_session_updates_status(self) -> None:
        future = datetime.now(timezone.utc) + timedelta(days=1)
        bundle = self._build_session_bundle(future)

        with TestClient(self.main.app) as client:
            status_resp = client.get("/integrations/pat")
            self.assertEqual(status_resp.status_code, 200)
            initial = status_resp.json()
            self.assertFalse(initial.get("session_configured"))

            rotate_resp = client.post(
                "/integrations/pat/session",
                json={"bundle": bundle, "updated_by": "tester"},
            )
            self.assertEqual(rotate_resp.status_code, 200)
            rotated = rotate_resp.json()
            self.assertTrue(rotated.get("session_configured"))
            self.assertEqual(rotated.get("active_credential"), "session")
            self.assertEqual(rotated.get("session_updated_by"), "tester")

            status_after = client.get("/integrations/pat")
            self.assertEqual(status_after.status_code, 200)
            payload = status_after.json()
            self.assertTrue(payload.get("session_configured"))

            clear_resp = client.request(
                "DELETE",
                "/integrations/pat/session",
                json={"updated_by": "tester"},
            )
            self.assertEqual(clear_resp.status_code, 200)
            cleared = clear_resp.json()
            self.assertFalse(cleared.get("session_configured"))
            self.assertEqual(cleared.get("active_credential"), "none")

    def test_import_rejects_invalid_bundle(self) -> None:
        invalid_bundle = json.dumps({"foo": "bar"})
        with TestClient(self.main.app) as client:
            response = client.post(
                "/integrations/pat/session",
                json={"bundle": invalid_bundle},
            )
            self.assertEqual(response.status_code, 400)
            detail = response.json().get("detail")
            self.assertIn("Session bundle", detail)

    def test_import_rejects_expired_bundle(self) -> None:
        past = datetime.now(timezone.utc) - timedelta(days=1)
        bundle = self._build_session_bundle(past)
        with TestClient(self.main.app) as client:
            response = client.post(
                "/integrations/pat/session",
                json={"bundle": bundle},
            )
            self.assertEqual(response.status_code, 400)
            detail = response.json().get("detail", "")
            self.assertIn("expired", detail.lower())


if __name__ == "__main__":
    unittest.main()
