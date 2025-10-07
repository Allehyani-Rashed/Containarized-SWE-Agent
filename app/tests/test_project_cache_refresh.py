import json
import os
import shutil
import subprocess
import tempfile
import threading
import time
import unittest
from pathlib import Path
from typing import Callable
from unittest import mock

from app.app.project_cache import (
    BreakoutEvent,
    ProjectCacheCallbacks,
    ProjectCacheError,
    ProjectCacheService,
)
from app.app.project_cache import git_ops as project_cache_git_ops
from app.app.project_cache import locking as cache_locking
from app.app.project_cache import sentinel as project_cache_sentinel


def _run(cmd: list[str], *, cwd: Path | None = None) -> None:
    subprocess.run(cmd, cwd=str(cwd) if cwd is not None else None, check=True, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)


class RefreshProjectCacheTests(unittest.TestCase):
    def setUp(self) -> None:
        self.tmp_dir = tempfile.TemporaryDirectory()
        self.tmp_path = Path(self.tmp_dir.name)
        self.cache_root = self.tmp_path / "cache-root"
        self.gitlab_host = "gitlab.example.com"
        self.project_path = "codex/test"
        self.service = ProjectCacheService(cache_root=self.cache_root)
        self.callbacks_events: list[BreakoutEvent] = []
        self.service_with_callbacks = ProjectCacheService(
            cache_root=self.cache_root,
            callbacks=ProjectCacheCallbacks(on_breakout_detected=self.callbacks_events.append),
        )

    def tearDown(self) -> None:
        self.tmp_dir.cleanup()

    def _initialize_cache_repo(self) -> tuple[Path, Path]:
        remote_path = self.tmp_path / "remote.git"
        _run(["git", "init", "--bare", "--initial-branch", "main", str(remote_path)])

        cache_path = self.service.repo_path_for(self.gitlab_host, self.project_path)
        if cache_path.exists():
            shutil.rmtree(cache_path)
        cache_path.parent.mkdir(parents=True, exist_ok=True)
        _run(["git", "clone", str(remote_path), str(cache_path)])
        _run(["git", "config", "user.email", "tester@example.com"], cwd=cache_path)
        _run(["git", "config", "user.name", "Cache Tester"], cwd=cache_path)
        (cache_path / "README.md").write_text("initial\n", encoding="utf-8")
        _run(["git", "add", "README.md"], cwd=cache_path)
        _run(["git", "commit", "-m", "Initial commit"], cwd=cache_path)
        _run(["git", "push", "-u", "origin", "main"], cwd=cache_path)
        # Ensure breakout sentinel is seeded for service operations
        self.service.bootstrap(
            gitlab_host=self.gitlab_host,
            project_path=self.project_path,
            default_branch="main",
            dry_run=True,
        )
        return remote_path, cache_path

    def _refresh(
        self,
        *,
        dry_run: bool = False,
        force: bool = False,
        gitlab_token: str | None = None,
        service: ProjectCacheService | None = None,
        log_fn: Callable[[str], None] | None = None,
    ) -> str:
        active_service = service or self.service
        return active_service.refresh(
            gitlab_host=self.gitlab_host,
            project_path=self.project_path,
            default_branch="main",
            gitlab_token=gitlab_token,
            dry_run=dry_run,
            force=force,
            log_fn=log_fn,
            identifier_override=None,
        )

    def _enforce(
        self,
        *,
        dry_run: bool = False,
        quota_mb: int | None = None,
        prune_after_hours: int | None = None,
        log_fn: Callable[[str], None] | None = None,
    ) -> None:
        self.service.enforce_policy(
            gitlab_host=self.gitlab_host,
            project_path=self.project_path,
            quota_mb=quota_mb,
            prune_after_hours=prune_after_hours,
            dry_run=dry_run,
            log_fn=log_fn,
        )

    def _snapshot(
        self,
        *,
        commit_hash: str,
        branch: str = "main",
        dry_run: bool = False,
        log_fn: Callable[[str], None] | None = None,
        retention_hours: int | None = None,
        max_snapshots: int | None = None,
    ) -> Path | None:
        outcome = self.service.snapshot(
            gitlab_host=self.gitlab_host,
            project_path=self.project_path,
            commit_hash=commit_hash,
            branch=branch,
            dry_run=dry_run,
            log_fn=log_fn,
            retention_hours=retention_hours,
            max_snapshots=max_snapshots,
        )
        return outcome.created_path

    def test_refresh_updates_to_remote_head(self) -> None:
        remote_path, cache_path = self._initialize_cache_repo()

        upstream_clone = self.tmp_path / "upstream"
        _run(["git", "clone", str(remote_path), str(upstream_clone)])
        _run(["git", "config", "user.email", "upstream@example.com"], cwd=upstream_clone)
        _run(["git", "config", "user.name", "Upstream"], cwd=upstream_clone)
        (upstream_clone / "README.md").write_text("updated\n", encoding="utf-8")
        _run(["git", "commit", "-am", "Update readme"], cwd=upstream_clone)
        _run(["git", "push"], cwd=upstream_clone)

        log_messages: list[str] = []
        refreshed_hash = self._refresh(log_fn=log_messages.append)

        upstream_head = subprocess.check_output(["git", "rev-parse", "HEAD"], cwd=str(upstream_clone)).decode("utf-8").strip()
        cache_head = subprocess.check_output(["git", "rev-parse", "HEAD"], cwd=str(cache_path)).decode("utf-8").strip()
        self.assertEqual(cache_head, upstream_head)
        self.assertEqual(refreshed_hash, upstream_head)
        self.assertTrue(
            any("synced to" in message for message in log_messages),
            "Expected synced commit log entry",
        )

    def test_refresh_respects_dry_run(self) -> None:
        remote_path, cache_path = self._initialize_cache_repo()

        upstream_clone = self.tmp_path / "upstream-dry"
        _run(["git", "clone", str(remote_path), str(upstream_clone)])
        _run(["git", "config", "user.email", "dry@example.com"], cwd=upstream_clone)
        _run(["git", "config", "user.name", "Dry Upstream"], cwd=upstream_clone)
        (upstream_clone / "README.md").write_text("dry update\n", encoding="utf-8")
        _run(["git", "commit", "-am", "Dry update"], cwd=upstream_clone)
        _run(["git", "push"], cwd=upstream_clone)

        before_head = subprocess.check_output(["git", "rev-parse", "HEAD~1"], cwd=str(upstream_clone)).decode("utf-8").strip()
        cache_head_before = subprocess.check_output(["git", "rev-parse", "HEAD"], cwd=str(cache_path)).decode("utf-8").strip()
        self.assertEqual(cache_head_before, before_head)

        log_messages: list[str] = []
        refreshed_hash = self._refresh(dry_run=True, log_fn=log_messages.append)

        cache_head_after = subprocess.check_output(["git", "rev-parse", "HEAD"], cwd=str(cache_path)).decode("utf-8").strip()
        self.assertEqual(cache_head_after, cache_head_before)
        self.assertEqual(refreshed_hash, cache_head_before)
        self.assertTrue(
            any("RUNNER_GIT_DRY_RUN=1 set; skipping git fetch" in message for message in log_messages),
            "Expected dry-run fetch skip log",
        )
        self.assertTrue(
            any("synced to" in message for message in log_messages),
            "Expected synced commit log entry",
        )

    def test_refresh_blocks_dirty_worktree(self) -> None:
        _, cache_path = self._initialize_cache_repo()
        (cache_path / "README.md").write_text("local change\n", encoding="utf-8")

        with self.assertRaises(ProjectCacheError) as captured:
            self._refresh()

        message = str(captured.exception)
        self.assertIn("uncommitted changes", message)
        self.assertIn("--force", message)

    def test_refresh_force_overwrites_dirty_worktree(self) -> None:
        _, cache_path = self._initialize_cache_repo()
        (cache_path / "README.md").write_text("local change\n", encoding="utf-8")

        self._refresh(force=True)

        status = subprocess.check_output(["git", "status", "--porcelain"], cwd=str(cache_path)).decode("utf-8")
        self.assertEqual(status.strip(), "")

    def test_refresh_initializes_submodules(self) -> None:
        remote_path, cache_path = self._initialize_cache_repo()

        submodule_src = self.tmp_path / "submodule-src"
        _run(["git", "init", "--initial-branch", "main", str(submodule_src)])
        _run(["git", "config", "user.email", "sub@example.com"], cwd=submodule_src)
        _run(["git", "config", "user.name", "Sub Module"], cwd=submodule_src)
        (submodule_src / "module.txt").write_text("submodule contents\n", encoding="utf-8")
        _run(["git", "add", "module.txt"], cwd=submodule_src)
        _run(["git", "commit", "-m", "Initial submodule commit"], cwd=submodule_src)
        submodule_remote = self.tmp_path / "submodule-remote.git"
        _run(["git", "clone", "--bare", str(submodule_src), str(submodule_remote)])

        original_allow = os.environ.get("GIT_ALLOW_PROTOCOL")
        os.environ["GIT_ALLOW_PROTOCOL"] = "file"
        try:
            upstream_clone = self.tmp_path / "upstream-with-submodule"
            _run(["git", "clone", str(remote_path), str(upstream_clone)])
            _run(["git", "config", "user.email", "upstream@example.com"], cwd=upstream_clone)
            _run(["git", "config", "user.name", "Upstream"], cwd=upstream_clone)
            _run(["git", "config", "protocol.file.allow", "always"], cwd=upstream_clone)
            _run(["git", "config", "protocol.file.allow", "always"], cwd=cache_path)
            _run(["git", "submodule", "add", str(submodule_remote), "deps/submodule"], cwd=upstream_clone)
            _run(["git", "add", ".gitmodules", "deps/submodule"], cwd=upstream_clone)
            _run(["git", "commit", "-m", "Add submodule"], cwd=upstream_clone)
            _run(["git", "push"], cwd=upstream_clone)

            submodule_file = cache_path / "deps" / "submodule" / "module.txt"
            self.assertFalse(submodule_file.exists())

            self._refresh()

            self.assertTrue(submodule_file.exists(), "Expected submodule file to be populated after refresh")
        finally:
            if original_allow is None:
                os.environ.pop("GIT_ALLOW_PROTOCOL", None)
            else:
                os.environ["GIT_ALLOW_PROTOCOL"] = original_allow

    def test_refresh_runs_git_lfs_commands_when_configured(self) -> None:
        remote_path, cache_path = self._initialize_cache_repo()

        upstream_clone = self.tmp_path / "upstream-lfs"
        _run(["git", "clone", str(remote_path), str(upstream_clone)])
        _run(["git", "config", "user.email", "lfs@example.com"], cwd=upstream_clone)
        _run(["git", "config", "user.name", "LFS Upstream"], cwd=upstream_clone)
        (upstream_clone / ".gitattributes").write_text("*.bin filter=lfs diff=lfs merge=lfs -text\n", encoding="utf-8")
        _run(["git", "add", ".gitattributes"], cwd=upstream_clone)
        _run(["git", "commit", "-m", "Configure LFS"], cwd=upstream_clone)
        _run(["git", "push"], cwd=upstream_clone)

        original_run = project_cache_git_ops.run_git_command
        lfs_calls: list[list[str]] = []

        def fake_run(args: list[str], cwd: Path, env: dict[str, str]) -> subprocess.CompletedProcess:
            if len(args) >= 2 and args[0] == "git" and args[1] == "lfs":
                lfs_calls.append(args[2:])
                return subprocess.CompletedProcess(args, 0, stdout=b"", stderr=b"")
            return original_run(args, cwd, env)

        with mock.patch.object(project_cache_git_ops, "run_git_command", side_effect=fake_run):
            with mock.patch("app.app.project_cache.service.shutil.which", return_value="/usr/bin/git-lfs"):
                self._refresh()

        self.assertIn(["fetch"], lfs_calls)
        self.assertIn(["checkout"], lfs_calls)

    def test_refresh_fetches_additional_branches_configured_via_env(self) -> None:
        remote_path, cache_path = self._initialize_cache_repo()

        upstream_clone = self.tmp_path / "upstream-release"
        _run(["git", "clone", str(remote_path), str(upstream_clone)])
        _run(["git", "config", "user.email", "release@example.com"], cwd=upstream_clone)
        _run(["git", "config", "user.name", "Release"], cwd=upstream_clone)
        _run(["git", "checkout", "-b", "release"], cwd=upstream_clone)
        (upstream_clone / "release.txt").write_text("release branch\n", encoding="utf-8")
        _run(["git", "add", "release.txt"], cwd=upstream_clone)
        _run(["git", "commit", "-m", "Add release file"], cwd=upstream_clone)
        _run(["git", "push", "-u", "origin", "release"], cwd=upstream_clone)

        original_run = project_cache_git_ops.run_git_command
        git_calls: list[list[str]] = []

        def capturing_run(args: list[str], cwd: Path, env: dict[str, str]) -> subprocess.CompletedProcess:
            if isinstance(args, list):
                git_calls.append(list(args))
            return original_run(args, cwd, env)

        os.environ["PROJECT_CACHE_ADDITIONAL_BRANCHES"] = "release"
        self.addCleanup(lambda: os.environ.pop("PROJECT_CACHE_ADDITIONAL_BRANCHES", None))

        with mock.patch.object(project_cache_git_ops, "run_git_command", side_effect=capturing_run):
            self._refresh()

        fetch_invocations = [call for call in git_calls if call[:4] == ["git", "fetch", "--tags", "--force"]]
        self.assertTrue(
            any("release" in call for call in fetch_invocations),
            "Expected release branch fetch during refresh",
        )

    def test_enforce_cache_policy_raises_when_quota_exceeded(self) -> None:
        _, cache_path = self._initialize_cache_repo()
        big_file = cache_path / "big.bin"
        big_file.write_bytes(b"0" * (2 * 1024 * 1024))  # 2 MiB
        _run(["git", "add", "big.bin"], cwd=cache_path)
        _run(["git", "commit", "-m", "Add large file"], cwd=cache_path)

        with self.assertRaises(ProjectCacheError) as captured:
            self._enforce(quota_mb=1, prune_after_hours=None)

        message = str(captured.exception)
        self.assertIn("remains above quota", message)

    def test_refresh_waits_for_existing_cache_lock(self) -> None:
        _, _ = self._initialize_cache_repo()
        repo_path = self.service.repo_path_for(self.gitlab_host, self.project_path)

        lock_started = threading.Event()

        def hold_lock() -> None:
            with cache_locking.cache_operation_lock(repo_path, identifier="test-lock", log_fn=None):
                lock_started.set()
                time.sleep(0.3)

        thread = threading.Thread(target=hold_lock)
        thread.start()
        self.assertTrue(lock_started.wait(timeout=2), "Lock holder did not start in time")
        start = time.perf_counter()
        refreshed = self._refresh()
        duration = time.perf_counter() - start
        thread.join()

        self.assertTrue(refreshed)
        self.assertGreaterEqual(duration, 0.25, "Refresh did not wait for lock release")

    def test_snapshot_project_cache_prunes_old_entries(self) -> None:
        _, cache_path = self._initialize_cache_repo()
        _run(["git", "config", "user.email", "snapshot@example.com"], cwd=cache_path)
        _run(["git", "config", "user.name", "Snapshot"], cwd=cache_path)
        (cache_path / "snapshot.txt").write_text("snapshot one\n", encoding="utf-8")
        _run(["git", "add", "snapshot.txt"], cwd=cache_path)
        _run(["git", "commit", "-m", "Snapshot file"], cwd=cache_path)

        first_commit = subprocess.check_output(["git", "rev-parse", "HEAD"], cwd=str(cache_path)).decode("utf-8").strip()
        first_snapshot = self._snapshot(
            commit_hash=first_commit,
            branch="main",
            retention_hours=999,
            max_snapshots=2,
        )
        self.assertIsNotNone(first_snapshot)

        (cache_path / "snapshot.txt").write_text("snapshot two\n", encoding="utf-8")
        _run(["git", "commit", "-am", "Snapshot two"], cwd=cache_path)
        second_commit = subprocess.check_output(["git", "rev-parse", "HEAD"], cwd=str(cache_path)).decode("utf-8").strip()
        self._snapshot(
            commit_hash=second_commit,
            branch="main",
            retention_hours=999,
            max_snapshots=1,
        )

        snapshot_dir = cache_path.parent / "snapshots"
        snapshots = list(snapshot_dir.glob("*.bundle"))
        self.assertEqual(len(snapshots), 1)
        remaining = snapshots[0]
        with (cache_path.parent / "cache-metadata.json").open("r", encoding="utf-8") as handle:
            metadata = json.load(handle)
        self.assertEqual(len(metadata.get("snapshots", [])), 1)
        self.assertEqual(Path(metadata["snapshots"][0]["path"]).resolve(), remaining.resolve())

    def test_refresh_emits_breakout_callback_when_sentinel_missing(self) -> None:
        _, cache_path = self._initialize_cache_repo()
        sentinel_path = cache_path.parent / project_cache_sentinel.SENTINEL_FILENAME
        sentinel_path.unlink(missing_ok=True)

        with self.assertRaises(ProjectCacheError) as captured:
            self._refresh(service=self.service_with_callbacks)

        self.assertIn("breakout", str(captured.exception).lower())
        self.assertTrue(
            any(isinstance(event, BreakoutEvent) for event in self.callbacks_events),
            "Expected breakout callback to be invoked",
        )

    def test_refresh_surfaces_authentication_error(self) -> None:
        _, cache_path = self._initialize_cache_repo()

        original_run = project_cache_git_ops.run_git_command

        def failing_fetch(args: list[str], cwd: Path, env: dict[str, str]) -> subprocess.CompletedProcess:
            if len(args) >= 2 and args[0] == "git" and args[1] == "fetch":
                return subprocess.CompletedProcess(
                    args,
                    128,
                    stdout=b"",
                    stderr=b"fatal: Authentication failed for 'https://oauth2:project-specific-token@gitlab.example.com/group/project.git'",
                )
            return original_run(args, cwd, env)

        with mock.patch.object(project_cache_git_ops, "run_git_command", side_effect=failing_fetch):
            with self.assertRaises(ProjectCacheError) as captured:
                self._refresh(gitlab_token="project-specific-token")

        message = str(captured.exception)
        self.assertIn("Git authentication failed", message)
        self.assertIn("POST /integrations/pat/verify", message)
        self.assertNotIn("project-specific-token", message)
        self.assertIn("<redacted>", message)

    def test_refresh_fails_on_corrupted_git_dir(self) -> None:
        # Create a repo then corrupt the .git directory to simulate corruption
        _, cache_path = self._initialize_cache_repo()
        git_dir = cache_path / ".git"
        # Remove objects directory to induce git failures
        objects_dir = git_dir / "objects"
        if objects_dir.exists():
            shutil.rmtree(objects_dir)
        # Add a bogus file to break repository invariants
        (git_dir / "CORRUPTED").write_text("broken", encoding="utf-8")

        with self.assertRaises(ProjectCacheError) as captured:
            self._refresh()

        error_message = str(captured.exception)
        self.assertIn("git fsck", error_message)
        self.assertIn("scripts/project_cache.py --refresh", error_message)


if __name__ == "__main__":
    unittest.main()
