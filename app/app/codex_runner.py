from __future__ import annotations

import json
import os
import subprocess
from dataclasses import dataclass, field
from pathlib import Path
from typing import Callable, Iterable, Optional

import base64

import docker
from docker.errors import APIError, DockerException, ImageNotFound

from .allowlist import proxy_environment

REPO_ROOT = Path(__file__).resolve().parents[2]
RUNNER_CONTEXT = REPO_ROOT / "runner"
RUNNER_IMAGE_TAG = "local-codex-runner:latest"
DEFAULT_DOCKER_NETWORK = "codex-shared"
DEFAULT_MEM_LIMIT = "2g"
DEFAULT_PIDS_LIMIT = 256
CODEX_METADATA_FILENAME = "CODEX_METADATA.json"
CONTAINER_SECURITY_OPTIONS = {
    "read_only": True,
    "cap_drop": ["ALL"],
    "security_opt": ["no-new-privileges:true"],
    "user": "1000:1000",
}
DEFAULT_TMPFS_MOUNTS = {
    "/tmp": "size=64m,uid=1000,gid=1000",
    "/run": "size=16m,uid=1000,gid=1000",
    "/home/codex": "size=128m,uid=1000,gid=1000",
}


@dataclass
class CodexResult:
    exit_code: int
    used_docker: bool
    branch: Optional[str] = None
    mr_url: Optional[str] = None
    agent_version: Optional[str] = None
    invocation_flags: list[str] = field(default_factory=list)


class CodexRunnerError(RuntimeError):
    """Raised when the codex execution fails before producing an exit code."""


def run_codex(
    workspace: Path,
    *,
    prompt: str,
    agent_type: str = "codex",
    model: Optional[str] = None,
    allowlist: Optional[Iterable[str]] = None,
    gitlab_host: str,
    gitlab_project_path: str,
    gitlab_token: str,
    codex_token: Optional[str],
    chatgpt_session_bundle: Optional[str],
    claude_api_key: Optional[str] = None,
    target_branch: str,
    branch_name: str,
    mr_title: str,
    task_id: int,
    log_fn: Optional[Callable[[str], None]] = None,
) -> CodexResult:
    """Execute the placeholder codex workflow, preferring Docker when available."""
    allowlist = list(allowlist or [])
    workspace = workspace.resolve()

    if not gitlab_token:
        raise CodexRunnerError("GitLab token is required for finish_task operations")

    # Determine metadata filename based on agent type
    is_claude = agent_type == "claude-code"
    metadata_filename = "CLAUDE_METADATA.json" if is_claude else CODEX_METADATA_FILENAME
    metadata_path = workspace / metadata_filename
    result_path = workspace / "RUNNER_RESULT.json"
    for stale_path in (result_path, metadata_path):
        if stale_path.exists():
            try:
                stale_path.unlink()
            except OSError:
                # Stale metadata from previous runs is best-effort removed.
                pass

    runner_env = {
        "GITLAB_TOKEN": gitlab_token,
        "GITLAB_HOST": gitlab_host,
        "GITLAB_PROJECT_PATH": gitlab_project_path,
        "TARGET_BRANCH": target_branch,
        "BRANCH": branch_name,
        "MR_TITLE": mr_title,
        "TASK_ID": str(task_id),
        "RUNNER_RESULT_FILE": "RUNNER_RESULT.json",
    }

    if is_claude:
        # Claude Code specific environment variables
        runner_env.update({
            "CLAUDE_PROMPT": prompt,
            "CLAUDE_METADATA_FILE": metadata_filename,
            "CLAUDE_INVOCATION_FLAGS": "--dangerously-skip-permissions",
            "CLAUDE_MODEL": model or "sonnet",
        })
        if claude_api_key:
            runner_env["CLAUDE_API_KEY"] = claude_api_key
    else:
        # Codex specific environment variables
        runner_env.update({
            "PROMPT": prompt,
            "CODEX_METADATA_FILE": metadata_filename,
            "CODEX_INVOCATION_FLAGS": "--yolo --skip-git-repo-check",
        })

    dry_run_flag = os.environ.get("RUNNER_GIT_DRY_RUN")
    if dry_run_flag is not None:
        runner_env["RUNNER_GIT_DRY_RUN"] = dry_run_flag

    if codex_token:
        runner_env["CODEX_ACCESS_TOKEN"] = codex_token

    if chatgpt_session_bundle:
        encoded_bundle = base64.b64encode(chatgpt_session_bundle.encode("utf-8")).decode("ascii")
        runner_env["CODEX_SESSION_BUNDLE_B64"] = encoded_bundle
        if "CODEX_CREDENTIAL_MODE" not in runner_env:
            runner_env["CODEX_CREDENTIAL_MODE"] = "session"
    elif codex_token:
        runner_env["CODEX_CREDENTIAL_MODE"] = "api_token"

    runner_env.update(proxy_environment())

    if os.environ.get("RUNNER_DISABLE_DOCKER", "0") == "1":
        exit_code = _run_local_stub(workspace, prompt, allowlist, runner_env, log_fn)
        result_branch, mr_url = _load_finish_metadata(result_path, log_fn) if exit_code == 0 else (None, None)
        agent_version, flags = _load_metadata(metadata_path, log_fn)
        return CodexResult(
            exit_code=exit_code,
            used_docker=False,
            branch=result_branch,
            mr_url=mr_url,
            agent_version=agent_version,
            invocation_flags=flags,
        )

    try:
        exit_code = _run_in_docker(workspace, prompt, allowlist, runner_env, agent_type, log_fn)
    except (DockerException, CodexRunnerError) as exc:
        if log_fn:
            log_fn(f"Docker unavailable or failed ({exc}); using local stub")
        exit_code = _run_local_stub(workspace, prompt, allowlist, runner_env, log_fn)
        used_docker = False
    else:
        used_docker = True
    result_branch, mr_url = _load_finish_metadata(result_path, log_fn) if exit_code == 0 else (None, None)
    agent_version, flags = _load_metadata(metadata_path, log_fn)
    return CodexResult(
        exit_code=exit_code,
        used_docker=used_docker,
        branch=result_branch,
        mr_url=mr_url,
        agent_version=agent_version,
        invocation_flags=flags,
    )


