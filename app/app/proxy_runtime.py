from __future__ import annotations

import os
import shutil
import subprocess
import time
from pathlib import Path
from typing import Callable, Optional

import docker
from docker.errors import APIError, DockerException, NotFound

from .codex_runner import DEFAULT_DOCKER_NETWORK

REPO_ROOT = Path(__file__).resolve().parents[2]
DEFAULT_PROXY_CONTAINER = "codex-egress-proxy"
DEFAULT_COMPOSE_SERVICE = "codex-egress-proxy"
DEFAULT_PRECHECK_TIMEOUT = 15.0
LogFn = Optional[Callable[[str], None]]


def ensure_proxy_stack(log_fn: LogFn = None, timeout: float = DEFAULT_PRECHECK_TIMEOUT) -> bool:
    """Ensure the Tinyproxy container and shared network exist before runner launch."""

    if os.environ.get("DISABLE_PROXY") == "1":
        if log_fn:
            log_fn("proxy disabled via DISABLE_PROXY=1; skipping proxy preflight")
        return True

    container_name = os.environ.get("PROXY_CONTAINER_NAME", DEFAULT_PROXY_CONTAINER)
    compose_service = os.environ.get("PROXY_COMPOSE_SERVICE", DEFAULT_COMPOSE_SERVICE)
    network_name = os.environ.get("RUNNER_DOCKER_NETWORK", DEFAULT_DOCKER_NETWORK)

    try:
        client = docker.from_env()
    except DockerException as exc:
        if log_fn:
            log_fn(f"unable to connect to Docker daemon: {exc}")
        return False

    try:
        container = _ensure_container(client, container_name, compose_service, log_fn)
        if container is None:
            return False

        if not _confirm_container_running(container, log_fn, timeout):
            return False

        if network_name:
            if not _ensure_network_present(client, network_name, compose_service, log_fn):
                return False

            if not _ensure_container_network(client, network_name, container.id, log_fn, timeout):
                return False

        if log_fn:
            ip_addr = _container_ip(container, network_name)
            suffix = f" (network {network_name} IP {ip_addr})" if ip_addr else ""
            log_fn(f"proxy container '{container_name}' ready{suffix}")
        return True
    finally:
        try:
            client.close()
        except Exception:
            pass


def preflight_proxy_stack(*, docker_disabled: bool, log_fn: LogFn = None) -> bool:
    """Run the proxy preflight gate, respecting docker-disabled scenarios."""

    if docker_disabled:
        if log_fn:
            log_fn("Skipping proxy preflight (Docker disabled)")
        return True
    if log_fn:
        log_fn("Verifying proxy stack readiness")
    return ensure_proxy_stack(log_fn=log_fn)


def _ensure_network_present(
    client: docker.DockerClient,
    network_name: str,
    compose_service: str,
    log_fn: LogFn,
) -> bool:
    if not network_name:
        return True

    try:
        client.networks.get(network_name)
        return True
    except NotFound:
        if log_fn:
            log_fn(
                f"docker network '{network_name}' not found; attempting to recreate via docker compose",
            )
        if _start_proxy_via_compose(compose_service, log_fn):
            try:
                client.networks.get(network_name)
                return True
            except NotFound:
                if log_fn:
                    log_fn(
                        f"docker network '{network_name}' still missing after docker compose up",
                    )
                return False
        if log_fn:
            log_fn(
                "unable to recreate proxy network via docker compose; manual intervention required",
            )
        return False
    except DockerException as exc:
        if log_fn:
            log_fn(f"error while inspecting docker network '{network_name}': {exc}")
        return False


def _ensure_container(
    client: docker.DockerClient,
    container_name: str,
    compose_service: str,
    log_fn: LogFn,
) -> Optional[docker.models.containers.Container]:
    container = _get_container(client, container_name)
    if container is None:
        if log_fn:
            log_fn(f"proxy container '{container_name}' not found; starting via docker compose")
        if not _start_proxy_via_compose(compose_service, log_fn):
            return None
        time.sleep(1)
        container = _get_container(client, container_name)
        if container is None:
            if log_fn:
                log_fn(f"proxy container '{container_name}' still missing after docker compose up")
            return None

    try:
        container.reload()
    except DockerException as exc:
        if log_fn:
            log_fn(f"unable to refresh proxy container state: {exc}")
        return None

    status = container.attrs.get("State", {}).get("Status")
    if status != "running":
        if log_fn:
            log_fn(f"proxy container '{container_name}' status is '{status}'; attempting to start")
        try:
            container.start()
        except DockerException as exc:
            if log_fn:
                log_fn(f"failed to start proxy container '{container_name}': {exc}")
            return None
    return container


