import shutil
import tempfile
import unittest
from pathlib import Path

from app.app.sanitizer import (
    LEGACY_SANITIZER_FILENAME,
    PRIMARY_SANITIZER_FILENAME,
    WORKSPACES_ROOT,
    load_sanitizer_patterns,
    sanitize_workspace,
)


class SanitizerFilenameTests(unittest.TestCase):
    def setUp(self) -> None:
        self.tmp_dir = tempfile.TemporaryDirectory()
        self.project_root = Path(self.tmp_dir.name)
        self.created_workspaces: list[int] = []

    def tearDown(self) -> None:
        for task_id in self.created_workspaces:
            shutil.rmtree(WORKSPACES_ROOT / str(task_id), ignore_errors=True)
        self.tmp_dir.cleanup()

    def _sanitize(self, task_id: int) -> Path:
        self.created_workspaces.append(task_id)
        return sanitize_workspace(self.project_root, task_id)

    def test_prefers_projectsanitize_when_both_exist(self) -> None:
        (self.project_root / "keepme.txt").write_text("data\n", encoding="utf-8")
        (self.project_root / "legacy-only.txt").write_text("legacy\n", encoding="utf-8")
        (self.project_root / PRIMARY_SANITIZER_FILENAME).write_text("keepme.txt\n", encoding="utf-8")
        (self.project_root / LEGACY_SANITIZER_FILENAME).write_text("legacy-only.txt\n", encoding="utf-8")

        workspace = self._sanitize(task_id=9042)
        self.assertFalse((workspace / "keepme.txt").exists(), ".projectsanitize entries should be applied")
        self.assertTrue(
            (workspace / "legacy-only.txt").exists(),
            "legacy file should be ignored when .projectsanitize is present",
        )

    def test_warns_and_uses_legacy_when_projectsanitize_missing(self) -> None:
        (self.project_root / "secret.txt").write_text("secret\n", encoding="utf-8")
        (self.project_root / LEGACY_SANITIZER_FILENAME).write_text("secret.txt\n", encoding="utf-8")

        with self.assertLogs("app.app.sanitizer", level="WARNING") as captured:
            patterns = load_sanitizer_patterns(self.project_root)
        joined = " ".join(captured.output)
        self.assertIn(".codexignore", joined)
        self.assertIn("secret.txt", patterns)

        workspace = self._sanitize(task_id=9043)
        self.assertFalse((workspace / "secret.txt").exists())


if __name__ == "__main__":
    unittest.main()
