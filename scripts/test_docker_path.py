#!/usr/bin/env python3
"""Ad-hoc helper to exercise the Docker codex runner end-to-end.

Creates a throwaway project (or reuses a supplied path/ID), registers it via the
FastAPI orchestrator when needed, submits a task (or inspects an existing one),
and prints the resulting logs plus `CODEX_CHANGE.log` from the sanitized
workspace. Defaults to Docker mode, supports per-run snapshots, custom network
allowlists at the project level, and skips cleanup when requested. Authentication
relies solely on a ChatGPT session bundle.
"""

from __future__ import annotations

import argparse
import os
import shutil
import subprocess
import sys
import tempfile
import time
from pathlib import Path
from datetime import datetime
from typing import Optional

REPO_ROOT = Path(__file__).resolve().parents[1]
LOG_DIVIDER = "-" * 60

if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from fastapi.testclient import TestClient

from app.app.project_cache import ProjectCacheError, ProjectCacheService

CACHE_SERVICE = ProjectCacheService()


def _reset_app_modules() -> None:
    """Discard cached `app.app.*` modules so Fresh imports re-init the app."""
    metrics_module = sys.modules.get("app.app.metrics")
    if metrics_module is not None:
        reset = getattr(metrics_module, "reset_metrics_registry", None)
        if callable(reset):
            reset()
    for name in list(sys.modules.keys()):
        if name.startswith("app.app"):
            sys.modules.pop(name)


def _bootstrap_app() -> TestClient:
    """Return a TestClient wired up to a freshly initialised FastAPI app."""
    from sqlmodel import SQLModel

    SQLModel.metadata.clear()
    from app.app import main as main_module

    return TestClient(main_module.app)