def _run_in_docker(
    workspace: Path,
    prompt: str,
    allowlist: Iterable[str],
    runner_env: dict[str, str],
    agent_type: str,
    log_fn: Optional[Callable[[str], None]],
) -> int:
    if not RUNNER_CONTEXT.exists():
        raise CodexRunnerError("Runner build context is missing")

    client = docker.from_env()
    _ensure_runner_image(client, log_fn)

    volumes = {str(workspace): {"bind": "/work", "mode": "rw"}}
    environment = dict(runner_env)

    # Determine the launcher script based on agent type
    is_claude = agent_type == "claude-code"
    if is_claude:
        command = ["/usr/local/bin/launch_claude_code.sh"]
        # Claude Code uses CLAUDE_PROMPT, which is already set in runner_env
    else:
        command = ["/usr/local/bin/launch_codex.sh"]
        environment["CODEX_PROMPT"] = prompt

    environment["EGRESS_ALLOWLIST"] = ",".join(allowlist)

    mem_limit = os.environ.get("RUNNER_MEM_LIMIT", DEFAULT_MEM_LIMIT)
    pids_limit_env = os.environ.get("RUNNER_PIDS_LIMIT")
    if pids_limit_env is None:
        pids_limit = DEFAULT_PIDS_LIMIT
    else:
        try:
            pids_limit = int(pids_limit_env)
        except (TypeError, ValueError):
            pids_limit = DEFAULT_PIDS_LIMIT

    tmpfs_mounts = dict(DEFAULT_TMPFS_MOUNTS)

    network_target = os.environ.get("RUNNER_DOCKER_NETWORK", DEFAULT_DOCKER_NETWORK)
    container_kwargs = dict(
        image=RUNNER_IMAGE_TAG,
        command=command,
        volumes=volumes,
        environment=environment,
        detach=True,
        mem_limit=mem_limit,
        pids_limit=pids_limit,
        tmpfs=tmpfs_mounts,
    )
    container_kwargs.update(CONTAINER_SECURITY_OPTIONS)
    if network_target:
        container_kwargs["network"] = network_target

    try:
        container = client.containers.create(**container_kwargs)
    except APIError as exc:
        if network_target and "network" in str(exc).lower():
            if log_fn:
                log_fn(
                    f"docker: failed to attach network '{network_target}' ({exc}); retrying without explicit network",
                )
            container_kwargs.pop("network", None)
            container = client.containers.create(**container_kwargs)
        else:
            raise
    try:
        container.start()
        for raw in container.logs(stream=True, follow=True):
            if log_fn:
                log_fn(raw.decode("utf-8", errors="ignore").rstrip())
        result = container.wait()
        exit_code = int(result.get("StatusCode", 1))
        if log_fn:
            error_message = result.get("Error")
            if error_message:
                log_fn(f"docker: container error reported: {error_message}")
        state: dict[str, object] = {}
        try:
            container.reload()
        except Exception:
            state = {}
        else:
            state = container.attrs.get("State", {})
        if log_fn and state:
            if state.get("OOMKilled"):
                log_fn("docker: runner terminated due to OOM (mem_limit active)")
            if state.get("Error"):
                log_fn(f"docker: state error: {state['Error']}")
    finally:
        try:
            container.remove(force=True)
        except DockerException:
            pass
    return exit_code