def _ensure_container_network(
    client: docker.DockerClient,
    network_name: str,
    container_id: str,
    log_fn: LogFn,
    timeout: float,
) -> bool:
    try:
        network = client.networks.get(network_name)
    except DockerException as exc:
        if log_fn:
            log_fn(f"unable to inspect network '{network_name}': {exc}")
        return False

    network.reload()
    attached = (network.attrs or {}).get("Containers") or {}
    if container_id in attached:
        return True

    if log_fn:
        log_fn(f"proxy container not attached to network '{network_name}'; connecting")
    try:
        network.connect(container_id)
    except APIError as exc:
        # It's possible another process connected it between reload and connect.
        message = str(exc)
        if "already exists" not in message.lower():
            if log_fn:
                log_fn(f"failed to connect proxy container to network '{network_name}': {exc}")
            return False
    except DockerException as exc:
        if log_fn:
            log_fn(f"error connecting proxy container to network '{network_name}': {exc}")
        return False

    return _confirm_network_attachment(client, network_name, container_id, log_fn, timeout)


def _confirm_container_running(
    container: docker.models.containers.Container,
    log_fn: LogFn,
    timeout: float,
) -> bool:
    deadline = time.time() + timeout
    while time.time() < deadline:
        try:
            container.reload()
        except DockerException as exc:
            if log_fn:
                log_fn(f"unable to reload proxy container state: {exc}")
            return False
        status = container.attrs.get("State", {}).get("Status")
        if status == "running":
            return True
        time.sleep(0.5)
    if log_fn:
        log_fn("proxy container failed to reach running state before timeout")
    return False


def _confirm_network_attachment(
    client: docker.DockerClient,
    network_name: str,
    container_id: str,
    log_fn: LogFn,
    timeout: float,
) -> bool:
    deadline = time.time() + timeout
    while time.time() < deadline:
        try:
            network = client.networks.get(network_name)
            network.reload()
        except DockerException as exc:
            if log_fn:
                log_fn(f"unable to reload network '{network_name}': {exc}")
            return False
        attached = (network.attrs or {}).get("Containers") or {}
        if container_id in attached:
            return True
        time.sleep(0.5)
    if log_fn:
        log_fn(f"proxy container did not attach to network '{network_name}' before timeout")
    return False


def _container_ip(
    container: docker.models.containers.Container,
    network_name: Optional[str],
) -> Optional[str]:
    if not network_name:
        return None
    networks = (container.attrs or {}).get("NetworkSettings", {}).get("Networks", {})
    details = networks.get(network_name)
    if not details:
        return None
    return details.get("IPAddress")


def _get_container(
    client: docker.DockerClient,
    container_name: str,
) -> Optional[docker.models.containers.Container]:
    try:
        return client.containers.get(container_name)
    except NotFound:
        return None
    except DockerException:
        return None


def _start_proxy_via_compose(service: str, log_fn: LogFn) -> bool:
    commands = []
    custom = os.environ.get("COMPOSE_COMMAND")
    if custom:
        commands.append(custom.strip().split())
    commands.append(["docker", "compose"])
    commands.append(["docker-compose"])

    for base_cmd in commands:
        if not base_cmd:
            continue
        executable = base_cmd[0]
        if shutil.which(executable) is None:
            continue
        cmd = base_cmd + ["up", "-d", service]
        try:
            result = subprocess.run(
                cmd,
                cwd=str(REPO_ROOT),
                check=False,
                capture_output=True,
                text=True,
            )
        except OSError as exc:
            if log_fn:
                log_fn(f"failed to invoke {' '.join(cmd)}: {exc}")
            continue
        if result.returncode == 0:
            if log_fn:
                log_fn(f"started proxy service via: {' '.join(cmd)}")
            return True
        stderr = (result.stderr or "").strip()
        if log_fn:
            log_fn(f"compose command {' '.join(cmd)} failed: {stderr or 'unknown error'}")
    if log_fn:
        log_fn("unable to start proxy service via docker compose; manual intervention required")
    return False