def _create_sample_project(root: Path) -> Path:
    """Seed a minimal git-initialised project for the task run."""
    root.mkdir(parents=True, exist_ok=True)
    (root / "README.md").write_text("docker path demo\n", encoding="utf-8")
    (root / "notes.txt").write_text("original content\n", encoding="utf-8")
    (root / ".projectsanitize").write_text(
        "# Sanitized workspace denylist for docker demo\n"
        "node_modules/\n"
        "dist/\n"
        ".env\n",
        encoding="utf-8",
    )
    subprocess.run(["git", "init", "-b", "main"], cwd=root, check=True, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    subprocess.run(["git", "config", "user.email", "codex-docker@example.com"], cwd=root, check=True, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    subprocess.run(["git", "config", "user.name", "Codex Docker"], cwd=root, check=True, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    subprocess.run(["git", "add", "."], cwd=root, check=True, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    subprocess.run(["git", "commit", "-m", "Initial commit"], cwd=root, check=True, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    return root


def _seed_project_cache(
    project_root: Path,
    *,
    gitlab_host: str,
    gitlab_project_path: str,
) -> Path:
    """Ensure the canonical cache directory contains a git repository for the project."""

    cache_repo = CACHE_SERVICE.repo_path_for(gitlab_host, gitlab_project_path).resolve()
    project_root = project_root.resolve()

    if cache_repo == project_root:
        return cache_repo

    cache_repo.parent.mkdir(parents=True, exist_ok=True)

    git_dir = cache_repo / ".git"
    if git_dir.exists():
        return cache_repo

    if cache_repo.exists():
        # Avoid clobbering unexpected contents; require manual cleanup instead.
        raise RuntimeError(
            f"Cache directory {cache_repo} exists without a git repository. Remove it and retry.",
        )

    shutil.copytree(project_root, cache_repo, symlinks=True)
    return cache_repo


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Run a placeholder codex task via Docker")
    parser.add_argument(
        "--prompt",
        default="Test docker codex run",
        help="Prompt text to send with the task",
    )
    parser.add_argument(
        "--project-root",
        type=Path,
        help="Optional project directory to reuse instead of creating a sample project",
    )
    parser.add_argument(
        "--keep-workspace",
        action="store_true",
        help="Skip deleting the sanitized workspace under workspaces/<task>/safe",
    )
    parser.add_argument(
        "--allowlist",
        metavar="HOST",
        nargs="+",
        help="Optional list of domains to store on the project allowlist",
    )
    parser.add_argument(
        "--project-id",
        type=int,
        help="Use an existing project ID instead of registering a new project",
    )
    parser.add_argument(
        "--task-id",
        type=int,
        help="Inspect an existing task ID instead of submitting a new task",
    )
    parser.add_argument(
        "--snapshot-prefix",
        help=(
            "Copy the sanitized workspace into workspaces/snapshots/<prefix>-<timestamp> "
            "so multiple runs can be inspected side-by-side"
        ),
    )
    parser.add_argument(
        "--snapshot-dir",
        type=Path,
        default=REPO_ROOT / "workspaces" / "snapshots",
        help="Directory where workspace snapshots should be stored (default: workspaces/snapshots)",
    )
    parser.add_argument(
        "--gitlab-token",
        default=os.environ.get("GITLAB_PAT"),
        help=(
            "GitLab personal access token with write_repository scope. "
            "Defaults to GITLAB_PAT when set."
        ),
    )
    parser.add_argument(
        "--codex-token",
        dest="codex_token",
        help="Codex access token to export as CODEX_ACCESS_TOKEN before submitting the task",
    )
    parser.add_argument(
        "--disable-docker",
        action="store_true",
        help="Force the helper to run with RUNNER_DISABLE_DOCKER=1 (stub mode)",
    )
    parser.add_argument(
        "--expect-auth-failure",
        action="store_true",
        help="Assert that the Codex task fails due to authentication issues",
    )
    parser.add_argument(
        "--gitlab-host",
        default="https://gitlab.example.com",
        help="GitLab host to register with the project (default: https://gitlab.example.com)",
    )
    parser.add_argument(
        "--gitlab-project-path",
        default="example/docker-demo",
        help="Namespace/repo path for the demo project (default: example/docker-demo)",
    )
    parser.add_argument(
        "--session-bundle",
        type=Path,
        help="Path to a ChatGPT auth.json bundle to import before running the task",
    )
    parser.add_argument(
        "--branch",
        dest="branch_name",
        help="Optional branch name to use instead of the generated codex/task-* branch",
    )
    parser.add_argument(
        "--target-branch",
        dest="target_branch",
        help="Target (base) branch for the task; defaults to the project's configured default branch",
    )
    parser.add_argument(
        "--change-mode",
        dest="change_mode",
        choices=["merge_request", "branch_commit"],
        default="merge_request",
        help="Choose whether to create a merge request (default) or commit to the existing branch",
    )
    parser.add_argument(
        "--codex-model",
        dest="codex_model",
        help="Optional Codex model identifier to use for the task run",
    )
    parser.add_argument(
        "--codex-reasoning-effort",
        dest="codex_reasoning_effort",
        choices=["low", "medium", "high"],
        default="medium",
        help="Codex reasoning effort to request (default: medium)",
    )
    parser.add_argument(
        "--live",
        action="store_true",
        help="Disable RUNNER_GIT_DRY_RUN and push to GitLab (requires valid token and allowlisted network)",
    )
    parser.add_argument(
        "--exercise-cache",
        action="store_true",
        help=(
            "Exercise cache bootstrap/refresh logs and simulate a failure: "
            "prints cache path, forces a dry-run bootstrap skip, then corrupts the cache to verify failure handling"
        ),
    )
    return parser.parse_args()


def _resolve_project_path(args: argparse.Namespace, scratch_dir: Path) -> Path:
    if args.project_root:
        project_path = args.project_root.expanduser().resolve()
        if not project_path.exists():
            raise FileNotFoundError(f"Project root does not exist: {project_path}")
        return project_path
    return _create_sample_project(scratch_dir / "docker-demo-project")


def _register_project(
    client: TestClient,
    gitlab_token: str,
    *,
    gitlab_host: str,
    gitlab_project_path: str,
    allowlist: Optional[list[str]] = None,
) -> dict:
    payload = {
        "name": "docker-demo-project",
        "default_branch": "main",
        "gitlab_host": gitlab_host,
        "gitlab_project_path": gitlab_project_path,
    }
    if allowlist is not None:
        payload["allowlist"] = allowlist
    response = client.post("/projects", json=payload)
    response.raise_for_status()
    return response.json()


def _update_project_allowlist(client: TestClient, project_id: int, allowlist: list[str]) -> list[str]:
    response = client.patch(f"/projects/{project_id}", json={"allowlist": allowlist})
    response.raise_for_status()
    body = response.json()
    return body.get("allowlist", allowlist)


def _submit_task(
    client: TestClient,
    project_id: int,
    prompt: str,
    *,
    branch_name: Optional[str] = None,
    target_branch: Optional[str] = None,
    codex_model: Optional[str] = None,
    codex_reasoning_effort: Optional[str] = None,
    change_mode: Optional[str] = None,
) -> int:
    payload = {
        "project_id": project_id,
        "prompt": prompt,
    }
    if branch_name:
        payload["branch_name"] = branch_name
    if target_branch:
        payload["target_branch"] = target_branch
    if codex_model:
        payload["codex_model"] = codex_model
    if codex_reasoning_effort:
        payload["codex_reasoning_effort"] = codex_reasoning_effort
    if change_mode:
        payload["change_mode"] = change_mode

    response = client.post("/tasks", json=payload)
    response.raise_for_status()
    return response.json()["id"]


def _wait_for_completion(client: TestClient, task_id: int, timeout: float = 40.0) -> dict:
    deadline = time.time() + timeout
    while time.time() < deadline:
        detail_resp = client.get(f"/tasks/{task_id}")
        detail_resp.raise_for_status()
        payload = detail_resp.json()
        if payload["status"] in {"done", "failed"}:
            return payload
        time.sleep(0.5)
    raise TimeoutError(f"Task {task_id} did not finish within {timeout} seconds")


def _print_logs(client: TestClient, task_id: int) -> list[str]:
    log_resp = client.get(f"/tasks/{task_id}/logs?follow=0")
    log_resp.raise_for_status()
    payload = log_resp.json()
    entries = payload.get("entries", [])
    snapshot_status = payload.get("status")
    snapshot_branch = payload.get("branch") or "--"
    snapshot_target = payload.get("target_branch") or "--"
    snapshot_mode = payload.get("change_mode") or "--"
    snapshot_commit = payload.get("commit_sha") or "--"
    snapshot_commit_url = payload.get("commit_url") or ""
    snapshot_model = payload.get("codex_model") or "default"
    snapshot_reasoning = payload.get("codex_reasoning_effort") or "medium"
    snapshot_abort = payload.get("abort_requested", False)
    credentials = payload.get("credentials") or {}
    pat_available = "yes" if credentials.get("gitlab_pat_available") else "no"
    pat_updated = credentials.get("gitlab_pat_last_updated") or "--"
    chat_available = "yes" if credentials.get("chatgpt_session_available") else "no"
    chat_updated = credentials.get("chatgpt_session_last_updated") or "--"
    print(LOG_DIVIDER)
    print("Task log snapshot:")
    print(
        f"- Status at capture: {snapshot_status or '--'} | Mode: {snapshot_mode} | Branch: {snapshot_branch} | "
        f"Base: {snapshot_target} | Model: {snapshot_model} | Reasoning: {snapshot_reasoning} | "
        f"Abort requested: {'yes' if snapshot_abort else 'no'}"
    )
    if snapshot_mode == 'branch_commit' and snapshot_commit != '--':
        if snapshot_commit_url:
            print(f"- Commit: {snapshot_commit} ({snapshot_commit_url})")
        else:
            print(f"- Commit: {snapshot_commit}")
    print(
        "- Credentials: PAT {pat} (updated {pat_time}) | ChatGPT session {chat} (updated {chat_time})".format(
            pat=pat_available,
            pat_time=pat_updated,
            chat=chat_available,
            chat_time=chat_updated,
        )
    )
    for entry in entries:
        print(entry)
    print(LOG_DIVIDER)
    return entries


def _show_change_log(workspace_path: Optional[Path]) -> None:
    if workspace_path is None:
        print("Sanitized workspace unavailable; skipping CODEX_CHANGE.log inspection")
        return

    change_log = workspace_path / "CODEX_CHANGE.log"
    if not change_log.exists():
        print("CODEX_CHANGE.log missing from workspace")
        return
    print("CODEX_CHANGE.log contents:\n")
    print(change_log.read_text(encoding="utf-8"))


def _snapshot_workspace(workspace_path: Path, snapshot_dir: Path, prefix: str) -> Path:
    snapshot_dir.mkdir(parents=True, exist_ok=True)
    timestamp = datetime.now().strftime("%Y%m%d-%H%M%S")
    destination = snapshot_dir / f"{prefix}-{timestamp}"
    if destination.exists():
        raise FileExistsError(f"Snapshot destination already exists: {destination}")
    shutil.copytree(workspace_path, destination)
    print(f"Snapshot copied to {destination}")
    return destination


def main() -> None:
    args = _parse_args()
    scratch_dir_obj: Optional[tempfile.TemporaryDirectory[str]] = None

    created_task = False
    snapshot_path: Optional[Path] = None
    workspace_path: Optional[Path] = None
    original_db_url = os.environ.get("APP_DATABASE_URL")
    original_dry_run = os.environ.get("RUNNER_GIT_DRY_RUN")
    original_disable_docker = os.environ.get("RUNNER_DISABLE_DOCKER")
    using_temp_db = original_db_url is None

    if args.live:
        if not args.gitlab_token:
            raise RuntimeError("--live requires --gitlab-token or GITLAB_PAT to be set")
        os.environ.pop("RUNNER_GIT_DRY_RUN", None)
    else:
        os.environ["RUNNER_GIT_DRY_RUN"] = "1"
        if not args.gitlab_token:
            args.gitlab_token = "dry-run-token"
        print("Running in dry-run mode: pushes and MR creation are skipped; using placeholder GitLab token.")

    if args.disable_docker:
        os.environ["RUNNER_DISABLE_DOCKER"] = "1"
        print("Docker disabled via --disable-docker; stub runner will be used.")
    else:
        os.environ.pop("RUNNER_DISABLE_DOCKER", None)

    if args.codex_token:
        os.environ["CODEX_ACCESS_TOKEN"] = args.codex_token

    try:
        scratch_dir_obj = tempfile.TemporaryDirectory()
        scratch_dir = Path(scratch_dir_obj.name)
        if using_temp_db:
            os.environ["APP_DATABASE_URL"] = f"sqlite:///{scratch_dir / 'helper.db'}"

        _reset_app_modules()
        with _bootstrap_app() as client:
            helper_actor = "docker-helper"
            if args.gitlab_token:
                rotate_payload = {"token": args.gitlab_token, "updated_by": helper_actor}
                rotate_resp = client.post("/integrations/pat", json=rotate_payload)
                rotate_resp.raise_for_status()
            else:
                status_payload = client.get("/integrations/pat").json()
                if not status_payload.get("configured"):
                    raise RuntimeError(
                        "GitLab PAT not configured; provide --gitlab-token or pre-configure via the integrations API",
                    )

            if args.session_bundle:
                try:
                    bundle_text = args.session_bundle.read_text(encoding="utf-8")
                except OSError as exc:  # noqa: BLE001
                    raise RuntimeError(f"Failed to read session bundle: {exc}") from exc
                session_payload = {"bundle": bundle_text, "updated_by": helper_actor}
                session_resp = client.post("/integrations/pat/session", json=session_payload)
                session_resp.raise_for_status()

            status_snapshot = client.get("/integrations/pat").json()
            pat_flag = "configured" if status_snapshot.get("configured") else "missing"
            session_flag = "configured" if status_snapshot.get("session_configured") else "missing"
            active_kind = status_snapshot.get("active_credential", "none")
            print(
                f"Credential status -> GitLab PAT: {pat_flag}, ChatGPT session: {session_flag}, active: {active_kind}"
            )

            if not args.disable_docker and not status_snapshot.get("session_configured"):
                if args.expect_auth_failure:
                    print(
                        "warning: ChatGPT session bundle not configured; proceeding because --expect-auth-failure was set",
                    )
                else:
                    raise RuntimeError(
                        "ChatGPT session bundle not configured; provide --session-bundle or import one via Settings before running Docker tasks",
                    )

            project_id: Optional[int] = args.project_id
            if args.task_id is None:
                project_root: Optional[Path] = None
                if project_id is None:
                    project_root = _resolve_project_path(args, scratch_dir)
                    project_data = _register_project(
                        client,
                        args.gitlab_token,
                        gitlab_host=args.gitlab_host,
                        gitlab_project_path=args.gitlab_project_path,
                        allowlist=args.allowlist,
                    )
                    project_id = project_data["id"]
                    print(
                        "Registered project {pid} at {root} (GitLab: {host}/{path})".format(
                            pid=project_id,
                            root=project_root,
                            host=args.gitlab_host.rstrip('/'),
                            path=args.gitlab_project_path,
                        )
                    )
                    configured_allowlist = project_data.get("allowlist", [])
                    if configured_allowlist:
                        print(
                            "Configured project allowlist: {domains}".format(
                                domains=", ".join(configured_allowlist),
                            )
                        )
                    if project_root is not None:
                        try:
                            cache_repo = _seed_project_cache(
                                project_root,
                                gitlab_host=args.gitlab_host,
                                gitlab_project_path=args.gitlab_project_path,
                            )
                        except RuntimeError as cache_error:
                            raise RuntimeError(
                                f"Failed to seed project cache for project {project_id}: {cache_error}",
                            ) from cache_error
                        else:
                            print(f"Seeded project cache at {cache_repo}")
                else:
                    print(f"Using existing project {project_id} for new task")
                    if args.allowlist is not None:
                        updated_allowlist = _update_project_allowlist(client, project_id, args.allowlist)
                        print(
                            "Updated project allowlist: {domains}".format(
                                domains=", ".join(updated_allowlist) if updated_allowlist else "<empty>",
                            )
                        )
            elif project_id is not None:
                print(f"Using existing project {project_id} for inspection")

            if args.exercise_cache:
                # Probe cache bootstrap/refresh paths and an intentional failure
                repo_path = CACHE_SERVICE.repo_path_for(args.gitlab_host or "", args.gitlab_project_path or "")
                print(f"Cache path for project: {repo_path}")
                # Force a dry-run bootstrap message by ensuring directory exists without .git
                repo_path.parent.mkdir(parents=True, exist_ok=True)
                if not repo_path.exists():
                    repo_path.mkdir(parents=True)
                # Invoke refresh in dry-run to capture skip messages
                try:
                    refreshed = CACHE_SERVICE.refresh(
                        gitlab_host=args.gitlab_host or "",
                        project_path=args.gitlab_project_path or "",
                        default_branch="main",
                        dry_run=True,
                        log_fn=lambda m: print(f"[cache] {m}"),
                        identifier_override=f"{args.gitlab_host.rstrip('/')}/{args.gitlab_project_path}",
                    )
                    print(f"Dry-run refresh result: {refreshed}")
                except ProjectCacheError as exc:
                    print(f"Expected dry-run cache warning: {exc}")
                # Simulate corruption and ensure a hard failure occurs
                corrupt_flag = repo_path / ".git"
                if not corrupt_flag.exists():
                    corrupt_flag.mkdir(parents=True, exist_ok=True)
                (corrupt_flag / "BROKEN").write_text("1", encoding="utf-8")
                try:
                    CACHE_SERVICE.refresh(
                        gitlab_host=args.gitlab_host or "",
                        project_path=args.gitlab_project_path or "",
                        default_branch="main",
                        dry_run=False,
                        log_fn=lambda m: print(f"[cache] {m}"),
                        identifier_override=f"{args.gitlab_host.rstrip('/')}/{args.gitlab_project_path}",
                    )
                except ProjectCacheError as exc:
                    print(f"Intentional cache refresh failure captured: {exc}")

            if args.task_id is not None:
                task_id = args.task_id
                print(f"Inspecting existing task {task_id}")
            else:
                if project_id is None:
                    raise RuntimeError("Project ID required to submit a new task")
                task_id = _submit_task(
                    client,
                    project_id,
                    args.prompt,
                    branch_name=args.branch_name,
                    target_branch=args.target_branch,
                    codex_model=args.codex_model,
                    codex_reasoning_effort=args.codex_reasoning_effort,
                    change_mode=args.change_mode,
                )
                print(
                    "Submitted task {task_id} (project_id={pid}, mode={mode}, branch={branch}, base={base}, model={model}, reasoning={reasoning})".format(
                        task_id=task_id,
                        pid=project_id,
                        mode=args.change_mode,
                        branch=args.branch_name or "<generated>",
                        base=args.target_branch or "<default>",
                        model=args.codex_model or "<default>",
                        reasoning=args.codex_reasoning_effort,
                    )
                )
                created_task = True

            result = _wait_for_completion(client, task_id)
            print(f"Task status: {result['status']}")
            workspace_location = result.get("workspace_path")
            if workspace_location:
                workspace_path = Path(workspace_location)
                print(f"Sanitized workspace: {workspace_path}")
            else:
                print("Sanitized workspace path missing from task result")

            if result.get("branch"):
                print(f"Branch recorded: {result['branch']}")
            if result.get("target_branch"):
                print(f"Base branch: {result['target_branch']}")
            if result.get("codex_model"):
                print(f"Codex model used: {result['codex_model']}")
            if result.get("codex_reasoning_effort"):
                print(f"Reasoning effort: {result['codex_reasoning_effort']}")
            if result.get("codex_agent_version"):
                print(f"Codex agent version: {result['codex_agent_version']}")
            if result.get("codex_invocation"):
                print(f"Codex invocation: {result['codex_invocation']}")

            if args.expect_auth_failure and result["status"] != "failed":
                raise RuntimeError("Expected Codex auth failure but task completed successfully")
            if not args.expect_auth_failure and result["status"] != "done":
                raise RuntimeError(f"Task did not succeed (status={result['status']})")

            _print_logs(client, task_id)
            _show_change_log(workspace_path)

            if args.snapshot_prefix and workspace_path is not None:
                snapshot_path = _snapshot_workspace(workspace_path, args.snapshot_dir, args.snapshot_prefix)

    finally:
        if scratch_dir_obj:
            scratch_dir_obj.cleanup()
        if using_temp_db:
            os.environ.pop("APP_DATABASE_URL", None)
        elif original_db_url is not None:
            os.environ["APP_DATABASE_URL"] = original_db_url
        if original_dry_run is None:
            os.environ.pop("RUNNER_GIT_DRY_RUN", None)
        else:
            os.environ["RUNNER_GIT_DRY_RUN"] = original_dry_run
        if original_disable_docker is None:
            os.environ.pop("RUNNER_DISABLE_DOCKER", None)
        else:
            os.environ["RUNNER_DISABLE_DOCKER"] = original_disable_docker

    if created_task and not args.keep_workspace and workspace_path is not None:
        workspace_parent = workspace_path.parent
        if workspace_parent.exists():
            shutil.rmtree(workspace_parent, ignore_errors=True)

    if args.snapshot_prefix and 'snapshot_path' in locals() and snapshot_path is not None:
        print(f"Sanitized workspace snapshot preserved at {snapshot_path}")


if __name__ == "__main__":
    try:
        main()
    except Exception as exc:  # noqa: BLE001 - propagate user-facing failure
        print(f"Error: {exc}", file=sys.stderr)
        sys.exit(1)