def _ensure_runner_image(client, log_fn: Optional[Callable[[str], None]]) -> None:
    try:
        client.images.get(RUNNER_IMAGE_TAG)
    except ImageNotFound:
        if log_fn:
            log_fn("Runner image not found; building placeholder image")
        response = client.api.build(path=str(RUNNER_CONTEXT), tag=RUNNER_IMAGE_TAG, decode=True)
        for chunk in response:
            message = chunk.get("stream") or chunk.get("status")
            if message and log_fn:
                log_fn(message.strip())


def _run_finish_task_local(
    workspace: Path,
    env: dict[str, str],
    log_fn: Optional[Callable[[str], None]],
) -> int:
    script_path = workspace / "runner" / "bin" / "finish_task.sh"
    if not script_path.exists():
        script_path = REPO_ROOT / "runner" / "bin" / "finish_task.sh"
    if not script_path.exists():
        raise CodexRunnerError("finish_task.sh script is missing")

    script_path = script_path.resolve()
    try:
        script_path.chmod(script_path.stat().st_mode | 0o111)
    except OSError:
        pass

    process = subprocess.run(
        [str(script_path)],
        cwd=str(workspace),
        check=False,
        capture_output=True,
        text=True,
        env=env,
    )

    if log_fn and process.stdout:
        for line in process.stdout.splitlines():
            log_fn(line)
    if log_fn and process.stderr:
        for line in process.stderr.splitlines():
            log_fn(f"stderr: {line}")

    return process.returncode


def _load_finish_metadata(result_path: Path, log_fn: Optional[Callable[[str], None]]) -> tuple[Optional[str], Optional[str]]:
    if not result_path.exists():
        if log_fn:
            log_fn(f"finish_task metadata not found at {result_path}")
        return None, None

    try:
        content = result_path.read_text(encoding="utf-8")
        data = json.loads(content)
    except (OSError, json.JSONDecodeError) as exc:
        if log_fn:
            log_fn(f"Unable to parse finish_task metadata: {exc}")
        return None, None

    branch = data.get("branch")
    mr_url = data.get("mr_url")
    return branch, mr_url


def _load_metadata(metadata_path: Path, log_fn: Optional[Callable[[str], None]]) -> tuple[Optional[str], list[str]]:
    if not metadata_path.exists():
        if log_fn:
            log_fn(f"Metadata file not found at {metadata_path}")
        return None, []

    try:
        payload = json.loads(metadata_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        if log_fn:
            log_fn(f"Unable to parse metadata file {metadata_path}: {exc}")
        return None, []

    version = payload.get("agent_version")
    flags_raw = payload.get("flags", [])
    if isinstance(flags_raw, str):
        flags: list[str] = [flags_raw]
    elif isinstance(flags_raw, list):
        flags = [str(item) for item in flags_raw if item]
    else:
        flags = []
    return version, flags


def _run_local_stub(
    workspace: Path,
    prompt: str,
    allowlist: Iterable[str],
    runner_env: dict[str, str],
    log_fn: Optional[Callable[[str], None]],
) -> int:
    runner_path = workspace / "runner" / "bin" / "codex"
    if not runner_path.exists():
        runner_path = REPO_ROOT / "runner" / "bin" / "codex"
    if not runner_path.exists():
        raise CodexRunnerError("codex CLI script is missing")

    runner_path = runner_path.resolve()
    try:
        runner_path.chmod(runner_path.stat().st_mode | 0o111)
    except OSError:
        # Best effort to ensure executability.
        pass

    env = os.environ.copy()
    env.update(runner_env)
    env["CODEX_PROMPT"] = prompt
    env["EGRESS_ALLOWLIST"] = ",".join(allowlist)
    env["HOME"] = runner_env.get("HOME", str(workspace))

    flags = [flag for flag in runner_env.get("CODEX_INVOCATION_FLAGS", "").split() if flag]
    if "--skip-git-repo-check" not in flags:
        flags.append("--skip-git-repo-check")

    invocation = [str(runner_path), "exec", "--cd", str(workspace), *flags, "-"]

    process = subprocess.run(
        invocation,
        cwd=str(workspace),
        check=False,
        capture_output=True,
        text=True,
        env=env,
        input=prompt,
    )

    if log_fn and process.stdout:
        for line in process.stdout.splitlines():
            log_fn(line)
    if log_fn and process.stderr:
        for line in process.stderr.splitlines():
            log_fn(f"stderr: {line}")

    if process.returncode != 0:
        return process.returncode

    finish_code = _run_finish_task_local(workspace, env, log_fn)
    return finish_code
