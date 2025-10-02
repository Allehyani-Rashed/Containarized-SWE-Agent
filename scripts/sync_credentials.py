#!/usr/bin/env python3
"""Synchronise GitLab and Codex session credentials based on values stored in .env."""

from __future__ import annotations

import argparse
import os
import sys
from pathlib import Path
from typing import Dict

PROJECT_ROOT = Path(__file__).resolve().parents[1]
DEFAULT_ENV_FILE = PROJECT_ROOT / ".env"
DEFAULT_ACTOR = "env-sync"

if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Load GitLab and Codex session credentials from an env file into the local database.",
    )
    parser.add_argument(
        "--env-file",
        type=Path,
        default=DEFAULT_ENV_FILE,
        help="Path to the env file to read (default: %(default)s)",
    )
    parser.add_argument(
        "--actor",
        default=DEFAULT_ACTOR,
        help="Actor metadata recorded alongside stored credentials (default: %(default)s)",
    )
    return parser.parse_args()


def _set_env_vars(values: Dict[str, str]) -> None:
    for key, value in values.items():
        if key == "APP_SECRET_KEY" and value:
            os.environ[key] = value
        elif key not in os.environ:
            os.environ[key] = value


def main() -> int:
    args = _parse_args()
    env_file = args.env_file
    if not env_file.exists():
        print(f"warning: env file not found: {env_file}", file=sys.stderr)
        return 0

    # Defer heavy imports until after env vars are populated.
    from app.app.env_sync import EnvConfig, EnvSyncError, parse_env_file, sync_credentials
    from app.app.secrets import reset_secret_manager

    env_values = parse_env_file(env_file)
    _set_env_vars(env_values)
    reset_secret_manager()

    if "CHATGPT_SESSION_BUNDLE" in env_values:
        print(
            "warning: CHATGPT_SESSION_BUNDLE is deprecated; rename it to CHATGPT_SESSION_JSON",
            file=sys.stderr,
        )

    session_bundle_json = env_values.get("CHATGPT_SESSION_JSON")
    session_bundle_path = env_values.get("CHATGPT_SESSION_BUNDLE_PATH")
    bundle_path = Path(session_bundle_path).expanduser() if session_bundle_path else None

    config = EnvConfig(
        gitlab_pat=env_values.get("GITLAB_PAT"),
        project_name=env_values.get("PROJECT_NAME"),
        project_default_branch=env_values.get("PROJECT_DEFAULT_BRANCH"),
        gitlab_host=env_values.get("GITLAB_HOST"),
        gitlab_project_path=env_values.get("GITLAB_PROJECT_PATH"),
        session_bundle_path=bundle_path,
        session_bundle_json=session_bundle_json,
        actor=args.actor,
    )

    try:
        result = sync_credentials(config, repo_root=PROJECT_ROOT)
    except EnvSyncError as exc:
        print(f"error: credential sync failed: {exc}", file=sys.stderr)
        return 1

    messages = []
    if result.gitlab_pat_updated:
        messages.append("GitLab PAT stored")
    if result.session_bundle_updated:
        messages.append("ChatGPT session bundle stored")
    if result.project_created:
        messages.append(f"Project created (id={result.project_id})")
    elif result.project_updated:
        messages.append(f"Project updated (id={result.project_id})")
    if messages:
        print("; ".join(messages))
    else:
        print("No credentials updated; check env values if this is unexpected")

    if result.session_bundle_error:
        print(f"warning: {result.session_bundle_error}", file=sys.stderr)

    return 0


if __name__ == "__main__":  # pragma: no cover
    sys.exit(main())
