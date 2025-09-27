#!/usr/bin/env python3
"""Print runner container hardening highlights and verify critical flags."""

from __future__ import annotations

import os
import shutil
import sys
import tempfile
import warnings
from contextlib import ExitStack
import shutil
from pathlib import Path
from typing import Iterable, Optional, Tuple
from uuid import uuid4

REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

warnings.filterwarnings(
    "ignore",
    message=".*Unable to find acceptable character detection dependency.*",
)

from app.app.codex_runner import (
    CONTAINER_SECURITY_OPTIONS,
    DEFAULT_MEM_LIMIT,
    DEFAULT_PIDS_LIMIT,
    DEFAULT_TMPFS_MOUNTS,
    RUNNER_CONTEXT,
    RUNNER_IMAGE_TAG,
    _ensure_runner_image,
)


def _format_list(values: Iterable[str]) -> str:
    return ", ".join(sorted(values)) if values else "<empty>"


def _run_escape_probe() -> Tuple[str, Optional[str]]:
    if os.environ.get("RUNNER_DISABLE_DOCKER", "0") == "1":
        return "skipped (docker disabled)", None

    try:
        import docker
        from docker.errors import APIError, DockerException, ImageNotFound
    except ModuleNotFoundError:
        return "skipped (docker SDK unavailable)", None

    if not RUNNER_CONTEXT.exists():
        return "skipped (runner context missing)", "runner build context is not available"

    try:
        client = docker.from_env()
    except DockerException as exc:  # type: ignore[name-defined]
        return f"skipped (docker unreachable: {exc})", None

    try:
        _ensure_runner_image(client, log_fn=None)
    except (DockerException, ImageNotFound, APIError) as exc:  # type: ignore[name-defined]
        return f"skipped (unable to ensure runner image: {exc})", "runner image could not be prepared"

    sentinel_name = f"codex_sentinel_{uuid4().hex}"
    host_tmp = Path(tempfile.gettempdir()) / sentinel_name
    host_tmp.write_text("sentinel", encoding="utf-8")

    command = [
        f"set -euo pipefail; cat /work/../../../../tmp/{sentinel_name}"
    ]

    volumes = {tempfile.mkdtemp(): {"bind": "/work", "mode": "rw"}}

    mem_limit = os.environ.get("RUNNER_MEM_LIMIT", DEFAULT_MEM_LIMIT)
    pids_limit_env = os.environ.get("RUNNER_PIDS_LIMIT")
    try:
        pids_limit = int(pids_limit_env) if pids_limit_env is not None else DEFAULT_PIDS_LIMIT
    except (TypeError, ValueError):
        pids_limit = DEFAULT_PIDS_LIMIT

    tmpfs_mounts = dict(DEFAULT_TMPFS_MOUNTS)

    container_kwargs = dict(
        image=RUNNER_IMAGE_TAG,
        command=command,
        volumes=volumes,
        environment={},
        detach=True,
        mem_limit=mem_limit,
        pids_limit=pids_limit,
        tmpfs=tmpfs_mounts,
    )
    container_kwargs.update(CONTAINER_SECURITY_OPTIONS)

    # Keep resources tidy even if docker operations fail mid-way.
    with ExitStack() as stack:
        workspace_dir = next(iter(volumes.keys()))
        stack.callback(lambda path=workspace_dir: shutil.rmtree(path, ignore_errors=True))
        stack.callback(lambda path=host_tmp: path.unlink(missing_ok=True))

        try:
            container = client.containers.create(**container_kwargs)
        except DockerException as exc:  # type: ignore[name-defined]
            return f"skipped (docker create failed: {exc})", "docker container could not be created"

        stack.callback(_remove_container, container)

        container.start()
        result = container.wait()
        exit_code = int(result.get("StatusCode", 1))
        logs = container.logs(stdout=True, stderr=True).decode("utf-8", errors="ignore")

    if exit_code == 0:
        return "FAILED (escape probe succeeded)", (
            "container escaped workspace boundaries and read /tmp sentinel"
        )

    if logs:
        tail = logs.strip().splitlines()[-1]
        return f"OK (attempt failed as expected: {tail})", None
    return "OK (attempt failed as expected)", None


def _remove_container(container) -> None:
    try:
        container.remove(force=True)
    except Exception:
        pass


def main() -> int:
    failures: list[str] = []

    read_only = CONTAINER_SECURITY_OPTIONS.get("read_only")
    if not read_only:
        failures.append("read_only root filesystem is not enabled")

    cap_drop = tuple(CONTAINER_SECURITY_OPTIONS.get("cap_drop", []) or [])
    if "ALL" not in cap_drop:
        failures.append("cap_drop is missing 'ALL'")

    security_opt = tuple(CONTAINER_SECURITY_OPTIONS.get("security_opt", []) or [])
    if not any(opt.startswith("no-new-privileges") for opt in security_opt):
        failures.append("security_opt does not enforce no-new-privileges")

    user = CONTAINER_SECURITY_OPTIONS.get("user") or ""
    if user in {"0", "root", "0:0", ""}:
        failures.append("runner container user is root; expected non-root user")

    tmpfs_mounts = DEFAULT_TMPFS_MOUNTS.keys()
    required_tmpfs = {"/tmp", "/run", "/home/codex"}
    if not required_tmpfs.issubset(tmpfs_mounts):
        missing = required_tmpfs.difference(tmpfs_mounts)
        failures.append(f"tmpfs mounts missing: {', '.join(sorted(missing))}")

    mem_limit = os.environ.get("RUNNER_MEM_LIMIT", DEFAULT_MEM_LIMIT)
    pids_limit_env = os.environ.get("RUNNER_PIDS_LIMIT")
    try:
        pids_limit = int(pids_limit_env) if pids_limit_env is not None else DEFAULT_PIDS_LIMIT
    except (TypeError, ValueError):
        pids_limit = DEFAULT_PIDS_LIMIT

    print("Runner container hardening summary:\n")
    print(f"  read_only root filesystem : {read_only}")
    print(f"  dropped capabilities      : {_format_list(cap_drop)}")
    print(f"  security options          : {_format_list(security_opt)}")
    print(f"  runtime user              : {user}")
    print(f"  tmpfs mounts              : {_format_list(DEFAULT_TMPFS_MOUNTS.keys())}")
    print(f"  memory limit (effective)  : {mem_limit}")
    print(f"  pids limit (effective)    : {pids_limit}")

    probe_status, probe_failure = _run_escape_probe()
    print(f"  breakout probe            : {probe_status}")
    if probe_failure:
        failures.append(probe_failure)

    if failures:
        print("\nScan FAILED:")
        for failure in failures:
            print(f"  - {failure}")
        return 1

    print("\nScan OK: critical hardening flags are present.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
