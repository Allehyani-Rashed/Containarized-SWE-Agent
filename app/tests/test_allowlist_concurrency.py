import importlib.util
import os
import sys
import tempfile
import unittest
from pathlib import Path


class AllowlistConcurrencyTests(unittest.TestCase):
    def setUp(self) -> None:
        self.tmp_dir = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp_dir.cleanup)
        proxy_dir = Path(self.tmp_dir.name) / "proxy"
        proxy_dir.mkdir(parents=True, exist_ok=True)
        os.environ["PROXY_DIR"] = str(proxy_dir)
        os.environ["SKIP_PROXY_RELOAD"] = "1"

        module_path = Path(__file__).resolve().parents[1] / "app" / "allowlist.py"
        self.module_name = f"allowlist_test_module_{id(self)}"
        spec = importlib.util.spec_from_file_location(self.module_name, module_path)
        if spec is None or spec.loader is None:
            raise RuntimeError("Unable to load allowlist module for testing")
        module = importlib.util.module_from_spec(spec)
        sys.modules[self.module_name] = module
        spec.loader.exec_module(module)
        self.allowlist = module
        self.filter_path = module.GENERATED_FILTER_PATH

    def tearDown(self) -> None:
        os.environ.pop("PROXY_DIR", None)
        os.environ.pop("SKIP_PROXY_RELOAD", None)
        if hasattr(self, "module_name"):
            sys.modules.pop(self.module_name, None)

    def _read_entries(self) -> list[str]:
        if not self.filter_path.exists():
            return []
        return [
            line.strip()
            for line in self.filter_path.read_text(encoding="utf-8").splitlines()
            if line.strip() and not line.startswith("#")
        ]

    def test_union_and_cleanup_across_tasks(self) -> None:
        self.allowlist.apply_project_allowlist(
            task_id=1,
            project_host="https://gitlab.alpha.example",
            extras=["api.alpha.example"],
        )
        self.allowlist.apply_project_allowlist(
            task_id=2,
            project_host="https://gitlab.beta.example",
            extras=["api.beta.example"],
        )

        combined_entries = self._read_entries()
        self.assertIn("gitlab.alpha.example", combined_entries)
        self.assertIn("gitlab.beta.example", combined_entries)
        self.assertIn("api.alpha.example", combined_entries)
        self.assertIn("api.beta.example", combined_entries)

        self.allowlist.clear_task_allowlist(1)
        remaining_entries = self._read_entries()
        self.assertNotIn("gitlab.alpha.example", remaining_entries)
        self.assertNotIn("api.alpha.example", remaining_entries)
        self.assertIn("gitlab.beta.example", remaining_entries)
        self.assertIn("api.beta.example", remaining_entries)

        self.allowlist.clear_task_allowlist(2)
        base_entries = self._read_entries()
        self.assertIn("gitlab.com", base_entries)
        self.assertNotIn("gitlab.alpha.example", base_entries)
        self.assertNotIn("gitlab.beta.example", base_entries)


if __name__ == "__main__":
    unittest.main()
